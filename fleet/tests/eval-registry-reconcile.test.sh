#!/usr/bin/env bash
# eval-registry-reconcile.test.sh — FAIL-ON-REVERT tests for fleet/checks/eval-registry-reconcile.sh.
#
# RED-PROOF, one per drift class:
#   T1  D1 UNEVALUATED ADOPTION  — tool in inventory, NO verdict row -> RED
#   T2  D2 STALE ROW             — ADOPT verdict, tool absent from inventory -> RED
#   T3  D3 CONTRADICTION         — REJECT verdict, tool present in inventory -> RED
#
# ANTI-FALSE-POSITIVE:
#   T4  clean fixture -> ZERO findings, exit 0
#
# UNREADABLE-INPUT PROOF:
#   T5  missing registry -> non-zero exit, NOT "no drift"
#
# HERMETIC: all fixtures built under mktemp -d. No network. Inventory is generated from
#   fixture source files (gates.json, pyproject.toml, graph.json, TOOL-INVENTORY.md).
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
SCRIPT="$HERE/../checks/eval-registry-reconcile.sh"
PASS=0; FAIL=0
ok(){ PASS=$((PASS+1)); echo "  ok   $*"; }
no(){ FAIL=$((FAIL+1)); echo "  FAIL $*"; }
chk(){ case "$3" in *"$2"*) ok "$1";; *) no "$1 (missing: $2)";; esac; }
nchk(){ case "$3" in *"$2"*) no "$1 (unexpected: $2)";; *) ok "$1";; esac; }

TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
FLEETD="$TMP/fleet"; mkdir -p "$FLEETD/state"

# ── helper: run the reconciler against fixture source files ─────────────────────────
run_reconcile(){
  env ER_FLEET="$FLEETD" ER_PRODUCT="$TMP/product" \
      ER_REGISTRY="$FLEETD/state/EVAL-REGISTRY.md" \
      ER_INVENTORY="$FLEETD/state/EVAL-INVENTORY.tsv" \
      ER_GRAPH="$TMP/product/graphify-out/graph.json" \
      ER_GATES="$TMP/product/tools/gates.json" \
      ER_PYPTOML="$TMP/product/pyproject.toml" \
      ER_TOOLINV="$FLEETD/TOOL-INVENTORY.md" "$@" bash "$SCRIPT" 2>&1
}

# ── fixture: minimal EVAL-REGISTRY.md table ──────────────────────────────────────────
write_registry(){
  local content="$1"
  cat > "$FLEETD/state/EVAL-REGISTRY.md" <<EOF
# EVAL-REGISTRY — test fixture

| tool | scope | date | verdict | alignment | reason | evidence-link | supersedes |
|---|---|---|---|---|---|---|---|
$content
## Backfill note
EOF
}

# ── fixture: set up product sources for inventory generation ─────────────────────────
# The reconciler GENERATES inventory from these live sources (gates.json is the easiest
# to control — each gate ID becomes an inventory row).
init_product_dirs(){
  mkdir -p "$TMP/product/graphify-out" "$TMP/product/tools"
  echo '{"nodes":[]}' > "$TMP/product/graphify-out/graph.json"
  printf '[project]\ndependencies = []\n' > "$TMP/product/pyproject.toml"
  touch "$FLEETD/TOOL-INVENTORY.md"
}

# Write gates.json with the given gate IDs — each becomes an inventory tool entry.
write_gates(){
  local ids=("$@")
  {
    printf '[\n'
    local first=1
    for id in "${ids[@]}"; do
      [ -z "$id" ] && continue
      [ "$first" -eq 1 ] || printf ',\n'
      first=0
      printf '  {"id": "%s", "enforcer": "tools/check_%s.py"}' "$id" "$id"
    done
    printf '\n]\n'
  } > "$TMP/product/tools/gates.json"
}

init_product_dirs
write_gates  # empty gates → inventory only from other sources (all empty → 0 entries)

# ═══════════════════════════════════════════════════════════════════════════════════════
echo "== T1. D1: UNEVALUATED ADOPTION — tool in inventory, NO verdict row =="
# "uneval-tool" is a gate enforcer (in inventory), but has no registry row.
write_registry '| keep-tool | test scope | 2026-01-01 | ADOPT — shipped | aligned | fine | link | — |'
write_gates "uneval-tool" "keep-tool"

OUT="$(run_reconcile)"; RC=$?
chk "T1a detects D1"              "D1 UNEVALUATED ADOPTION" "$OUT"
chk "T1b names the tool"          "uneval-tool"             "$OUT"
[ "$RC" -ne 0 ] && ok "T1c exit non-zero on D1" || no "T1c exit non-zero on D1 (got $RC)"

# Fix: add the verdict row for uneval-tool. "keep-tool" is ADOPT and in inventory → OK.
# But we need to keep keep-tool in inventory too, so D2 does NOT fire for it.
write_registry '| keep-tool | test scope | 2026-01-01 | ADOPT — shipped | aligned | fine | link | — |
| uneval-tool | test scope | 2026-01-01 | ADOPT — shipped | aligned | now evaluated | link | — |'
OUT="$(run_reconcile)"; RC=$?
nchk "T1d D1 gone after fix"     "D1 UNEVALUATED ADOPTION" "$OUT"
nchk "T1e also no D2 on clean"   "D2 STALE ROW"           "$OUT"
[ "$RC" -eq 0 ] && ok "T1f clean exit 0 after fix" || no "T1f clean exit 0 after fix (got $RC)"

echo "== T2. D2: STALE ROW — ADOPT verdict, tool ABSENT from inventory =="
# "stale-adopt" has an ADOPT row, but is NOT a gate (not in inventory).
# "present-tool" is UNRESOLVED (not ADOPT or REJECT), and IS a gate (in inventory).
write_registry '| stale-adopt | test scope | 2026-01-01 | ADOPT — shipped | aligned | fine | link | — |
| present-tool | test scope | 2026-01-01 | UNRESOLVED — pending | mixed | pending | link | — |'
write_gates "present-tool"

OUT="$(run_reconcile)"; RC=$?
chk "T2a detects D2"              "D2 STALE ROW"       "$OUT"
chk "T2b names the tool"          "stale-adopt"        "$OUT"
[ "$RC" -ne 0 ] && ok "T2c exit non-zero on D2" || no "T2c exit non-zero on D2 (got $RC)"

# Fix: remove the stale ADOPT row. Only present-tool (UNRESOLVED) remains.
# present-tool is in inventory and UNRESOLVED → no D1, D2, or D3.
write_registry '| present-tool | test scope | 2026-01-01 | UNRESOLVED — pending | mixed | pending | link | — |'
OUT="$(run_reconcile)"; RC=$?
nchk "T2d D2 gone after fix"     "D2 STALE ROW"        "$OUT"
[ "$RC" -eq 0 ] && ok "T2e clean exit 0 after fix" || no "T2e clean exit 0 after fix (got $RC)"

echo "== T3. D3: CONTRADICTION — REJECT verdict, tool PRESENT in inventory =="
# "reject-me" is REJECTED, but IS a gate (in inventory) → D3 CONTRADICTION.
write_registry '| reject-me | test scope | 2026-01-01 | REJECTED — do not use | aligned | risk | link | — |
| safe-tool | test scope | 2026-01-01 | ADOPT — shipped | aligned | good | link | — |'
write_gates "reject-me" "safe-tool"

OUT="$(run_reconcile)"; RC=$?
chk "T3a detects D3"              "D3 CONTRADICTION"    "$OUT"
chk "T3b names the tool"          "reject-me"           "$OUT"
[ "$RC" -ne 0 ] && ok "T3c exit non-zero on D3" || no "T3c exit non-zero on D3 (got $RC)"

# Fix: change REJECT to ADOPT. Both tools are ADOPT and in inventory → clean.
write_registry '| reject-me | test scope | 2026-01-01 | ADOPT — shipped | aligned | now ok | link | — |
| safe-tool | test scope | 2026-01-01 | ADOPT — shipped | aligned | good | link | — |'
OUT="$(run_reconcile)"; RC=$?
nchk "T3d D3 gone after fix"     "D3 CONTRADICTION"     "$OUT"
[ "$RC" -eq 0 ] && ok "T3e clean exit 0 after fix" || no "T3e clean exit 0 after fix (got $RC)"

echo "== T4. ANTI-FALSE-POSITIVE: clean fixture =="
# Everything in registry matches inventory. tool-a (ADOPT) in inventory, tool-b (REJECT) NOT in inventory.
write_registry '| tool-a | test scope | 2026-01-01 | ADOPT — shipped | aligned | fine | link | — |
| tool-b | test scope | 2026-01-01 | REJECTED — bad | aligned | reason | link | — |'
write_gates "tool-a"  # tool-a in inventory (ADOPT match), tool-b NOT in inventory (REJECT, not running → fine)

OUT="$(run_reconcile)"; RC=$?
[ "$RC" -eq 0 ] && ok "T4a clean fixture exit 0" || no "T4a clean fixture exit 0 (got $RC)"
nchk "T4b no D1 on clean"         "D1 UNEVALUATED ADOPTION" "$OUT"
nchk "T4c no D2 on clean"         "D2 STALE ROW"            "$OUT"
nchk "T4d no D3 on clean"         "D3 CONTRADICTION"         "$OUT"
chk "T4e reports GREEN"           "VERDICT: GREEN"           "$OUT"

echo "== T5. UNREADABLE-INPUT: missing registry =="
rm -f "$FLEETD/state/EVAL-REGISTRY.md"
OUT="$(run_reconcile 2>&1)"; RC=$?
[ "$RC" -ne 0 ] && ok "T5a exit non-zero on missing registry" || no "T5a exit non-zero on missing registry (got $RC)"
nchk "T5b does NOT claim no drift" "no drift found" "$OUT"
nchk "T5c does NOT claim GREEN"    "VERDICT: GREEN" "$OUT"
chk "T5d says FATAL"               "FATAL"          "$OUT"

# ── summary ─────────────────────────────────────────────────────────────────────────
echo ""
echo "=== eval-registry-reconcile.test.sh: $PASS passed, $FAIL failed ==="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
