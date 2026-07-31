#!/usr/bin/env bash
# verify-restart-cmds.test.sh — FAIL-ON-REVERT dogfood for WATCHDOG-RESTART-CMDS-VERIFY.
#
# GREEN IS NOT PROOF. This suite exists because the thing under test is itself a gate: if it can
# be gamed, silently pass, or pass vacuously, the whole "monit may now be enabled" decision is a
# lie and auto-recovery misfires on the next service death (the 9-day-stale-grader incident at the
# restart step).
#
# It RE-SEEDS EACH OF THE FOUR ORIGINAL DEFECTS and proves verify goes RED on each:
#   grader-daemon  `systemctl restart bench-grader-daemon` (unit does not exist)
#   session-bridge `systemctl --user restart ...`          (meaningless for root)
#   roci-tunnel    `fleet/bridge-reconnect.sh`             (relative path, missing file)
#   gateway-4lom   `ssh 4-LOM sudo systemctl restart ...`  (Host alias root cannot see + sudo)
# ...and it asserts the REAL committed registry passes the static grammar, so reverting any of the
# four back to its broken seed value turns this suite RED.
#
# HERMETIC: every live-mode case runs against fixture registries + fixture scripts under a
# `mktemp -d`, with VERIFY_UNITS_DIR pointed at an empty temp dir, and the selfwatch cases use a
# STUB verify via SELFWATCH_VERIFY. The only real-file dependency is a --static-only (text-only)
# pass over the committed registry. No network, no sudo, no monit, nothing installed.
#
# Run:  bash fleet/tests/verify-restart-cmds.test.sh   (exit 0 = all pass)
set -uo pipefail

SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"        # .../fleet
WD="$SRC/watchdog"
VERIFY="$WD/verify-restart-cmds.sh"
SELF="$WD/monit-selfwatch.sh"
REAL_REG="$SRC/state/service-registry.tsv"
for f in "$VERIFY" "$SELF" "$WD/watchdog-lib.sh" "$REAL_REG"; do
  [ -f "$f" ] || { echo "FAIL: missing $f" >&2; exit 1; }
done

PASS=0; FAIL=0
ok(){  PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){ FAIL=$((FAIL+1)); echo "FAIL: $1"; }

D="$(mktemp -d)"
trap 'rm -rf "$D"' EXIT
TAB="$(printf '\t')"
EMPTY_UNITS="$D/no-units"; mkdir -p "$EMPTY_UNITS"

# A real, executable fixture target so the GREEN baseline is not hand-waved.
GOOD="$D/good-restart.sh"
printf '#!/usr/bin/env bash\nexit 0\n' > "$GOOD"; chmod +x "$GOOD"
NOEXEC="$D/no-exec.sh"; printf '#!/usr/bin/env bash\n' > "$NOEXEC"; chmod 0644 "$NOEXEC"

# reg <file> <restart_cmd>... -> write a registry with one row per restart_cmd given.
reg(){
  local f="$1"; shift
  { echo "# fixture registry"
    local i=0 c
    for c in "$@"; do
      i=$((i+1))
      printf 'svc%s%sprocess%spgrep:svc%s%snone%s0%s%s%sfleet\n' \
        "$i" "$TAB" "$TAB" "$i" "$TAB" "$TAB" "$TAB" "$c" "$TAB"
    done
  } > "$f"
}

# run_verify <registry> [extra args...] -> echoes rc, output on stderr-free capture
run_verify(){
  local r="$1"; shift
  WD_REGISTRY="$r" VERIFY_UNITS_DIR="$EMPTY_UNITS" bash "$VERIFY" "$@" >"$D/out" 2>&1
  echo $?
}

expect_red(){   # expect_red <label> <registry> [args...]
  local label="$1" r="$2"; shift 2
  local rc; rc="$(run_verify "$r" "$@")"
  if [ "$rc" -ne 0 ]; then ok "$label -> RED (rc $rc)"
  else bad "$label -> GREEN, but it MUST be RED. Output:
$(cat "$D/out")"; fi
}
expect_green(){ # expect_green <label> <registry> [args...]
  local label="$1" r="$2"; shift 2
  local rc; rc="$(run_verify "$r" "$@")"
  if [ "$rc" -eq 0 ]; then ok "$label -> GREEN (rc 0)"
  else bad "$label -> RED, but it MUST be GREEN. Output:
$(cat "$D/out")"; fi
}

echo "== 1. baseline: a genuinely runnable restart_cmd is GREEN =="
reg "$D/ok.tsv" "$GOOD"
expect_green "absolute, executable restart_cmd" "$D/ok.tsv"

echo
echo "== 2. THE FOUR ORIGINAL DEFECTS each go RED =="
reg "$D/d1.tsv" "systemctl restart bench-grader-daemon-does-not-exist-$$"
expect_red "grader defect: systemctl restart of a NON-EXISTENT unit" "$D/d1.tsv"
reg "$D/d2.tsv" "systemctl --user restart session-bridge"
expect_red "bridge defect: systemctl --user (meaningless as root)" "$D/d2.tsv"
reg "$D/d3.tsv" "fleet/bridge-reconnect.sh"
expect_red "roci defect: RELATIVE path (monit cwd=/)" "$D/d3.tsv"
reg "$D/d4.tsv" "ssh 4-LOM sudo systemctl restart charon-gateway"
expect_red "gateway defect: ~/.ssh/config Host alias + remote sudo" "$D/d4.tsv"

echo
echo "== 3. root-context hazards =="
# shellcheck disable=SC2088  # a LITERAL tilde is the point: monit-as-root would resolve it to /root
reg "$D/h1.tsv" "~/charon-private/fleet/restart.sh"
expect_red "~ in path (root's ~ is /root)" "$D/h1.tsv"
reg "$D/h2.tsv" "\$HOME/restart.sh"
expect_red "\$HOME in path" "$D/h2.tsv"
reg "$D/h3.tsv" "/bin/sh -c 'echo hi'"
expect_red "single quote (breaks monit's /bin/sh -c '<cmd>' wrapper)" "$D/h3.tsv"
reg "$D/h4.tsv" "/usr/bin/env echo \"x\""
expect_red "double quote (terminates the monit config string)" "$D/h4.tsv"
reg "$D/h5.tsv" "/usr/bin/sudo /bin/systemctl restart x"
expect_red "sudo (monit is already root; no NOPASSWD on the remote leg)" "$D/h5.tsv"
reg "$D/h6.tsv" "$D/does-not-exist.sh"
expect_red "absolute path to a MISSING script" "$D/h6.tsv"
reg "$D/h7.tsv" "$NOEXEC"
expect_red "absolute path to a NON-EXECUTABLE script" "$D/h7.tsv"
reg "$D/h8.tsv" "/usr/bin/setsid relative-thing --go"
expect_red "relative command NESTED behind a wrapper (setsid)" "$D/h8.tsv"
reg "$D/h9.tsv" "/usr/sbin/runuser -u no-such-user-$$ -- $GOOD"
expect_red "runuser target user does not exist" "$D/h9.tsv"
reg "$D/h10.tsv" "none"
expect_red "restart_cmd 'none' (a supervised service with no recovery)" "$D/h10.tsv"

echo
echo "== 4. ssh-leg hygiene =="
reg "$D/s1.tsv" "/usr/bin/ssh -o BatchMode=yes -o UserKnownHostsFile=$D/kh stack@10.0.1.60 true"
expect_red "ssh without -i (root has no keys/agent of its own)" "$D/s1.tsv"
reg "$D/s2.tsv" "/usr/bin/ssh -i $GOOD -o UserKnownHostsFile=$D/kh stack@10.0.1.60 true"
expect_red "ssh without BatchMode=yes (can block on a prompt forever)" "$D/s2.tsv"
reg "$D/s3.tsv" "/usr/bin/ssh -i $GOOD -o BatchMode=yes -o StrictHostKeyChecking=no stack@10.0.1.60 true"
expect_red "ssh with StrictHostKeyChecking=no (weakening a gate to pass it)" "$D/s3.tsv"

echo
echo "== 5. NON-VACUOUS: nothing-to-check must never read as GREEN =="
printf '# only comments, zero service rows\n' > "$D/empty.tsv"
expect_red "registry with ZERO service rows" "$D/empty.tsv"
printf 'svc%sprocess%spgrep:x%snone%s0%s/bin/true\n' "$TAB" "$TAB" "$TAB" "$TAB" "$TAB" > "$D/malformed.tsv"  # 6 cols, want 7
expect_red "MALFORMED row (6 cols) is NOT silently skipped" "$D/malformed.tsv"
expect_red "registry file missing entirely" "$D/nope.tsv"

echo
echo "== 6. shipped units/ must not rot =="
BADU="$D/units-bad"; mkdir -p "$BADU"
printf '[Unit]\nDescription=x\n\n[Service]\nExecStart=/nope/python3 /nope/x.py\nUser=no-such-user-%s\n' "$$" > "$BADU/bogus.service"
reg "$D/u.tsv" "$GOOD"
if WD_REGISTRY="$D/u.tsv" VERIFY_UNITS_DIR="$BADU" bash "$VERIFY" >"$D/out" 2>&1; then
  bad "a shipped unit with a missing ExecStart binary + missing User was accepted"
else
  ok "shipped unit with missing ExecStart binary / unknown User -> RED"
fi
GOODU="$D/units-good"; mkdir -p "$GOODU"
printf '[Unit]\nDescription=x\n\n[Service]\nExecStart=%s\n\n[Install]\nWantedBy=multi-user.target\n' "$GOOD" > "$GOODU/fine.service"
if WD_REGISTRY="$D/u.tsv" VERIFY_UNITS_DIR="$GOODU" bash "$VERIFY" >"$D/out" 2>&1; then
  ok "a well-formed shipped unit is accepted"
else
  bad "a well-formed shipped unit was rejected:
$(cat "$D/out")"
fi

echo
echo "== 7. the ENABLE is actually BLOCKED (monit-selfwatch) =="
STUB_RED="$D/verify-red.sh";   printf '#!/usr/bin/env bash\necho "RED fixture"\nexit 1\n' > "$STUB_RED";   chmod +x "$STUB_RED"
STUB_GREEN="$D/verify-green.sh"; printf '#!/usr/bin/env bash\necho "GREEN fixture"\nexit 0\n' > "$STUB_GREEN"; chmod +x "$STUB_GREEN"
run_gate(){ SELFWATCH_VERIFY="$1" SELFWATCH_SURFACE="" bash "$SELF" --gate-enable >"$D/gate" 2>&1; echo $?; }

rc="$(run_gate "$STUB_RED")"
if [ "$rc" -ne 0 ]; then ok "verify RED -> --gate-enable REFUSES (rc $rc)"
else bad "verify RED but --gate-enable allowed the enable"; fi
if grep -q 'enable --now monit' "$D/gate"; then
  bad "the enable command was PRINTED while verify is RED — the operator would just run it"
else
  ok "the 'systemctl enable --now monit' line is NOT printed while verify is RED"
fi

rc="$(run_gate "$STUB_GREEN")"
if [ "$rc" -eq 0 ]; then ok "verify GREEN -> --gate-enable ALLOWS the enable (rc 0)"
else bad "verify GREEN but --gate-enable still refused:
$(cat "$D/gate")"; fi
if grep -q 'enable --now monit' "$D/gate"; then ok "the enable sequence IS printed once verify is GREEN"
else bad "verify GREEN but the enable sequence was never printed"; fi

rc="$(run_gate "$D/no-such-verify.sh")"
if [ "$rc" -ne 0 ]; then ok "FAIL-CLOSED: a MISSING verify script refuses the enable (rc $rc)"
else bad "a missing verify script was treated as a pass — fail-open"; fi

# The gate must run the FULL verify, not the hermetic --static-only subset (which cannot see a
# missing unit/script). A revert to --static-only here would silently gut the gate.
# shellcheck disable=SC2016  # matching the LITERAL source text of monit-selfwatch.sh
if grep -q 'bash "$VERIFY" --quiet' "$SELF" && ! grep -q 'static-only' "$SELF"; then
  ok "monit-selfwatch invokes the FULL verify (not the weaker --static-only mode)"
else
  bad "monit-selfwatch no longer invokes the full verify — the enable gate is gutted"
fi

echo
echo "== 8. FAIL-ON-REVERT: the REAL committed registry passes the static grammar =="
# Text-only, so it is CI-safe. Reverting ANY of the four restart_cmds to its broken seed value
# (relative path / ~ / systemctl --user / bare `ssh <alias> sudo ...`) turns this RED.
if bash "$VERIFY" --static-only >"$D/out" 2>&1; then
  ok "committed service-registry.tsv restart_cmds satisfy the root-context grammar"
else
  bad "committed service-registry.tsv has a restart_cmd that is NOT root-context safe:
$(cat "$D/out")"
fi

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL VERIFY-RESTART-CMDS TESTS PASS"
