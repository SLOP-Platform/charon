#!/usr/bin/env bash
# canary-service.test.sh — RED-PROOF for the always-on gate-test canary (4LOM-CANARY-SERVICE).
#
# GREEN IS NOT PROOF. Everything below is proven by EXECUTION against a throwaway fixture suite
# under `mktemp -d` — synthetic *.test.sh files with known, seeded behaviours — so the canary's
# verdict is observed, never asserted from source. No network, no real gate run, ~12s.
#
# The four seeded behaviours are exactly the four the canary must tell apart:
#   aa-green   always passes                      -> green / ok
#   bb-broken  always fails (rc=1)                -> red   / broken          (the 8 genuine reds)
#   cc-flaky   fails its 1st run, passes its 2nd  -> slow  / slow            (the reconcile-merged
#                                                    class: fails under the concurrent runner,
#                                                    passes standalone — adjudicated by the
#                                                    SERIAL re-run, not by rc)
#   dd-slowto  sleeps past the CONCURRENT timeout -> slow  / slow-timeout    (rc=124, but passes
#                                                    when re-run alone => the LOAD failed)
#   ee-hung    sleeps past BOTH timeouts          -> red   / broken-timeout  (rc=124 even alone =>
#                                                    too slow to finish IS a failure, not a flake)
#
# Also red-proofed here, each by execution: the non-vacuous refusal (rc=3), the fail-closed
# machinery refusal (rc=4), the STALE-report refusal (rc=5, the 9-day-dead-grader class), the
# fork-bomb reentrancy guard (rc=6), the distinct DEGRADED-vs-RED exit codes (2 vs 1), the exact
# 4-column report grammar, the watchdog registry registration, and the deploy script's
# no-sudo / no-monit / nothing-enabled-for-you contract.
#
# Run:  bash fleet/tests/canary-service.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
RUNNER="$SRC/canary-service/run-canary.sh"
DEPLOY="$SRC/canary-service/deploy-4lom.sh"
REGISTRY="$SRC/state/service-registry.tsv"
for f in "$RUNNER" "$DEPLOY"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
TAB="$(printf '\t')"

# The canary refuses to run nested (gate.sh exports CHARON_GATE_ACTIVE=1 into every test it
# spawns). The escape hatch is honoured ONLY for a tests dir that is not the real fleet/tests —
# case (k) below proves the recursive path itself stays permanently closed.
export CANARY_ALLOW_NESTED=1

# ── fixture builder ──────────────────────────────────────────────────────────────────────────
mk_fixture(){ # mk_fixture <dir> <behaviour...>
  local root="$1"; shift
  mkdir -p "$root/tests" "$root/state"
  local b
  for b in "$@"; do
    case "$b" in
      green)  printf '#!/usr/bin/env bash\nexit 0\n' > "$root/tests/aa-green.test.sh" ;;
      broken) printf '#!/usr/bin/env bash\nexit 1\n' > "$root/tests/bb-broken.test.sh" ;;
      flaky)  # fails its FIRST invocation, passes its second => concurrent-fail / serial-pass
              printf '#!/usr/bin/env bash\nC="$(dirname "$0")/../cc-count"\nn=$(( $(cat "$C" 2>/dev/null || echo 0) + 1 ))\necho "$n" > "$C"\n[ "$n" -ge 2 ]\n' > "$root/tests/cc-flaky.test.sh" ;;
      slowto) printf '#!/usr/bin/env bash\nsleep 2\nexit 0\n' > "$root/tests/dd-slowto.test.sh" ;;
      hung)   printf '#!/usr/bin/env bash\nsleep 60\nexit 0\n' > "$root/tests/ee-hung.test.sh" ;;
      ambient) # the MEASURED reconcile-merged class: still fails the FIRST serial re-run under
              # residual box load, passes the second. Only the bounded retry classifies it right.
              printf '#!/usr/bin/env bash\nC="$(dirname "$0")/../rr-count"\nn=$(( $(cat "$C" 2>/dev/null || echo 0) + 1 ))\necho "$n" > "$C"\n[ "$n" -ge 3 ]\n' > "$root/tests/rr-ambient.test.sh" ;;
    esac
  done
}

run_canary(){ # run_canary <fixture-root> [extra env assignments...] ; echoes rc
  local root="$1"; shift
  local rc=0
  env CANARY_FLEET="$root" CANARY_TESTS_DIR="$root/tests" \
      CANARY_REPORT="$root/state/canary-report.tsv" CANARY_LOG_DIR="$root/state/canary-logs" \
      CANARY_TIMEOUT_S=1 CANARY_SERIAL_TIMEOUT_S=3 CANARY_JOBS=8 CANARY_GIT_PULL=0 \
      "$@" bash "$RUNNER" run > "$root/run.out" 2>&1 || rc=$?
  echo "$rc"
}

status_canary(){ # status_canary <fixture-root> [extra env] ; echoes rc, output -> <root>/status.out
  local root="$1"; shift
  local rc=0
  env CANARY_FLEET="$root" CANARY_TESTS_DIR="$root/tests" \
      CANARY_REPORT="$root/state/canary-report.tsv" \
      "$@" bash "$RUNNER" status > "$root/status.out" 2>&1 || rc=$?
  echo "$rc"
}

attr_of(){ # attr_of <report> <test-name> -> attribution column
  awk -F"$TAB" -v n="$2" '$1==n{print $4}' "$1" | head -1
}
status_of(){ awk -F"$TAB" -v n="$2" '$1==n{print $3!=""?$2:""}' "$1" | head -1; }
meta_of(){ grep -m1 "^# meta$TAB" "$1" | tr "$TAB" '\n' | awk -v k="$2=" 'index($0,k)==1{sub(/^[^=]*=/,"");print;exit}'; }

# ── (a) FULL ATTRIBUTION: all five behaviours in one run ─────────────────────────────────────
A="$D/a"; mk_fixture "$A" green broken flaky slowto hung
RC_A="$(run_canary "$A")"
REP_A="$A/state/canary-report.tsv"

if [ -f "$REP_A" ]; then ok "(a0) report written to the cached path"; else bad "(a0) no report at $REP_A"; fi

check_attr(){ # check_attr <label> <test> <want-status> <want-attr>
  local got_s got_a
  got_s="$(status_of "$REP_A" "$2")"; got_a="$(attr_of "$REP_A" "$2")"
  if [ "$got_s" = "$3" ] && [ "$got_a" = "$4" ]; then
    ok "$1 $2 -> $got_s/$got_a"
  else
    bad "$1 $2 -> got '$got_s/$got_a', want '$3/$4'"
  fi
}
check_attr "(a1)" aa-green.test.sh  green ok
check_attr "(a2)" bb-broken.test.sh red   broken
# THE load-bearing distinction: cc-flaky and bb-broken BOTH fail the concurrent phase with rc=1.
# Only the serial re-run separates them. If phase 2 is ever removed, (a3) flips to red/broken.
check_attr "(a3)" cc-flaky.test.sh  slow  slow
check_attr "(a4)" dd-slowto.test.sh slow  slow-timeout
check_attr "(a5)" ee-hung.test.sh   red   broken-timeout

# ── (b) exit code + meta counts for a mixed run: BROKEN present => rc=1 ──────────────────────
if [ "$RC_A" = "1" ]; then ok "(b1) mixed run with genuine reds exits 1 (RED)"; else bad "(b1) mixed run exit=$RC_A want 1"; fi
if [ "$(meta_of "$REP_A" broken)" = "2" ] && [ "$(meta_of "$REP_A" slow)" = "2" ] && [ "$(meta_of "$REP_A" green)" = "1" ]; then
  ok "(b2) meta counts green=1 broken=2 slow=2"
else
  bad "(b2) meta counts wrong: green=$(meta_of "$REP_A" green) broken=$(meta_of "$REP_A" broken) slow=$(meta_of "$REP_A" slow)"
fi
if [ "$(meta_of "$REP_A" verdict)" = "red" ]; then ok "(b3) meta verdict=red"; else bad "(b3) meta verdict=$(meta_of "$REP_A" verdict)"; fi

# ── (b4) REPORT GRAMMAR: every data row is exactly 4 TAB columns (test|status|last_run|attr) ─
badrows="$(grep -v '^#' "$REP_A" | awk -F"$TAB" 'NF!=4' | wc -l | tr -d ' ')"
nrows="$(grep -cv '^#' "$REP_A" || true)"
if [ "$badrows" = "0" ] && [ "$nrows" = "5" ]; then ok "(b4) report grammar: 5 rows, all exactly 4 columns"; else bad "(b4) report grammar: rows=$nrows malformed=$badrows"; fi

# ── (c) DEGRADED is a DISTINCT exit code from RED (slow-only run => rc=2, not 1 and not 0) ───
C="$D/c"; mk_fixture "$C" green flaky
RC_C="$(run_canary "$C")"
REP_C="$C/state/canary-report.tsv"
if [ "$RC_C" = "2" ]; then ok "(c1) slow-only run exits 2 (DEGRADED) — distinct from RED(1) and GREEN(0)"; else bad "(c1) slow-only run exit=$RC_C want 2"; fi
if [ "$(meta_of "$REP_C" verdict)" = "degraded" ] && [ "$(meta_of "$REP_C" broken)" = "0" ]; then ok "(c2) slow-only verdict=degraded, broken=0"; else bad "(c2) slow-only verdict=$(meta_of "$REP_C" verdict) broken=$(meta_of "$REP_C" broken)"; fi

# ── (c4/c5) BOUNDED SERIAL RETRY, and its fail-on-revert ─────────────────────────────────────
# rr-ambient fails its concurrent run AND its first serial re-run, passing only on the second —
# the measured `reconcile-merged` wall-clock case. With the shipped 2 attempts it must read SLOW;
# knock attempts back to 1 (the pre-fix behaviour) and the SAME check flips to BROKEN. That flip
# is the proof the retry is load-bearing, not decoration.
R2="$D/r2"; mk_fixture "$R2" green ambient
RC_R2="$(run_canary "$R2" CANARY_SERIAL_ATTEMPTS=2)"
if [ "$(attr_of "$R2/state/canary-report.tsv" rr-ambient.test.sh)" = "slow" ] && [ "$RC_R2" = "2" ]; then
  ok "(c4) 2 serial attempts classify the ambient-load red as SLOW (rc=2 DEGRADED)"
else
  bad "(c4) ambient red with 2 attempts -> '$(attr_of "$R2/state/canary-report.tsv" rr-ambient.test.sh)' rc=$RC_R2, want slow/2"
fi
R1="$D/r1"; mk_fixture "$R1" green ambient
RC_R1="$(run_canary "$R1" CANARY_SERIAL_ATTEMPTS=1)"
if [ "$(attr_of "$R1/state/canary-report.tsv" rr-ambient.test.sh)" = "broken" ] && [ "$RC_R1" = "1" ]; then
  ok "(c5) fail-on-revert: 1 serial attempt MISLABELS the same check as BROKEN — the retry is load-bearing"
else
  bad "(c5) ambient red with 1 attempt -> '$(attr_of "$R1/state/canary-report.tsv" rr-ambient.test.sh)' rc=$RC_R1, want broken/1"
fi

# ── (c3) all-green run exits 0 ───────────────────────────────────────────────────────────────
G="$D/g"; mk_fixture "$G" green
RC_G="$(run_canary "$G")"
if [ "$RC_G" = "0" ]; then ok "(c3) all-green run exits 0"; else bad "(c3) all-green run exit=$RC_G want 0"; fi

# ── (d) NON-VACUOUS: zero discovered checks is RED (rc=3), never a silent pass ───────────────
V="$D/v"; mk_fixture "$V"          # tests/ exists but is EMPTY
RC_V="$(run_canary "$V")"
REP_V="$V/state/canary-report.tsv"
if [ "$RC_V" = "3" ]; then ok "(d1) vacuous run (0 checks discovered) exits 3 — not 0"; else bad "(d1) vacuous run exit=$RC_V want 3"; fi
if [ "$(meta_of "$REP_V" verdict)" = "vacuous" ] && [ "$(meta_of "$REP_V" total)" = "0" ]; then ok "(d2) vacuous report records verdict=vacuous total=0"; else bad "(d2) vacuous meta verdict=$(meta_of "$REP_V" verdict)"; fi
RC_VS="$(status_canary "$V")"
if [ "$RC_VS" != "0" ] && grep -q 'RED' "$V/status.out"; then ok "(d3) status on a vacuous report reads RED (rc=$RC_VS)"; else bad "(d3) status on vacuous report: rc=$RC_VS out=$(cat "$V/status.out")"; fi

# ── (e) FAIL-CLOSED: missing machinery is RED (rc=4), never skipped ─────────────────────────
M="$D/m"; mkdir -p "$M/state"      # NO tests/ directory at all
RC_M="$(run_canary "$M")"
if [ "$RC_M" = "4" ]; then ok "(e1) missing tests dir => FAIL-CLOSED rc=4 (not skipped, not green)"; else bad "(e1) missing tests dir exit=$RC_M want 4"; fi
if grep -q 'FAIL-CLOSED' "$M/run.out"; then ok "(e2) fail-closed reason is printed"; else bad "(e2) no FAIL-CLOSED reason in output"; fi

# ── (f) STALENESS: past ttl the cached verdict is UNKNOWN, never last-known-good ────────────
# This is the exact failure that let a dead grader look healthy for 9 days.
LAST_G="$(meta_of "$G/state/canary-report.tsv" last_run)"
TTL_G="$(meta_of "$G/state/canary-report.tsv" ttl_s)"
RC_FRESH="$(status_canary "$G" CANARY_NOW="$LAST_G")"
if [ "$RC_FRESH" = "0" ] && grep -qE 'canary: [0-9]+ green / [0-9]+ red \([0-9]+ slow\) @' "$G/status.out"; then
  ok "(f1) FRESH report surfaces the token-lean one-liner: $(cat "$G/status.out")"
else
  bad "(f1) fresh status rc=$RC_FRESH out=$(cat "$G/status.out")"
fi
RC_STALE="$(status_canary "$G" CANARY_NOW="$(( LAST_G + TTL_G + 1 ))")"
if [ "$RC_STALE" = "5" ] && grep -q 'STALE' "$G/status.out" && grep -q 'UNKNOWN' "$G/status.out"; then
  ok "(f2) report 1s past ttl reads UNKNOWN/STALE and exits 5 — the green verdict is NOT reused"
else
  bad "(f2) stale status rc=$RC_STALE out=$(cat "$G/status.out")"
fi
# FAIL-ON-REVERT: neuter the freshness bound (ttl -> huge) and the stale report goes green again,
# proving the ttl comparison is what is doing the work.
sed "s/${TAB}ttl_s=[0-9]*${TAB}/${TAB}ttl_s=999999999${TAB}/" "$G/state/canary-report.tsv" > "$G/state/neutered.tsv"
RC_NEUT=0
env CANARY_REPORT="$G/state/neutered.tsv" CANARY_NOW="$(( LAST_G + TTL_G + 1 ))" bash "$RUNNER" status >/dev/null 2>&1 || RC_NEUT=$?
if [ "$RC_NEUT" = "0" ]; then ok "(f3) fail-on-revert: widening ttl re-greens the same stale report => the ttl check is load-bearing"; else bad "(f3) neutered-ttl status rc=$RC_NEUT want 0"; fi
# A MISSING report is UNKNOWN, not green.
RC_MISS=0
env CANARY_REPORT="$D/nonexistent.tsv" bash "$RUNNER" status > "$D/miss.out" 2>&1 || RC_MISS=$?
if [ "$RC_MISS" = "5" ] && grep -q 'UNKNOWN' "$D/miss.out"; then ok "(f4) missing report reads UNKNOWN/RED (rc=5), never green"; else bad "(f4) missing-report status rc=$RC_MISS out=$(cat "$D/miss.out")"; fi

# ── (g) REENTRANCY: the gate -> canary -> gate recursion stays closed even with the seam set ─
RC_RE=0
env CHARON_GATE_ACTIVE=1 CANARY_ALLOW_NESTED=1 CANARY_TESTS_DIR="$SRC/tests" \
    CANARY_REPORT="$D/reentrancy.tsv" bash "$RUNNER" run > "$D/reentrancy.out" 2>&1 || RC_RE=$?
if [ "$RC_RE" = "6" ] && grep -q 'fork-bomb guard' "$D/reentrancy.out"; then
  ok "(g1) nested run against the REAL fleet/tests is refused (rc=6) even with CANARY_ALLOW_NESTED=1"
else
  bad "(g1) reentrancy guard rc=$RC_RE out=$(cat "$D/reentrancy.out")"
fi
if [ ! -f "$D/reentrancy.tsv" ]; then ok "(g2) a refused run writes no report (cannot fake a verdict)"; else bad "(g2) refused run wrote a report"; fi

# ── (h) WATCHDOG REGISTRATION: the sensor is itself supervised (who-watches-the-canary) ─────
if [ -f "$REGISTRY" ]; then
  row="$(grep -m1 "^canary-service${TAB}" "$REGISTRY" || true)"
  if [ -n "$row" ]; then
    ncol="$(printf '%s' "$row" | awk -F"$TAB" '{print NF}')"
    fresh="$(printf '%s' "$row" | awk -F"$TAB" '{print $4}')"
    ttl="$(printf '%s' "$row" | awk -F"$TAB" '{print $5}')"
    if [ "$ncol" = "7" ]; then ok "(h1) service-registry row present with 7 columns"; else bad "(h1) registry row has $ncol columns, want 7"; fi
    case "$fresh" in
      file:*canary-report.tsv) ok "(h2) registry freshness_probe watches the cached report — a HUNG canary alarms like a dead one" ;;
      *) bad "(h2) registry freshness_probe is '$fresh', want file:...canary-report.tsv" ;;
    esac
    case "$ttl" in ''|*[!0-9]*) bad "(h3) registry freshness_ttl_s is '$ttl', want an integer" ;; 0) bad "(h3) registry ttl is 0 — staleness would never alarm" ;; *) ok "(h3) registry freshness_ttl_s=$ttl" ;; esac
  else
    bad "(h1) no canary-service row in $REGISTRY — the sensor is unsupervised"
  fi
  if [ -f "$SRC/watchdog/monit.d/canary-service.conf" ]; then ok "(h4) rendered monit stanza committed (registry/monit.d in sync)"; else bad "(h4) monit.d/canary-service.conf missing — run fleet/watchdog/generate-monit-config.sh"; fi
else
  bad "(h1) registry not found: $REGISTRY"
fi

# ── (i) DEPLOY CONTRACT: unprivileged, monit-free, enables nothing on its own ───────────────
# Proven by EXECUTION, not by grepping the source: the printed operator instructions legitimately
# CONTAIN the words sudo/systemctl/loginctl, so only a real tripwire can tell "prints it" from
# "runs it". Every privileged/mutating tool is shimmed onto PATH and logs its own invocation.
SHIM="$D/shim"; mkdir -p "$SHIM"; SHIMLOG="$D/shim.log"; : > "$SHIMLOG"
for t in sudo apt-get monit loginctl systemctl; do
  printf '#!/usr/bin/env bash\nprintf "%%s %%s\\n" "%s" "$*" >> "%s"\nexit 0\n' "$t" "$SHIMLOG" > "$SHIM/$t"
  chmod +x "$SHIM/$t"
done
for sub in unit remote-cmd "install $D/units"; do
  # shellcheck disable=SC2086  # deliberate word-split: "install <dest>" is two args
  env PATH="$SHIM:$PATH" CANARY_SETTINGS="$D/settings-probe.json" bash "$DEPLOY" $sub >/dev/null 2>&1 || true
done
if grep -qE '^(sudo|apt-get|monit|loginctl) ' "$SHIMLOG"; then
  bad "(i1) deploy script EXECUTED a privileged/monit tool: $(grep -E '^(sudo|apt-get|monit|loginctl) ' "$SHIMLOG" | head -3 | tr '\n' ';')"
else
  ok "(i1) deploy script executes no sudo / apt-get / monit / loginctl (tripwire clean)"
fi
if grep -qE '^systemctl .*( enable| start| restart| daemon-reload)( |$)' "$SHIMLOG"; then
  bad "(i2) deploy script ENABLED/STARTED a unit itself: $(grep -E '^systemctl ' "$SHIMLOG" | head -3 | tr '\n' ';')"
else
  ok "(i2) deploy script only WRITES units + PRINTS the operator commands (nothing enabled/started)"
fi
if [ -f "$D/units/charon-canary.service" ]; then ok "(i3) install writes the unit file (and only that)"; else bad "(i3) install did not write the unit file"; fi
UNIT_OUT="$($DEPLOY unit 2>&1 || true)"
if grep -q 'run-canary.sh loop' <<<"$UNIT_OUT" && grep -q 'Restart=always' <<<"$UNIT_OUT" && grep -q 'WantedBy=default.target' <<<"$UNIT_OUT"; then
  ok "(i4) unit is a reboot-persistent always-on loop"
else
  bad "(i4) unit missing loop/Restart/WantedBy: $UNIT_OUT"
fi
# wire-surface must be a DRY RUN unless --apply
cp /dev/null "$D/settings.json"; printf '{"hooks":{"SessionStart":[{"hooks":[]}]}}\n' > "$D/settings.json"
BEFORE="$(cat "$D/settings.json")"
CANARY_SETTINGS="$D/settings.json" bash "$DEPLOY" wire-surface > "$D/wire.out" 2>&1 || true
if [ "$BEFORE" = "$(cat "$D/settings.json")" ] && grep -q 'DRY-RUN' "$D/wire.out"; then
  ok "(i5) wire-surface without --apply changes nothing (dry run)"
else
  bad "(i5) wire-surface mutated settings.json without --apply"
fi
CANARY_SETTINGS="$D/settings.json" bash "$DEPLOY" wire-surface --apply > "$D/wire2.out" 2>&1 || true
if grep -q 'run-canary.sh status' "$D/settings.json"; then ok "(i6) wire-surface --apply installs the SessionStart canary line"; else bad "(i6) wire-surface --apply did not wire the surface"; fi
CANARY_SETTINGS="$D/settings.json" bash "$DEPLOY" wire-surface --apply > "$D/wire3.out" 2>&1 || true
if [ "$(grep -c 'run-canary.sh status' "$D/settings.json")" = "1" ]; then ok "(i7) wire-surface is idempotent"; else bad "(i7) wire-surface duplicated the entry"; fi

# ── (j) FAIL-LOUD source contract ────────────────────────────────────────────────────────────
if head -100 "$RUNNER" | grep -q 'set -euo pipefail'; then ok "(j1) runner sets -euo pipefail"; else bad "(j1) runner missing set -euo pipefail"; fi

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL CANARY-SERVICE TESTS PASS"
