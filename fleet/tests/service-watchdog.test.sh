#!/usr/bin/env bash
# service-watchdog.test.sh — e2e DOGFOOD for SERVICE-LIVENESS-WATCHDOG.
#
# GREEN IS NOT PROOF. This SEEDS real faults with a DISPOSABLE CANARY and proves the watchdog
# detects each, then goes clean when reverted. It supervises money-path infra (the grader-daemon
# + broker), so a fake-green here is worse than none.
#
# The canary is TWO real, disposable pieces so ALIVE and FRESH are independently controllable:
#   - a live "process" (a renamed `sleep` whose cmdline carries a unique marker) — kill it => DEAD
#   - a writer loop touching an output file — kill it (process stays alive) => STALE (HUNG case)
#
# monit is NOT installed on this box (verified: env probe). The registry/generator/discovery/
# freshness/self-watch LOGIC is exercised fully monit-INDEPENDENTLY here. The steps that require a
# LIVE monit daemon (monit itself performing the restart, monit's reboot-persistence) are marked
# [BLOCKED-ON-OPERATOR] and print the exact install command — they are NOT silently skipped.
#
# Covers the ticket's accept items:
#   (b) add a registry row            -> rendered into monit config                    [done]
#   (a) kill a registered service     -> watchdog detects DEAD; restart is WIRED in config
#                                        (monit performing the restart is [BLOCKED-ON-OPERATOR])
#   (c) freeze output, process alive  -> STALE alarm fires (anti-staleness / hung service) [done]
#   (d) kill monit                    -> self-watch relaunches it (fake-monit seam)      [done]
#   (e) FAIL-ON-REVERT                -> neuter the freshness probe => STALE detection is LOST
#                                        (proves the freshness probe is load-bearing)     [done]
#
# Run:  bash fleet/tests/service-watchdog.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
WD="$SRC/watchdog"
GEN="$WD/generate-monit-config.sh"
DISC="$WD/discover-services.sh"
SELF="$WD/monit-selfwatch.sh"
for f in "$GEN" "$DISC" "$SELF" "$WD/watchdog-lib.sh"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
OUT="$D/canary.out"
REG="$D/registry.tsv"
TAB="$(printf '\t')"
MARKER="wdcanary$$"          # unique cmdline marker for the alive process
CANARY_PID=""; WRITER_PID=""

cleanup(){
  [ -n "$WRITER_PID" ] && kill "$WRITER_PID" 2>/dev/null
  [ -n "$CANARY_PID" ] && kill "$CANARY_PID" 2>/dev/null
  rm -rf "$D"
}
trap cleanup EXIT

# write_registry <ttl> [extra-row] — one canary row (+ optional extra row) into $REG.
write_registry(){
  local ttl="$1" extra="${2:-}"
  {
    printf '# test registry\n'
    printf 'canary%sprocess%spgrep:%s%sfile:%s%s%s%stouch %s/restart.flag%stest\n' \
      "$TAB" "$TAB" "$MARKER" "$TAB" "$OUT" "$TAB" "$ttl" "$TAB" "$D" "$TAB"
    [ -n "$extra" ] && printf '%s\n' "$extra"
  } > "$REG"
}

start_canary(){   # a real live process whose cmdline carries $MARKER (alive_probe target)
  bash -c "exec -a $MARKER sleep 300" &
  CANARY_PID=$!
}
start_writer(){   # a real loop keeping $OUT fresh
  ( while :; do date +%s > "$OUT"; sleep 0.2; done ) &
  WRITER_PID=$!
}
freeze_writer(){ [ -n "$WRITER_PID" ] && kill "$WRITER_PID" 2>/dev/null; WRITER_PID=""; }

run_health(){ WD_REGISTRY="$REG" bash "$DISC" --health --no-dark "$@" 2>&1; }

echo "=== SERVICE-WATCHDOG DOGFOOD (monit-independent legs) ==="

# ── (b) add a registry row -> rendered into monit config ─────────────────────
write_registry 2
GENOUT="$(WD_REGISTRY="$REG" bash "$GEN" --stdout 2>&1)"
printf '%s' "$GENOUT" | grep -q 'check process canary matching' \
  && ok "(b) registry row renders a monit 'check process' stanza" \
  || bad "(b) canary process stanza not rendered:
$GENOUT"
printf '%s' "$GENOUT" | grep -q 'check file canary-freshness' \
  && ok "(b) freshness_probe renders a monit 'check file ...-freshness' stanza" \
  || bad "(b) freshness stanza not rendered"
printf '%s' "$GENOUT" | grep -q "touch $D/restart.flag" \
  && ok "(a-wire) restart_cmd is WIRED into the monit start/exec action" \
  || bad "(a-wire) restart_cmd not present in rendered config"

# adding a SECOND row -> both services rendered (auto-incorporate)
EXTRA="canary2${TAB}process${TAB}pgrep:${MARKER}2${TAB}none${TAB}0${TAB}/bin/true${TAB}test"
write_registry 2 "$EXTRA"
GEN2="$(WD_REGISTRY="$REG" bash "$GEN" --stdout 2>&1)"
{ printf '%s' "$GEN2" | grep -q 'check process canary matching' && printf '%s' "$GEN2" | grep -q 'check process canary2 matching'; } \
  && ok "(b) adding a registry row -> that service is monitored on next render" \
  || bad "(b) second row not incorporated on render"
write_registry 2   # back to single canary row

# ── (H) baseline: alive + fresh -> CLEAN ─────────────────────────────────────
start_canary; start_writer
sleep 0.5
if OUT_H="$(run_health)"; then ok "(H) alive+fresh canary -> watchdog CLEAN (exit 0)"
else bad "(H) healthy canary not CLEAN:
$OUT_H"; fi

# ── (c) freeze output while process stays ALIVE -> STALE alarm (anti-staleness)
freeze_writer
sleep 3                                   # exceed the 2s TTL
if OUT_S="$(run_health)"; then
  bad "(c) STALE not detected — watchdog stayed CLEAN with frozen output:
$OUT_S"
else
  printf '%s' "$OUT_S" | grep -q 'STALE' \
    && ok "(c) frozen output + live process -> STALE alarm fires (the 9-day-stale-grader case)" \
    || bad "(c) exited RED but no STALE line:
$OUT_S"
fi

# ── (e) FAIL-ON-REVERT: neuter the freshness probe -> STALE detection is LOST ─
# Prove the freshness probe is load-bearing: a watchdog copy whose wd_probe_fresh always returns
# FRESH must FAIL to detect the very stale canary above. If a future edit removes the freshness
# logic, test (c) flips to CLEAN and FAILS — that linkage is what makes (c) a real guard.
REVDIR="$D/reverted"; mkdir -p "$REVDIR"
cp "$WD"/watchdog-lib.sh "$WD"/discover-services.sh "$REVDIR"/
# revert = neuter the freshness probe (always N/A) so nothing is ever STALE/MISS. discover-services.sh
# sources the lib from its OWN dir, so patching the copied lib disables freshness for the reverted copy.
sed -i 's/^wd_probe_fresh(){/wd_probe_fresh(){ return 3;/' "$REVDIR/watchdog-lib.sh"
grep -q 'wd_probe_fresh(){ return 3;' "$REVDIR/watchdog-lib.sh" || bad "(e) revert seam did not patch the lib — test bug"
REV_OUT="$(WD_REGISTRY="$REG" bash "$REVDIR/discover-services.sh" --health --no-dark 2>&1)"; REV_RC=$?
if [ "$REV_RC" -eq 0 ] && ! printf '%s' "$REV_OUT" | grep -q 'STALE'; then
  ok "(e) fail-on-revert: removing the freshness probe LOSES stale detection -> proves (c) is load-bearing"
else
  bad "(e) reverted watchdog still flagged stale (rc=$REV_RC) — the revert seam is wrong, (c) may be a false guard:
$REV_OUT"
fi

# ── (a) kill the registered service -> DEAD detected (restart is monit's job) ─
kill "$CANARY_PID" 2>/dev/null; CANARY_PID=""
sleep 0.3
if OUT_D="$(run_health)"; then
  bad "(a) DEAD not detected — watchdog CLEAN with the canary process killed:
$OUT_D"
else
  printf '%s' "$OUT_D" | grep -q 'DEAD' \
    && ok "(a) killed service -> watchdog detects DEAD (rc 1)" \
    || bad "(a) exited RED but no DEAD line:
$OUT_D"
fi

# ── (d) kill monit -> self-watch relaunches (fake-monit seam; monit not installed) ──
FAKE="$D/fake-monit"; UPFLAG="$D/monit.up"; STATE="$D/monit.state"; RELAUNCH="$D/relaunch.flag"
cat > "$FAKE" <<EOF
#!/usr/bin/env bash
# fake monit: 'status' succeeds only while the up-flag exists.
case "\$1" in status) [ -f "$UPFLAG" ] && exit 0 || exit 1;; esac
exit 0
EOF
chmod +x "$FAKE"
# healthy monit: up-flag present + fresh state file
touch "$UPFLAG"; : > "$STATE"
if SELFWATCH_MONIT_BIN="$FAKE" SELFWATCH_STATE="$STATE" SELFWATCH_TTL=300 \
   SELFWATCH_RELAUNCH_CMD="touch $RELAUNCH" bash "$SELF" --check >/dev/null 2>&1; then
  ok "(d) self-watch reports HEALTHY when monit responds + state fresh"
else
  bad "(d) self-watch flagged a healthy monit as down"
fi
# kill monit: remove up-flag -> status fails -> relaunch must fire
rm -f "$UPFLAG" "$RELAUNCH"
SELFWATCH_MONIT_BIN="$FAKE" SELFWATCH_STATE="$STATE" SELFWATCH_TTL=300 \
  SELFWATCH_RELAUNCH_CMD="touch $RELAUNCH" bash "$SELF" >/dev/null 2>&1
[ -f "$RELAUNCH" ] \
  && ok "(d) killed monit -> self-watch RELAUNCHES it (relaunch command fired)" \
  || bad "(d) monit down but self-watch did NOT relaunch"
# hung monit: up-flag present but state stale -> relaunch must fire
touch "$UPFLAG"; rm -f "$RELAUNCH"; touch -d '1 hour ago' "$STATE"
SELFWATCH_MONIT_BIN="$FAKE" SELFWATCH_STATE="$STATE" SELFWATCH_TTL=60 \
  SELFWATCH_RELAUNCH_CMD="touch $RELAUNCH" bash "$SELF" >/dev/null 2>&1
[ -f "$RELAUNCH" ] \
  && ok "(d) HUNG monit (stale state) -> self-watch relaunches (heartbeat freshness caught)" \
  || bad "(d) monit hung but self-watch did NOT relaunch"

# ── (e2) generator drift check: committed monit.d matches the real registry ──
if bash "$GEN" --check >/dev/null 2>&1; then
  ok "(e2) committed monit.d is IN SYNC with the real service-registry.tsv"
else
  bad "(e2) monit.d DRIFT vs registry — run: fleet/watchdog/generate-monit-config.sh"
fi

echo
echo "[BLOCKED-ON-OPERATOR] monit is not installed on this box; the following require a live monit"
echo "  and are proven only once the operator installs it:"
echo "    - monit itself PERFORMING the restart of a dead/stale service (detection + wiring proven above)"
echo "    - monit reboot-persistence via systemd (pid 1 IS systemd — verified)"
echo "  Install:  sudo apt-get install -y monit"
echo "            fleet/watchdog/generate-monit-config.sh"
echo "            sudo cp fleet/watchdog/monit.d/*.conf /etc/monit/conf.d/ && sudo systemctl enable --now monit"
echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL SERVICE-WATCHDOG DOGFOOD TESTS PASS"
