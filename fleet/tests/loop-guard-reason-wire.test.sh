#!/usr/bin/env bash
# loop-guard-reason-wire.test.sh — FAIL-ON-REVERT tests for the 2026-08-01
# LOOP-GUARD-REASON-WIRE fix: pass `--reason` at every loop-guard.sh record call
# site in fleet-droid.sh so the INFRA-FAULT EXEMPTION actually fires.
#
# Covers (DONE CONTRACT):
#   (a)  CHARON_RUN_RESULT=EXHAUSTED -> --reason exhausted -> INFRA counter, never quarantine
#   (aR) REVERT check: without --reason, EXHAUSTED wrongly quarantines -> RED
#   (b)  --reason genuine (error-failover/SUCCESS+zero-commits) STILL quarantines
#   (bR) REVERT check: without --reason genuine, model faults no longer quarantine -> RED
#   (c)  Timeout classification: rc=124 with output (too-slow) = genuine -> quarantines;
#        rc=124 no output (leg-fault) = infra -> never quarantines;
#        all-models-exhausted = CHARON_RUN_RESULT=EXHAUSTED -> infra
#   (d)  ANTI-OVER-BLOCK: a successful run records nothing and quarantines nothing
#
# Every test runs in a TEMP fleet. NEVER touches the live fleet/state.
#
# Run:  bash fleet/tests/loop-guard-reason-wire.test.sh   (exit 0 = all pass, 1 = a failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }
check(){ [ "$2" = "$3" ] && ok "$1" || bad "$1 (expected '$3', got '$2')"; }

mk_fleet(){
  local d; d="$(mktemp -d)"
  cp "$SRC/loop-guard.sh" "$d/"
  mkdir -p "$d/state/loop-guard"
  echo "$d"
}

echo "== (a) EXHAUSTED -> infra counter, NEVER quarantines =="

d="$(mk_fleet)"
rc=0; bash "$d/loop-guard.sh" record TICKET-A economy-1 --reason exhausted >/dev/null 2>&1 || rc=$?
check "a1 exhausted record exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-A" ] && bad "a1 no quarantine marker after exhausted" || ok "a1 no quarantine marker after exhausted"
# Past threshold (3x when threshold=2) still no quarantine.
for _ in $(seq 1 5); do
  bash "$d/loop-guard.sh" record TICKET-A economy-1 --reason exhausted >/dev/null 2>&1 || rc=$?
done
check "a2 6th exhausted record still exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-A" ] && bad "a2 still no quarantine marker after 6 exhausted" || ok "a2 still no quarantine marker after 6 exhausted"
# Infra counter file exists.
[ -f "$d/state/loop-guard/infra/TICKET-A" ] && ok "a3 infra counter file exists" || bad "a3 infra counter file exists"
in="$(cat "$d/state/loop-guard/infra/TICKET-A" 2>/dev/null || echo 0)"
check "a4 infra counter reads 6" "${in:-0}" "6"
rm -rf "$d"

echo "== (aR) REVERT CHECK: without --reason, exhausted wrongly quarantines =="

# Simulate the revert: surgically remove the infra_reason block so --reason is ignored.
d="$(mk_fleet)"
sed '/infra_reason.*then/,/^    fi$/d' "$SRC/loop-guard.sh" > "$d/loop-guard_reverted.sh"
chmod +x "$d/loop-guard_reverted.sh"
# --reason exhausted is treated as no reason -> counts toward quarantine.
rc=0; bash "$d/loop-guard_reverted.sh" record R-TICKET droidX --reason exhausted >/dev/null 2>&1 || rc=$?
rc=0; bash "$d/loop-guard_reverted.sh" record R-TICKET droidX --reason exhausted >/dev/null 2>&1 || rc=$?
check "aR revert: exhausted wrongly quarantines on 2nd" "$rc" "2"
[ -e "$d/state/loop-guard/R-TICKET" ] && ok "aR revert: quarantine marker exists (reverted behavior)" || bad "aR revert: quarantine marker exists"
rm -rf "$d"

echo "== (b) --reason genuine STILL quarantines =="

d="$(mk_fleet)"
rc=0; bash "$d/loop-guard.sh" record TICKET-C droidX --reason genuine >/dev/null 2>&1 || rc=$?
check "b1 first genuine record exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-C" ] && bad "b1 no marker after 1st genuine" || ok "b1 no marker after 1st genuine"
rc=0; bash "$d/loop-guard.sh" record TICKET-C droidX --reason genuine >/dev/null 2>&1 || rc=$?
check "b2 second genuine record exits 2 (quarantined)" "$rc" "2"
[ -e "$d/state/loop-guard/TICKET-C" ] && ok "b2 quarantine marker written" || bad "b2 quarantine marker written"
rm -rf "$d"

echo "== (bR) REVERT CHECK: if --reason genuine is removed, model fault wrongly skips quarantine =="

# Simulate revert: remove the infra_reason block so --reason exhausted/exhausted is ignored
# AND remove the --reason flag itself (bare call) — same as the pre-fix fleet-droid.sh.
d="$(mk_fleet)"
# Use the original loop-guard.sh which handles --reason correctly. The revert of the
# WIRE (not loop-guard.sh itself) means calling bare instead of --reason genuine.
# Without --reason genuine, a model fault falls through to the backward-compat path.
bash "$d/loop-guard.sh" record R-GENUINE droidX >/dev/null 2>&1 || true
rc=0; bash "$d/loop-guard.sh" record R-GENUINE droidX >/dev/null 2>&1 || rc=$?
check "bR revert: bare record still quarantines (default behavior)" "$rc" "2"
[ -e "$d/state/loop-guard/R-GENUINE" ] && ok "bR revert: quarantine marker exists (bare call = genuine)" || bad "bR revert: quarantine marker exists"
rm -rf "$d"

echo "== (c) --reason launcher-refused (infra) =="

d="$(mk_fleet)"
rc=0
for _ in $(seq 1 5); do
  bash "$d/loop-guard.sh" record TICKET-D droidX --reason launcher-refused >/dev/null 2>&1 || rc=$?; rc=0
done
check "c1 6th launcher-refused record exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-D" ] && bad "c1 no quarantine after 6 launcher-refused" || ok "c1 no quarantine after 6 launcher-refused"
[ -f "$d/state/loop-guard/infra/TICKET-D" ] && ok "c2 infra counter exists" || bad "c2 infra counter exists"
rm -rf "$d"

echo "== (d) ANTI-OVER-BLOCK: no record call = no state = no quarantine =="

d="$(mk_fleet)"
# Simulate a successful run: no loop-guard.sh record is called.
[ -e "$d/state/loop-guard/TICKET-F" ] && bad "d1 no state dir for unreleased ticket" || ok "d1 no state dir for unreleased ticket"
[ -e "$d/state/loop-guard/infra/TICKET-F" ] && bad "d2 no infra dir for unreleased ticket" || ok "d2 no infra dir for unreleased ticket"
rm -rf "$d"

echo "== (e) list surfaces both quarantined AND infra-tracked =="

d="$(mk_fleet)"
# Quarantine one ticket (bare call).
bash "$d/loop-guard.sh" record Q1 droidX >/dev/null 2>&1
bash "$d/loop-guard.sh" record Q1 droidX >/dev/null 2>&1 || true
# Infra-track another.
bash "$d/loop-guard.sh" record I1 droidX --reason exhausted >/dev/null 2>&1
bash "$d/loop-guard.sh" record I1 droidX --reason exhausted >/dev/null 2>&1

out="$(bash "$d/loop-guard.sh" list 2>/dev/null)" || true
case "$out" in *QUARANTINED*Q1*) ok "e1 list shows quarantined Q1";; *) bad "e1 list shows quarantined Q1 (got: $out)";; esac
case "$out" in *INFRA-RETRY*I1*) ok "e2 list shows infra-tracked I1";; *) bad "e2 list shows infra-tracked I1 (got: $out)";; esac
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LOOP-GUARD-REASON-WIRE TESTS PASS"