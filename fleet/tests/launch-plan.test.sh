#!/usr/bin/env bash
# launch-plan.test.sh — FAIL-ON-REVERT tests for fleet/launch-plan.sh
# (fleet/board/LAUNCH-PLAN-GATE.md accept block). Hermetic: fixture board/state dirs + a
# stubbed assign.py; no network; never touches the live board/state.
set -uo pipefail
HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"   # fleet/
TMP="$(mktemp -d)"
trap 'rm -rf "$TMP"' EXIT

fail=0
ok(){ printf '  PASS: %s\n' "$*"; }
bad(){ printf '  FAIL: %s\n' "$*"; fail=1; }

# ---------------------------------------------------------------------------
# fixtures
# ---------------------------------------------------------------------------
BOARD="$TMP/board"; STATE="$TMP/state"
mkdir -p "$BOARD" "$STATE/done" "$STATE/claims" "$STATE/submitted" "$STATE/needs-push" "$STATE/loop-guard"

# (a) splittable-undecomposed: difficulty>=3 (DIFF_MIN default), 2 owned surfaces, no
# decompose children, no serial_justified -> parallelizability-gate must FAIL it.
cat > "$BOARD/SPLIT-1.md" <<'EOF'
tier: strong
difficulty: 3
work_class: ci-infra
depends_on:
owns: fixtureA.txt, fixtureB.txt
accept: fixture ticket for the parallelizability gate.
EOF

# (b) a plain READY ticket that should plan with a NAMED model (no est_tokens -> pass-through).
cat > "$BOARD/READY-1.md" <<'EOF'
tier: economy
difficulty: 1
work_class: rig-meta
depends_on:
owns: fixtureC.txt
accept: fixture ticket, should plan with a named model.
EOF

# (c) a READY ticket whose assign.py-picked model's context cap is smaller than its est_tokens.
cat > "$BOARD/READY-CTX.md" <<'EOF'
tier: economy
difficulty: 1
work_class: rig-meta
depends_on:
owns: fixtureD.txt
est_tokens: 200000
accept: fixture ticket, context-fit filter should drop it.
EOF

# Stub assign.py — mimics the real CLI contract exactly (TICKET:/PICK:/REFUSED lines, exit
# 0 on a pick / 1 on refusal) so launch-plan.sh's parsing logic is exercised unmodified.
STUB_ASSIGN="$TMP/assign_stub.py"
cat > "$STUB_ASSIGN" <<'PYEOF'
import sys
tid = sys.argv[1] if len(sys.argv) > 1 else ""
print(f"TICKET: {tid}")
if tid == "READY-1":
    print("PICK: stub-model-small  (work_class=rig-meta)")
    print("  score=1.0")
    sys.exit(0)
if tid == "READY-CTX":
    print("PICK: stub-model-tiny  (work_class=rig-meta)")
    print("  score=1.0")
    sys.exit(0)
print("REFUSED — no eligible candidate (stub default)")
sys.exit(1)
PYEOF

# Context-cap fixture roster: stub-model-tiny has a cap way below READY-CTX's est_tokens;
# stub-model-small has no row (READY-1 must pass-through, not be false-dropped).
CONTEXT_TSV="$TMP/model-context.tsv"
cat > "$CONTEXT_TSV" <<'EOF'
# model	max_context
stub-model-tiny	8000
EOF

export LAUNCH_PLAN_BOARD="$BOARD"
export LAUNCH_PLAN_STATE="$STATE"
export LAUNCH_PLAN_ASSIGN_PY="$STUB_ASSIGN"
export LAUNCH_PLAN_CONTEXT_TSV="$CONTEXT_TSV"

echo "== (a) splittable-undecomposed ticket is REFUSED, not planned =="
out_a="$(bash "$HERE/launch-plan.sh" SPLIT-1 2>&1)"
if echo "$out_a" | grep -qE 'SPLIT-1[[:space:]]+.*model='; then
  bad "SPLIT-1 appears inside a Wave (should be REFUSED — splittable/undecomposed). Output:
$out_a"
else
  ok "SPLIT-1 does not appear inside any Wave"
fi
if echo "$out_a" | grep -qi 'SPLIT-1' && echo "$out_a" | grep -q 'decompose.sh SPLIT-1'; then
  ok "SPLIT-1 refusal points the operator at fleet/decompose.sh SPLIT-1"
else
  bad "SPLIT-1 refusal message missing / no decompose.sh pointer. Output:
$out_a"
fi

echo "== (b) a ticket plans with a NAMED model =="
out_b="$(bash "$HERE/launch-plan.sh" READY-1 2>&1)"
if echo "$out_b" | grep -qE 'READY-1[[:space:]]+.*model=stub-model-small'; then
  ok "READY-1 plans with the NAMED model stub-model-small"
else
  bad "READY-1 did not plan with the expected named model. Output:
$out_b"
fi

echo "== (c) a too-small-context model is filtered out =="
out_c="$(bash "$HERE/launch-plan.sh" READY-CTX 2>&1)"
if echo "$out_c" | grep -qE 'READY-CTX[[:space:]]+.*model=stub-model-tiny'; then
  bad "READY-CTX was planned despite an undersized context cap. Output:
$out_c"
else
  ok "READY-CTX not planned (context-fit filtered)"
fi
if echo "$out_c" | grep -qi 'CONTEXT-FIT' && echo "$out_c" | grep -q 'READY-CTX'; then
  ok "context-fit filter reason surfaced for READY-CTX"
else
  bad "no CONTEXT-FIT reason surfaced for READY-CTX. Output:
$out_c"
fi
if echo "$out_b" | grep -qi 'context-fit: no est_tokens declared'; then
  ok "READY-1 (no est_tokens) is correctly pass-through-noted, not dropped"
else
  bad "READY-1 missing the expected pass-through context-fit note"
fi

echo
if [ "$fail" -eq 0 ]; then
  echo "launch-plan.test.sh: ALL PASS"
  exit 0
else
  echo "launch-plan.test.sh: FAILURES ABOVE"
  exit 1
fi
