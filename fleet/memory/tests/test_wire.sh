#!/usr/bin/env bash
# test_wire.sh — FAIL-ON-REVERT tests for fleet/memory/ wire-up.
#
# Asserts the MEMORY-WIRE-RETRIEVAL contract:
#   (a) session-preamble.sh output is SMALL (pinned + pointer, not the full
#       ~95-file dump). Byte size of pinned + pointer must be < 50% of the
#       wholesale markdown/ dump.
#   (b) session-preamble.sh output contains the PINNED core header and a
#       point-of-need pointer naming fleet/memory/search.py.
#   (c) load.sh default mode = pinned + pointer (no wholesale dump).
#   (d) load.sh --query <topic> wraps search.py and returns ranked results.
#   (e) load.sh --json <topic> wraps search.py --json and returns valid JSON.
#   (f) search.py returns ranked results for a known topic ("failover") and
#       the top result is the actual failover doc.
#   (g) session-preamble.sh --check exits 0 and reports a sane pin/markdown
#       ratio + at least one result for the failover probe query.
#
# Run: bash fleet/memory/tests/test_wire.sh   (exit 0 = all pass)
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
MEM="$HERE/.."
PREAMBLE="$MEM/session-preamble.sh"
LOAD="$MEM/load.sh"
SEARCH="$MEM/search.py"
PIN="$MEM/pin.md"
MD_DIR="$MEM/markdown"

PASS=0; FAIL=0
ok()  { PASS=$((PASS+1)); echo "PASS: $1"; }
bad() { FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# ── (a) preamble is small relative to wholesale dump ─────────────────────────
echo "== (a) preamble size =="
preamble_bytes=$(bash "$PREAMBLE" 2>/dev/null | wc -c | tr -d ' ')
pin_bytes=0
[ -f "$PIN" ] && pin_bytes=$(wc -c < "$PIN" | tr -d ' ')
total_md_bytes=0
if [ -d "$MD_DIR" ]; then
  total_md_bytes=$(cat "$MD_DIR"/*.md 2>/dev/null | wc -c | tr -d ' ')
fi
echo "  preamble_bytes=$preamble_bytes  pin_bytes=$pin_bytes  markdown_total=$total_md_bytes"
[ "$preamble_bytes" -gt 0 ] && ok "a1 preamble emits non-empty output" || bad "a1 preamble emits non-empty output"
[ "$preamble_bytes" -lt 5000 ] && ok "a2 preamble is <5000 bytes (no wholesale dump)" || bad "a2 preamble is <5000 bytes (got $preamble_bytes)"
[ "$total_md_bytes" -gt 0 ] && [ "$preamble_bytes" -lt $(( total_md_bytes / 2 )) ] \
  && ok "a3 preamble is <50% of wholesale dump" \
  || bad "a3 preamble is <50% of wholesale dump (preamble=$preamble_bytes, total=$total_md_bytes)"

# ── (b) preamble contains pinned header + pointer ───────────────────────────
echo "== (b) preamble shape =="
out=$(bash "$PREAMBLE" 2>/dev/null)
echo "$out" | grep -q "PINNED CORE" && ok "b1 preamble contains PINNED CORE header" || bad "b1 preamble contains PINNED CORE header"
echo "$out" | grep -q "search.py"   && ok "b2 preamble points at search.py"          || bad "b2 preamble points at search.py"
echo "$out" | grep -qi "pull-on-demand\|point-of-need\|at point-of-need" \
  && ok "b3 preamble contains pull-on-demand language" \
  || bad "b3 preamble contains pull-on-demand language"

# ── (c) load.sh default = pinned + pointer, not wholesale ──────────────────
echo "== (c) load.sh default =="
load_default=$(bash "$LOAD" 2>/dev/null)
load_default_bytes=$(printf '%s' "$load_default" | wc -c | tr -d ' ')
echo "$load_default" | grep -q "PINNED CORE" && ok "c1 load.sh default contains PINNED CORE" || bad "c1 load.sh default contains PINNED CORE"
# Wholesale dump marker must NOT appear in default load
if echo "$load_default" | grep -q "FULL MEMORY SET"; then
  bad "c2 load.sh default must NOT contain FULL MEMORY SET marker"
else
  ok "c2 load.sh default does NOT contain FULL MEMORY SET marker"
fi
[ "$load_default_bytes" -lt 5000 ] && ok "c3 load.sh default <5000 bytes" || bad "c3 load.sh default <5000 bytes (got $load_default_bytes)"

# ── (d) load.sh --query wraps search.py ─────────────────────────────────────
echo "== (d) load.sh --query =="
qout=$(bash "$LOAD" --query failover 2>/dev/null)
echo "$qout" | grep -qi "failover" && ok "d1 load.sh --query failover returns failover results" || bad "d1 load.sh --query failover returns failover results"
echo "$qout" | grep -q "score:" && ok "d2 load.sh --query output is human-readable (has score:)" || bad "d2 load.sh --query output is human-readable (has score:)"

# ── (e) load.sh --json wraps search.py --json ──────────────────────────────
echo "== (e) load.sh --json =="
jout=$(bash "$LOAD" --json failover 2>/dev/null)
# Validate JSON
if printf '%s' "$jout" | python3 -c 'import json,sys; d=json.load(sys.stdin); assert isinstance(d,list); assert len(d)>0' 2>/dev/null; then
  ok "e1 load.sh --json returns valid JSON list with >0 results"
else
  bad "e1 load.sh --json returns valid JSON list with >0 results"
fi

# ── (f) search.py returns ranked failover results ───────────────────────────
echo "== (f) search.py direct =="
sout=$(python3 "$SEARCH" --json failover 2>/dev/null)
top_file=$(printf '%s' "$sout" | python3 -c 'import json,sys; d=json.load(sys.stdin); print(d[0]["file"] if d else "")' 2>/dev/null || echo "")
[ -n "$top_file" ] && ok "f1 search.py returns at least one result for failover" || bad "f1 search.py returns at least one result for failover"
echo "$top_file" | grep -qi "failover" && ok "f2 top result is the failover doc" || bad "f2 top result is the failover doc (got: $top_file)"

# ── (g) session-preamble.sh --check ─────────────────────────────────────────
echo "== (g) session-preamble.sh --check =="
rc=0; bash "$PREAMBLE" --check > /tmp/wire-check.out 2>&1 || rc=$?
[ "$rc" -eq 0 ] && ok "g1 --check exits 0" || bad "g1 --check exits 0 (rc=$rc)"
grep -q "pin/markdown ratio" /tmp/wire-check.out && ok "g2 --check reports pin/markdown ratio" || bad "g2 --check reports pin/markdown ratio"
grep -q "search failover:" /tmp/wire-check.out && ok "g3 --check reports failover search count" || bad "g3 --check reports failover search count"

# ── summary ─────────────────────────────────────────────────────────────────
echo ""
echo "== summary: $PASS passed, $FAIL failed =="
[ "$FAIL" -eq 0 ] && exit 0 || exit 1
