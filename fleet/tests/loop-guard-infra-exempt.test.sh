#!/usr/bin/env bash
# loop-guard-infra-exempt.test.sh — FAIL-ON-REVERT tests for the 2026-07-23
# INFRA-FAULT exemption in loop-guard.sh.
#
# Covers:
#   (a) record --reason=exhausted (infra fault) does NOT quarantine — the zero-commit
#       release is tracked but never triggers the quarantine threshold.
#   (b) record without --reason (genuine / backward-compat) STILL quarantines as before.
#   (c) record --reason=genuine STILL quarantines (explicit model-fault attribution).
#   (d) REVERT check: if the infra exemption is removed, the infra case wrongly
#       quarantines → test goes RED (fail-on-revert).
#   (e) list surfaces both quarantined and infra-tracked tickets (visibility).
#
# Every test runs in a TEMP fleet (copied scripts). It NEVER touches the live fleet/state.
#
# Run:  bash fleet/tests/loop-guard-infra-exempt.test.sh   (exit 0 = all pass, 1 = a failure)
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

echo "== (a) infra-fault zero-commit releases NEVER quarantine =="

# (a1) record --reason=exhausted: exit 0, no quarantine marker even after N>>threshold.
d="$(mk_fleet)"
rc=0; bash "$d/loop-guard.sh" record TICKET-A droidX --reason exhausted >/dev/null 2>&1 || rc=$?
check "a1-1 infra record exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-A" ] && bad "a1-2 no quarantine marker after infra-fault" || ok "a1-2 no quarantine marker after infra-fault"
# Multiple infra-fault releases still never quarantine.
for _ in $(seq 1 5); do
  bash "$d/loop-guard.sh" record TICKET-A droidX --reason exhausted >/dev/null 2>&1 || rc=$?
done
check "a1-3 6th infra record still exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-A" ] && bad "a1-4 still no quarantine marker after 6 infra-faults" || ok "a1-4 still no quarantine marker after 6 infra-faults"
# Infra counter file exists for observability.
[ -f "$d/state/loop-guard/infra/TICKET-A" ] && ok "a1-5 infra counter file exists" || bad "a1-5 infra counter file exists"
in="$(cat "$d/state/loop-guard/infra/TICKET-A" 2>/dev/null || echo 0)"
check "a1-6 infra counter reads 6" "${in:-0}" "6"
rm -rf "$d"

# (a2) Various infra reasons all skip quarantine (spot-check canonical forms).
for reason in infra infra-fault pool-exhausted all-exhausted pool-too-thin gateway-reset \
              red-board red-board-blocked-claim launcher-refused provider-exhausted \
              leg-fault provider-fault provider-side salvage-stash; do
  d="$(mk_fleet)"
  rc=0; bash "$d/loop-guard.sh" record TICKET-B droidX --reason "$reason" >/dev/null 2>&1 || rc=$?
  [ "$rc" = "0" ] || { bad "a2-$reason: rc=$rc expected 0"; }
  [ -e "$d/state/loop-guard/TICKET-B" ] && bad "a2-$reason: marker exists" || ok "a2-$reason: infra skipped quarantine"
  rm -rf "$d"
done

echo "== (b) genuine / no-reason zero-commit releases STILL quarantine =="

# (b1) No --reason (backward compat): 1st -> exit 0, 2nd -> exit 2 + quarantine marker.
d="$(mk_fleet)"
rc=0; bash "$d/loop-guard.sh" record TICKET-C droidX >/dev/null 2>&1 || rc=$?
check "b1-1 first genuine record exits 0" "$rc" "0"
[ -e "$d/state/loop-guard/TICKET-C" ] && bad "b1-2 no marker after 1st genuine" || ok "b1-2 no marker after 1st genuine"

rc=0; err="$(bash "$d/loop-guard.sh" record TICKET-C droidX 2>&1 >/dev/null)" || rc=$?
check "b1-3 second genuine record exits 2 (quarantined)" "$rc" "2"
[ -e "$d/state/loop-guard/TICKET-C" ] && ok "b1-4 quarantine marker written" || bad "b1-4 quarantine marker written"
case "$err" in *ESCALATION*) ok "b1-5 escalation line emitted";; *) bad "b1-5 escalation line emitted (got: $err)";; esac

# clear + re-verify.
bash "$d/loop-guard.sh" clear TICKET-C >/dev/null 2>&1
[ -e "$d/state/loop-guard/TICKET-C" ] && bad "b1-6 clear removes marker" || ok "b1-6 clear removes marker"
rm -rf "$d"

# (b2) --reason=genuine: behaves identically to no --reason (explicit attribution).
d="$(mk_fleet)"
bash "$d/loop-guard.sh" record TICKET-D droidX --reason genuine >/dev/null 2>&1
rc=0; bash "$d/loop-guard.sh" record TICKET-D droidX --reason genuine >/dev/null 2>&1 || rc=$?
check "b2 --reason=genuine quarantines on 2nd" "$rc" "2"
[ -e "$d/state/loop-guard/TICKET-D" ] && ok "b2 quarantine marker exists" || bad "b2 quarantine marker exists"
rm -rf "$d"

# (b3) --reason=ticket-fault and --reason=model-fault also quarantine.
for reason in ticket-fault model-fault; do
  d="$(mk_fleet)"
  bash "$d/loop-guard.sh" record TICKET-E droidX --reason "$reason" >/dev/null 2>&1
  rc=0; bash "$d/loop-guard.sh" record TICKET-E droidX --reason "$reason" >/dev/null 2>&1 || rc=$?
  check "b3-$reason quarantines on 2nd" "$rc" "2"
  rm -rf "$d"
done

echo "== (c) list surfaces quarantined AND infra-tracked tickets =="

d="$(mk_fleet)"
# Quarantine one ticket.
bash "$d/loop-guard.sh" record Q1 droidX >/dev/null 2>&1
bash "$d/loop-guard.sh" record Q1 droidX >/dev/null 2>&1 || true
# Infra-track another.
bash "$d/loop-guard.sh" record I1 droidX --reason exhausted >/dev/null 2>&1
bash "$d/loop-guard.sh" record I1 droidX --reason exhausted >/dev/null 2>&1

out="$(bash "$d/loop-guard.sh" list 2>/dev/null)" || true
case "$out" in *QUARANTINED*Q1*) ok "c1 list shows quarantined Q1";; *) bad "c1 list shows quarantined Q1 (got: $out)";; esac
case "$out" in *INFRA-RETRY*I1*) ok "c2 list shows infra-tracked I1";; *) bad "c2 list shows infra-tracked I1 (got: $out)";; esac
case "$out" in *"1 quarantined"*) ok "c3 list reports 1 quarantined";; *) bad "c3 list reports 1 quarantined (got: $out)";; esac
case "$out" in *"1 infra-tracked"*) ok "c4 list reports 1 infra-tracked";; *) bad "c4 list reports 1 infra-tracked (got: $out)";; esac
rm -rf "$d"

echo "== (d) FAIL-ON-REVERT: if infra exemption removed, test goes RED =="

# d1 — infra fault wrongly quarantines if the exemption is reverted.
# Simulate revert by using a SECOND copy of loop-guard.sh with the infra check
# removed. We assert that the INFRA case WILL quarantine under the reverted code.
d="$(mk_fleet)"
# Copy the real loop-guard.sh and then surgically neuter the infra check.
# Remove the entire `if [ -n "$reason" ] && infra_reason "$reason"; then` block
# so every record counts toward quarantine regardless of reason.
sed '/infra_reason.*then/,/^    fi$/d' "$SRC/loop-guard.sh" > "$d/loop-guard_reverted.sh"
chmod +x "$d/loop-guard_reverted.sh"
# With the revert: --reason=exhausted should now count toward quarantine.
rc=0; bash "$d/loop-guard_reverted.sh" record R-TICKET droidX --reason exhausted >/dev/null 2>&1 || rc=$?
rc=0; bash "$d/loop-guard_reverted.sh" record R-TICKET droidX --reason exhausted >/dev/null 2>&1 || rc=$?
check "d1 revert: infra fault wrongly quarantines on 2nd" "$rc" "2"
[ -e "$d/state/loop-guard/R-TICKET" ] && ok "d1 revert: quarantine marker exists (reverted behavior)" || bad "d1 revert: quarantine marker exists"
rm -rf "$d"

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL LOOP-GUARD-INFRA-EXEMPT TESTS PASS"
