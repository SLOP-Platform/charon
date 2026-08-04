#!/usr/bin/env bash
# lifecycle-enforce.test.sh — RED-PROOF / fail-on-revert suite for
# fleet/checks/lifecycle-enforce.sh, the LIFECYCLE-ENFORCEMENT gate.
#
# The gate's job is "nothing in the system BLOCKS on an unfinished commitment"
# (D-003). The suite proves each BUILT edge actually fires, and proves the gate
# actually goes RED when its own guard is reverted.
#
# Fail-on-revert: every assertion runs the REAL gate against a REAL synthetic tree
# on disk (LIFECYCLE_ROOT seam). Reverting the named clause of lifecycle-enforce.sh
# flips the corresponding case RED. Two tests go further and NEUTER the guard on a
# SCRATCHPAD COPY of the gate and assert the copy now passes a violating tree —
# the suite catches a reverted enforcer even when the guard's mere existence is
# what was deleted.
#
# Hermetic: mktemp -d only (sandbox-contained). No network, no gh, no git writes to
# any real repo, no dependency on fleet/state/ (passes from a fresh checkout).
#
# Run:  bash fleet/tests/lifecycle-enforce.test.sh   (exit 0 = all pass)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
GATE="${HERE}/fleet/checks/lifecycle-enforce.sh"
PASS=0
FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   ${*}"; }
bad(){ FAIL=$((FAIL+1)); echo "  FAIL ${*}"; }
rc_ok(){
  if [[ "${2}" -eq "${3}" ]]; then ok "${1}"; else bad "${1} (want rc=${3}, got rc=${2})"; fi
}
has(){
  if printf '%s' "${2}" | grep -qF "${3}"; then ok "${1}"; else bad "${1} (output lacked '${3}')"; fi
}

# shellcheck source=fleet/tests/lib/sandbox.sh
. "${HERE}/fleet/tests/lib/sandbox.sh"
sandbox_init

ROOT="$(sandbox_mk lifecycle-enforce-test)"
trap 'rm -rf "${ROOT}"' EXIT

# ---- fixture helpers ----------------------------------------------------------------
# fixture <name> — a fresh isolated tree with the estate layout.
fixture(){
  local d="${ROOT}/${1}"
  mkdir -p "${d}/docs/review-log" "${d}/fleet/board" "${d}/fleet/board/archive" "${d}/fleet/state"
  printf '%s\n' "${d}"
}
# ticket <root> <id> [parked] — a minimal board ticket file.
ticket(){
  {
    echo 'repo: charon'
    echo 'branch: feat/x'
    echo 'owns: a.sh'
    if [[ "${3:-}" = parked ]]; then echo 'parked: true'; fi
  } > "${1}/fleet/board/${2}.md"
}
# fragment <root> <name> <body> — a docs/review-log fragment.
fragment(){ printf '%s\n' "${3}" > "${1}/docs/review-log/${2}"; }
# verdict <root> <name> <verdict-line> — a fragment whose verdict is on the next line.
verdict(){ fragment "${1}" "${2}" "# Review
## Verdict
${3}"; }
# run_gate <root> — runs the real gate; echoes its rc into $GATE_RC.
run_gate(){
  local out
  out="$(LIFECYCLE_ROOT="${1}" bash "${GATE}" check 2>&1)"
  GATE_RC=$?
  GATE_OUT="${out}"
}

echo "=== 1. enforcer exists and is a readable script (file-level revert = suite RED) ==="
if [[ -f "${GATE}" ]] && [[ -r "${GATE}" ]]; then
  ok "gate file present and readable"
else
  bad "gate file missing — if lifecycle-enforce.sh is reverted/deleted, this suite must go RED"
fi

echo "=== 2. POSITIVE CONTROL: clean tree is GREEN (gate is not a greying exercise) ==="
C="$(fixture clean)"
ticket "${C}" FIX-ONE
verdict "${C}" FIX-ONE.md "ADOPT the whole thing"
run_gate "${C}"; rc_ok "clean tree GREEN" "${GATE_RC}" 0

echo "=== 3. E3 core: ADOPT verdict with no minted ticket -> RED ==="
L="$(fixture lonely)"
ticket "${L}" FIX-ONE
verdict "${L}" FIX-ONE.md "ADOPT the whole thing"
fragment "${L}" LONELY.md "## Decision: ADOPT something without a ticket"
run_gate "${L}"; rc_ok "LONELY ADOPT without a ticket REDs" "${GATE_RC}" 1
has  "E3 names the fragment" "${GATE_OUT}" "LONELY.md"
has  "E3 names the verdict edge" "${GATE_OUT}" "E3"

echo "=== 4. E3 core: REJECT verdict with no minted ticket -> RED ==="
R="$(fixture reject)"
ticket "${R}" FIX-ONE
verdict "${R}" FIX-ONE.md "ADOPT the whole thing"
verdict "${R}" NOPE.md "REJECT"
run_gate "${R}"; rc_ok "REJECT without a ticket REDs" "${GATE_RC}" 1
has  "E3 names NOPE.md" "${GATE_OUT}" "NOPE.md"

echo "=== 5. E3: ## Decision: ADOPT ... line-form verdict; fname ref turns it GREEN ==="
D="$(fixture decision)"
ticket "${D}" FIX-ONE
fragment "${D}" SOMETHING.md "## Decision: ADOPT some_tool (long form)"
run_gate "${D}"; rc_ok "decision-line ADOPT without a ticket REDs" "${GATE_RC}" 1
mv "${D}/docs/review-log/SOMETHING.md" "${D}/docs/review-log/FIX-ONE.md"
run_gate "${D}"; rc_ok "same fragment renamed to its board ticket is GREEN" "${GATE_RC}" 0

echo "=== 6. E3: a Ticket-line reference satisfies the minted-ticket rule ==="
T="$(fixture ticketline)"
ticket "${T}" FIX-ONE
fragment "${T}" UNNAMED.md "# Review
**Ticket:** FIX-ONE — tracked here
## Verdict
ADOPT"
run_gate "${T}"; rc_ok "Ticket-line ref GREEN" "${GATE_RC}" 0

echo "=== 7. E3: a prose token naming a board ticket satisfies the rule ==="
P="$(fixture prose-ref)"
ticket "${P}" FIX-ONE
fragment "${P}" OTHER.md "# Review
This adopts the plan tracked in FIX-ONE.
## Verdict
ADOPT"
run_gate "${P}"; rc_ok "prose reference to a minted ticket GREEN" "${GATE_RC}" 0

echo "=== 8. E3: a reference to an ARCHIVED board ticket is still a minted ticket ==="
A="$(fixture archive-ref)"
ticket "${A}" FIX-ONE
{
  echo 'repo: charon'
  echo 'branch: feat/x'
  echo 'owns: a.sh'
} > "${A}/fleet/board/archive/OLD-EVAL.md"
verdict "${A}" OLD-EVAL.md "ADOPT (this commit)"
run_gate "${A}"; rc_ok "archive-ticket ref GREEN" "${GATE_RC}" 0

echo "=== 9. E3: ordinary prose using the verbs adopt/reject is NOT a verdict ==="
Q="$(fixture prose)"
ticket "${Q}" FIX-ONE
fragment "${Q}" NOTE.md "# Note
We will adopt the merge queue and reject the old tooling after the audit."
run_gate "${Q}"; rc_ok "prose-only GREEN (no false verdict)" "${GATE_RC}" 0

echo "=== 10. E3: a NEGATED adoption statement is not an ADOPT verdict ==="
N="$(fixture negation)"
ticket "${N}" FIX-ONE
fragment "${N}" SKIP.md "## Decision: DO NOT ADOPT heavy_tool"
run_gate "${N}"; rc_ok "negation GREEN (not a verdict)" "${GATE_RC}" 0

echo "=== 11. E3: a PR-numbered fragment with an ADOPT verdict and no Ticket line REDs (D-007) ==="
B="$(fixture prnum)"
ticket "${B}" FIX-ONE
verdict "${B}" 99@charon.md "ADOPT"
run_gate "${B}"; rc_ok "PR-numbered ADOPT without a Ticket line REDs" "${GATE_RC}" 1
has  "E3 names the PR fragment" "${GATE_OUT}" "99@charon.md"

echo "=== 12. E1 core: an open ASKED row's Blocks field naming a LIVE ticket -> RED ==="
E1="$(fixture e1-live)"
ticket "${E1}" FOO-BAR
cat > "${E1}/fleet/state/DECISIONS.md" <<'EOF'
# DECISIONS
## ASKED — open, and what each one BLOCKS
### Q-099 · THE OPERATOR MUST DECIDE X · asked 2026-08-04
**BLOCKS:** FOO-BAR.
Nothing else.
EOF
run_gate "${E1}"; rc_ok "live ticket named by an open ASKED row REDs" "${GATE_RC}" 1
has  "E1 names the ticket" "${GATE_OUT}" "FOO-BAR"
has  "E1 names the edge" "${GATE_OUT}" "E1"

echo "=== 13. E1: a PARKED ticket is not active work -> not blocked -> GREEN ==="
E1p="$(fixture e1-parked)"
ticket "${E1p}" PARKED-TICKET parked
cat > "${E1p}/fleet/state/DECISIONS.md" <<'EOF'
## ASKED — open, and what each one BLOCKS
### Q-099 · THE OPERATOR MUST DECIDE X · asked 2026-08-04
**BLOCKS:** PARKED-TICKET.
EOF
run_gate "${E1p}"; rc_ok "parked ticket not blocked (GREEN)" "${GATE_RC}" 0

echo "=== 14. E1: a Blocks value that is prose, not a ticket id, is skipped ==="
E1q="$(fixture e1-prose)"
ticket "${E1q}" FOO-BAR
cat > "${E1q}/fleet/state/DECISIONS.md" <<'EOF'
## ASKED — open, and what each one BLOCKS
### Q-099 · THE OPERATOR MUST DECIDE X · asked 2026-08-04
**BLOCKS:** `require_code_owner_reviews`, the whole programme (D-001..D-004).
EOF
run_gate "${E1q}"; rc_ok "prose-only Blocks value GREEN" "${GATE_RC}" 0

echo "=== 15. E1: an ASKED row with no Blocks marker is not read -> GREEN ==="
E1m="$(fixture e1-nomarker)"
ticket "${E1m}" FOO-BAR
cat > "${E1m}/fleet/state/DECISIONS.md" <<'EOF'
## ASKED — open, and what each one BLOCKS
### Q-099 · THE OPERATOR MUST DECIDE X · asked 2026-08-04
No Blocks field in this row.
EOF
run_gate "${E1m}"; rc_ok "no-Blocks-marker row GREEN" "${GATE_RC}" 0

echo "=== 16. E1: a CLOSED/ANSWERED ASKED row does not block ==="
E1c="$(fixture e1-closed)"
ticket "${E1c}" FOO-BAR
cat > "${E1c}/fleet/state/DECISIONS.md" <<'EOF'
## ASKED — open, and what each one BLOCKS
### Q-001 · [CLOSED — see D-010] Old lane question · asked 2026-08-03
**Blocks:** FOO-BAR.
EOF
run_gate "${E1c}"; rc_ok "closed ASKED row does not block (GREEN)" "${GATE_RC}" 0

echo "=== 17. E1: a ticket that only exists in archive is not live -> not blocked ==="
E1a="$(fixture e1-archive)"
{
  echo 'repo: charon'
  echo 'branch: feat/x'
  echo 'owns: a.sh'
} > "${E1a}/fleet/board/archive/RETIRED-ONE.md"
cat > "${E1a}/fleet/state/DECISIONS.md" <<'EOF'
## ASKED — open, and what each one BLOCKS
### Q-099 · THE OPERATOR MUST DECIDE X · asked 2026-08-04
**BLOCKS:** RETIRED-ONE.
EOF
run_gate "${E1a}"; rc_ok "archive-only ticket not blocked (GREEN)" "${GATE_RC}" 0

echo "=== 18. 'edges' prints the built/not-built statement (acceptance d) ==="
OUT_E="$(bash "${GATE}" edges)"
rc_ok "edges exits 0" "$?" 0
has  "E1 BUILT" "${OUT_E}" "E1 ASKED-BLOCKS-TICKET: BUILT"
has  "E3 BUILT" "${OUT_E}" "E3 VERDICT-WITHOUT-TICKET: BUILT"
has  "E2 NOT-BUILT stated" "${OUT_E}" "E2 DECIDED-CONTRADICTED: NOT-BUILT"
has  "E4 NOT-BUILT stated" "${OUT_E}" "E4 DONE-BACKED-BY-EVIDENCE: NOT-BUILT"
has  "E5 NOT-BUILT stated" "${OUT_E}" "E5 OUT-OF-BAND-NOTIFY: NOT-BUILT"

echo "=== 19. usage: an unknown command exits 2 ==="
bash "${GATE}" bogus >/dev/null 2>&1; rc_ok "unknown command rc=2" "$?" 2

echo "=== 20. FAIL-ON-REVERT (E3): neuter the minted-ticket guard on a copy -> the copy GREENs a violating tree ==="
CP="$(sandbox_mk lifecycle-enforce-neuter)"
cp "${GATE}" "${CP}/lifecycle-enforce.sh"
sed -i 's/^        if not refs_minted_ticket(base, body, board):$/        if False:/' "${CP}/lifecycle-enforce.sh"
grep -q "if False:" "${CP}/lifecycle-enforce.sh" || bad "neuter sed did not apply"
LIFECYCLE_ROOT="${L}" bash "${CP}/lifecycle-enforce.sh" check >/dev/null 2>&1
rc_ok "neutered E3 guard passes the violating tree (suite would catch the revert)" "$?" 0

echo "=== 21. FAIL-ON-REVERT (E1): neuter the ASKED-row detector on a copy -> the copy GREENs a blocked tree ==="
CP1="$(sandbox_mk lifecycle-enforce-neuter1)"
cp "${GATE}" "${CP1}/lifecycle-enforce.sh"
sed -i 's/^        bm = re.search(.*$/        bm = None/' "${CP1}/lifecycle-enforce.sh"
grep -q "bm = None" "${CP1}/lifecycle-enforce.sh" || bad "neuter sed did not apply"
LIFECYCLE_ROOT="${E1}" bash "${CP1}/lifecycle-enforce.sh" check >/dev/null 2>&1
rc_ok "neutered E1 guard passes the blocked tree (suite would catch the revert)" "$?" 0

echo ""
echo "lifecycle-enforce.test.sh: ${PASS} passed, ${FAIL} failed"
if [[ "${FAIL}" -eq 0 ]]; then exit 0; else exit 1; fi
