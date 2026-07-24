#!/usr/bin/env bash
# stuck-ticket-loud.test.sh — FAIL-ON-REVERT tests for the stuck-ticket-loud detector.
#
# THE BUG (2026-07-23 deadlock RCA): a P0 keystone ticket was loop-guard-quarantined
# ("repeated zero-commit re-claims") and NOTHING was loud about it — the pool went dry.
# This test proves the detector IS load-bearing: it seeds quarantined/parked/dep-dissolved/
# orphan-marker fixtures and asserts the check is RED; neuter the core logic and it flips
# GREEN — confirming the check carries the LOUD signal.
#
# HERMETIC: builds throwaway fixtures under mktemp -d. NEVER touches the live board,
# live state, or product repo.
#
# Run:  bash fleet/tests/stuck-ticket-loud.test.sh   (exit 0 = all pass, 1 = failure)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # the real fleet/ dir
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# Run the stuck-ticket-loud check against a temp fleet and capture exit code + stdout.
run_check(){
  local fleet_dir="$1"; shift
  STL_FLEET_DIR="$fleet_dir" STL_QUIET=1 STL_LIMIT=0 \
    bash "$SRC/checks/stuck-ticket-loud.sh" "$@" 2>&1
}

# Build an isolated temp fleet with synthetic board + state.
# Args: arbitrary number of "<id> <tier> <extra-yaml>"-tuples for board ticket content.
build_fleet(){
  local d; d="$(mktemp -d)"
  mkdir -p "$d/board" "$d/board/archive" \
           "$d/state/claims" "$d/state/submitted" "$d/state/done" \
           "$d/state/needs-push" "$d/state/loop-guard" "$d/checks"
  cp "$SRC/checks/stuck-ticket-loud.sh" "$d/checks/"
  printf '%s\n' "$d"
}

mk_ticket(){
  local d="$1" id="$2" tier="$3"; shift 3
  {
    printf 'tier: %s\nbranch: feat/%s\n' "$tier" "$(echo "$id" | tr 'A-Z' 'a-z')"
    printf 'depends_on:\ndifficulty: 1\n'
    while [ $# -gt 0 ]; do printf '%s\n' "$1"; shift; done
  } > "$d/board/$id.md"
}

# Write a quarantine marker in loop-guard format (matching loop-guard.sh::record).
mk_quarantine(){
  local d="$1" id="$2" droid="${3:-droid-test}" thresh="${4:-2}"
  printf 'droid=%s\ncount=%s\nthreshold=%s\nquarantined=%s\nreason=repeated zero-commit re-claims (claim->no-op->release spin)\n' \
    "$droid" "$thresh" "$thresh" "$(date -u +%FT%TZ)" > "$d/state/loop-guard/$id"
}

echo "=== stuck-ticket-loud: fail-on-revert tests ==="

# ── t1: clean board — GREEN ─────────────────────────────────────────────────────────────
echo "--- t1: clean board ---"
d="$(build_fleet)"
mk_ticket "$d" "READY-A" "sonnet"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t1 clean board exits 0" || bad "t1 clean board exits $rc (expected 0)"
# Quiet mode: output is empty for clean (no STUCK lines). Confirm no STUCK text.
case "$out" in *"STUCK"*) bad "t1 clean had STUCK text: $out" ;; *) ok "t1 clean board: no STUCK lines" ;; esac
rm -rf "$d"

# ── t2: quarantined ticket — RED ────────────────────────────────────────────────────────
echo "--- t2: quarantined ticket ---"
d="$(build_fleet)"
mk_ticket "$d" "QA-QTICKET" "frontier"
mk_quarantine "$d" "QA-QTICKET"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t2 quarantined ticket exits 1" || bad "t2 quarantined ticket exits $rc (expected 1)"
case "$out" in *"STUCK[quarantined]"*"QA-QTICKET"*) ok "t2 STUCK[quarantined] emitted" ;; *) bad "t2 STUCK[quarantined] not found in: $out" ;; esac
case "$out" in *"LOOP-GUARD QUARANTINED"*) ok "t2 escalation message present" ;; *) bad "t2 escalation message missing" ;; esac
rm -rf "$d"

# ── t3: parked ticket — RED ─────────────────────────────────────────────────────────────
echo "--- t3: parked ticket ---"
d="$(build_fleet)"
mk_ticket "$d" "PK-TICKET" "sonnet" "parked: operator-led DEEP-DIVE — do not route"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t3 parked exits 1" || bad "t3 parked exits $rc (expected 1)"
case "$out" in *"STUCK[parked]"*"PK-TICKET"*) ok "t3 STUCK[parked] emitted" ;; *) bad "t3 STUCK[parked] not found in: $out" ;; esac
rm -rf "$d"

# ── t4: dep-dissolved — RED ─────────────────────────────────────────────────────────────
echo "--- t4: dep-dissolved ---"
d="$(build_fleet)"
mk_ticket "$d" "BROKEN-TICKET" "sonnet" "depends_on: GHOST-DEP"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t4 dep-dissolved exits 1" || bad "t4 dep-dissolved exits $rc (expected 1)"
case "$out" in *"STUCK[dep-dissolved]"*"BROKEN-TICKET"*"GHOST-DEP"*) ok "t4 STUCK[dep-dissolved] emitted with ghost dep" ;; *) bad "t4 STUCK[dep-dissolved] missing or wrong dep name: $out" ;; esac
rm -rf "$d"

# ── t5: orphan-marker — RED ─────────────────────────────────────────────────────────────
echo "--- t5: orphan-marker (claim) ---"
d="$(build_fleet)"
touch "$d/state/claims/NO-BOARD-TICKET"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t5 orphan-marker (claims) exits 1" || bad "t5 orphan-marker exits $rc (expected 1)"
case "$out" in *"STUCK[orphan-marker]"*"NO-BOARD-TICKET"*) ok "t5 STUCK[orphan-marker] emitted for claimed orphan" ;; *) bad "t5 STUCK[orphan-marker] missing: $out" ;; esac
rm -rf "$d"

# ── t6: orphan-marker (submitted) — RED ─────────────────────────────────────────────────
echo "--- t6: orphan-marker (submitted) ---"
d="$(build_fleet)"
touch "$d/state/submitted/SUBMIT-ORPHAN"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t6 orphan-marker (submitted) exits 1" || bad "t6 orphan-marker exits $rc (expected 1)"
case "$out" in *"STUCK[orphan-marker]"*"SUBMIT-ORPHAN"*) ok "t6 STUCK[orphan-marker] for submitted orphan" ;; *) bad "t6 missing: $out" ;; esac
rm -rf "$d"

# ── t7: orphan-marker (needs-push) — RED ────────────────────────────────────────────────
echo "--- t7: orphan-marker (needs-push) ---"
d="$(build_fleet)"
touch "$d/state/needs-push/PUSH-ORPHAN"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t7 orphan (needs-push) exits 1" || bad "t7 exits $rc (expected 1)"
case "$out" in *"STUCK[orphan-marker]"*"PUSH-ORPHAN"*) ok "t7 STUCK[orphan-marker] for push orphan" ;; *) bad "t7 missing: $out" ;; esac
rm -rf "$d"

# ── t8: quarantined but done — GREEN (false alarm not raised) ──────────────────────────
echo "--- t8: quarantined but already done ---"
d="$(build_fleet)"
mk_ticket "$d" "DONE-QQ" "sonnet"
mk_quarantine "$d" "DONE-QQ"
touch "$d/state/done/DONE-QQ"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t8 quarantined-but-done exits 0" || bad "t8 exits $rc (expected 0 — done = not stuck)"
case "$out" in *"STUCK"*) bad "t8 false STUCK on done ticket: $out" ;; *) ok "t8 no STUCK on done ticket" ;; esac
rm -rf "$d"

# ── t9: quarantined but submitted — GREEN ──────────────────────────────────────────────
echo "--- t9: quarantined but already submitted ---"
d="$(build_fleet)"
mk_ticket "$d" "SUBMIT-QQ" "sonnet"
mk_quarantine "$d" "SUBMIT-QQ"
touch "$d/state/submitted/SUBMIT-QQ"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t9 quarantined-but-submitted exits 0" || bad "t9 exits $rc (expected 0)"
case "$out" in *"STUCK"*) bad "t9 false STUCK on submitted ticket: $out" ;; *) ok "t9 no STUCK on submitted" ;; esac
rm -rf "$d"

# ── t10: parked but done — GREEN ────────────────────────────────────────────────────────
echo "--- t10: parked but done ---"
d="$(build_fleet)"
mk_ticket "$d" "DONE-PK" "sonnet" "parked: true"
touch "$d/state/done/DONE-PK"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t10 parked-but-done exits 0" || bad "t10 exits $rc (expected 0)"
rm -rf "$d"

# ── t11: quarantined with no board file — GREEN (orphaned quarantine, not stuck) ──────
echo "--- t11: quarantine marker without board file ---"
d="$(build_fleet)"
mk_quarantine "$d" "GONE-ALREADY"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t11 quarantined-no-board exits 0" || bad "t11 exits $rc (expected 0 — no board to be stuck)"
case "$out" in *"STUCK"*) bad "t11 false STUCK on marker with no board: $out" ;; *) ok "t11 no STUCK without board" ;; esac
rm -rf "$d"

# ── t12: dep-dissolved but dep already done — GREEN ─────────────────────────────────────
echo "--- t12: dep-dissolved but dep done ---"
d="$(build_fleet)"
mk_ticket "$d" "WAITING-TICK" "sonnet" "depends_on: NOW-DONE"
touch "$d/state/done/NOW-DONE"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t12 dep-done exits 0" || bad "t12 exits $rc (expected 0)"
case "$out" in *"STUCK"*) bad "t12 false STUCK on dep-is-done: $out" ;; *) ok "t12 no STUCK when dep is done" ;; esac
rm -rf "$d"

# ── t13: FAIL-ON-REVERT — neuter the quarantine scan, assert GREEN flips ─────────────────
echo "--- t13: fail-on-revert (neuter quarantine detection) ---"
d="$(build_fleet)"
mk_ticket "$d" "REVERT-TEST" "frontier"
mk_quarantine "$d" "REVERT-TEST"

# Sanity: before neutering, the check IS RED.
out_before="$(run_check "$d")"; rc_before=$?
[ "$rc_before" -eq 1 ] && ok "t13a pre-neuter: exits 1 (RED)" || bad "t13a pre-neuter exits $rc_before (expected 1)"
case "$out_before" in *"STUCK[quarantined]"*"REVERT-TEST"*) ok "t13b pre-neuter: STUCK[quarantined] present" ;; *) bad "t13b pre-neuter: STUCK missing: $out_before" ;; esac

# Neuter: delete the quarantine check function's body so it always returns 0 findings.
# We replace the scan_quarantined function — make it a no-op.
neutered="$d/checks/stuck-ticket-loud.sh.neutered"
sed 's/^scan_quarantined(){$/scan_quarantined(){ return 0; # NEUTERED/' \
  "$d/checks/stuck-ticket-loud.sh" > "$neutered"
chmod +x "$neutered"

out_after="$(STL_FLEET_DIR="$d" STL_QUIET=1 STL_LIMIT=0 bash "$neutered" 2>&1)"; rc_after=$?
[ "$rc_after" -eq 0 ] && ok "t13c neutered: exits 0 (GREEN — proves check was load-bearing)" \
  || bad "t13c neutered exits $rc_after (expected 0 — the check should have been neutered)"
case "$out_after" in *"STUCK[quarantined]"*) bad "t13d neutered: STUCK[quarantined] STILL present (neuter failed): $out_after" ;; *) ok "t13d neutered: STUCK[quarantined] gone" ;; esac
rm -rf "$d"

# ── t14: non-quarantine files in loop-guard/ do NOT false-positive ──────────────────────
echo "--- t14: non-quarantine files in loop-guard dir ignored ---"
d="$(build_fleet)"
mk_ticket "$d" "REAL-TICK" "sonnet"
# Write a file that does NOT look like a quarantine marker (no "droid=" header).
printf 'some other state\nnot a quarantine\n' > "$d/state/loop-guard/OTHER-STATE"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 0 ] && ok "t14 non-quarantine file in LG dir exits 0" || bad "t14 exits $rc (expected 0)"
case "$out" in *"STUCK"*) bad "t14 false STUCK from non-quarantine LG file: $out" ;; *) ok "t14 no false STUCK" ;; esac
rm -rf "$d"

# ── t15: mixed board — all four categories surface independently ────────────────────────
echo "--- t15: mixed board — all four categories ---"
d="$(build_fleet)"
mk_ticket "$d" "QUARANTINED-ONE" "frontier"
mk_quarantine "$d" "QUARANTINED-ONE"
mk_ticket "$d" "PARKED-ONE" "sonnet" "parked: operator hold for investigation"
mk_ticket "$d" "DEP-BROKEN-ONE" "sonnet" "depends_on: MISSING-DEP"
touch "$d/state/claims/ORPHAN-CLAIM"
out="$(run_check "$d")"; rc=$?
[ "$rc" -eq 1 ] && ok "t15 mixed board exits 1" || bad "t15 exits $rc (expected 1)"
case "$out" in *"STUCK[quarantined]"*) ok "t15 quarantined surfaced" ;; *) bad "t15 quarantined missing: $out" ;; esac
case "$out" in *"STUCK[parked]"*) ok "t15 parked surfaced" ;; *) bad "t15 parked missing: $out" ;; esac
case "$out" in *"STUCK[dep-dissolved]"*) ok "t15 dep-dissolved surfaced" ;; *) bad "t15 dep-dissolved missing: $out" ;; esac
case "$out" in *"STUCK[orphan-marker]"*) ok "t15 orphan-marker surfaced" ;; *) bad "t15 orphan-marker missing: $out" ;; esac
count="$(printf '%s\n' "$out" | grep -c '^STUCK\[')"
[ "$count" -eq 4 ] && ok "t15 exactly 4 STUCK lines (all four categories)" || bad "t15 got $count STUCK lines (expected 4)"
rm -rf "$d"

# ── t16: validate_board.sh GREEN on the live board ────────────────────────────────────
echo "--- t16: validate_board.sh must be GREEN ---"
out="$(bash "$SRC/validate_board.sh" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] && ok "t16 validate_board.sh is GREEN (exit 0)" \
  || bad "t16 validate_board.sh RED (exit $rc) — fix board hygiene first. Output:\n$(printf '%s\n' "$out" | tail -20)"
rm -f /tmp/stuck_test_out

echo
echo "--- $PASS passed, $FAIL failed ---"
[ "$FAIL" -eq 0 ] || exit 1
echo "ALL STUCK-TICKET-LOUD TESTS PASS"
