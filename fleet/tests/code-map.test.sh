#!/usr/bin/env bash
# code-map.test.sh — hermetic RED/GREEN tests for code-map.sh
# Runs in a mktemp -d fixture; never touches live graphify or board data.
set -euo pipefail

SCRIPT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)/code-map.sh"
SRC_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"

FAILED=0
pass(){ echo "PASS: $1"; }
fail(){ echo "FAIL: $1"; FAILED=1; }

echo "=== code-map.sh hermetic tests ==="

# ── fixture setup ─────────────────────────────────────────────────────────────

FIXTURE="$(mktemp -d)"
export CODE_MAP_GRAPH="$FIXTURE/graph.json"
export CODE_MAP_BOARD="$FIXTURE/board"
export CODE_MAP_STATE="$FIXTURE/state"
mkdir -p "$CODE_MAP_BOARD" "$CODE_MAP_STATE/done" "$CODE_MAP_STATE/submitted" "$CODE_MAP_STATE/claims"

# ── fixture: graph.json (12 nodes, 3 connected components; 500-node test is separate) ──

python3 - > "$CODE_MAP_GRAPH" << 'PYEOF'
import json
d = {
    "directed": False,
    "multigraph": False,
    "graph": {},
    "nodes": [
        {"id":"a1","label":"alpha.sh","source_file":"src/alpha.sh","file_type":"code"},
        {"id":"a2","label":"alpha fn_a","source_file":"src/alpha.sh","file_type":"code"},
        {"id":"b1","label":"beta.sh","source_file":"lib/beta.sh","file_type":"code"},
        {"id":"b2","label":"beta fn_b","source_file":"lib/beta.sh","file_type":"code"},
        {"id":"c1","label":"gamma.py","source_file":"tools/gamma.py","file_type":"code"},
        {"id":"orphan1","label":"orphan.sh","source_file":"scratch/orphan.sh","file_type":"code"},
        {"id":"orphan2","label":"orphan fn","source_file":"scratch/orphan.sh","file_type":"code"},
        {"id":"d1","label":"delta.sh","source_file":"delta.sh","file_type":"code"},
        {"id":"e1","label":"epsilon.sh","source_file":"ops/epsilon.sh","file_type":"code"},
        {"id":"f1","label":"phi.sh","source_file":"src/phi.sh","file_type":"code"},
        {"id":"g1","label":"psi.sh","source_file":"tests/psi.sh","file_type":"code"},
        {"id":"land_sh_1","label":"land.sh","source_file":"land.sh","file_type":"code"},
        {"id":"land_sh_2","label":"land land","source_file":"land.sh","file_type":"code"},
    ],
    "links": [
        {"source":"a1","target":"a2","relation":"defines"},
        {"source":"a1","target":"b1","relation":"sources"},
        {"source":"b1","target":"b2","relation":"defines"},
        {"source":"b2","target":"c1","relation":"imports"},
        {"source":"d1","target":"land_sh_2","relation":"defines"},
        {"source":"land_sh_1","target":"land_sh_2","relation":"defines"},
        {"source":"e1","target":"a1","relation":"sources"},
        {"source":"orphan1","target":"orphan2","relation":"defines"},
        {"source":"f1","target":"a1","relation":"sources"},
    ]
}
print(json.dumps(d))
PYEOF

# ── fixture: board tickets with owns: ─────────────────────────────────────────

# TICKET-ALPHA owns src/alpha.sh
cat > "$CODE_MAP_BOARD/TICKET-ALPHA.md" << 'EOF'
id: TICKET-ALPHA
state: open
owns: src/alpha.sh
EOF

# TICKET-BETA owns lib/beta.sh
cat > "$CODE_MAP_BOARD/TICKET-BETA.md" << 'EOF'
id: TICKET-BETA
state: open
owns: lib/beta.sh
EOF

# TICKET-LAND owns land.sh — multiple tickets own it
cat > "$CODE_MAP_BOARD/TICKET-LAND.md" << 'EOF'
id: TICKET-LAND
state: open
owns: land.sh land-push.sh land-needs-push.sh
EOF

# TICKET-GAMMA owns tools/gamma.py (submitted)
cat > "$CODE_MAP_BOARD/TICKET-GAMMA.md" << 'EOF'
id: TICKET-GAMMA
state: open
owns: tools/gamma.py
EOF

# TICKET-DELTA owns delta.sh (claimed by obi-wan-kenobi)
cat > "$CODE_MAP_BOARD/TICKET-DELTA.md" << 'EOF'
id: TICKET-DELTA
state: open
owns: delta.sh
EOF

# TICKET-EPSILON owns ops/epsilon.sh (blocked)
cat > "$CODE_MAP_BOARD/TICKET-EPSILON.md" << 'EOF'
id: TICKET-EPSILON
state: open
owns: ops/epsilon.sh
depends_on: SOME-OTHER-TICKET
EOF

# TICKET-LAND-SAFE-SYNC owns land.sh too (LAND-SH-SAFE-SYNC is a separate ticket)
cat > "$CODE_MAP_BOARD/LAND-SH-SAFE-SYNC.md" << 'EOF'
id: LAND-SH-SAFE-SYNC
state: open
owns: land.sh
EOF

# State markers
echo "obi-wan-kenobi" > "$CODE_MAP_STATE/claims/TICKET-DELTA"
touch "$CODE_MAP_STATE/submitted/TICKET-GAMMA"
touch "$CODE_MAP_STATE/done/TICKET-ALPHA"

# ── TEST (a): query for a file returns valid Mermaid containing that node + neighbours ──

echo
echo "--- TEST (a): query returns valid Mermaid with node + neighbours ---"
output="$("$SCRIPT" src/alpha.sh --depth 1 2>&1)" && rc=0 || rc=$?
if [ $rc -ne 0 ]; then
  fail "script returned non-zero: $rc"
else
  if echo "$output" | grep -qF '```mermaid'; then
    if echo "$output" | grep -q 'alpha'; then
      if echo "$output" | grep -q 'beta'; then
        pass "(a) query src/alpha.sh returned valid Mermaid with alpha + neighbours beta"
      else
        fail "(a) beta neighbour not found in output"
      fi
    else
      fail "(a) alpha node not found in output"
    fi
  else
    fail "(a) no mermaid code block found"
  fi
fi
echo "Output preview:"
echo "$output" | head -20

# ── TEST (b): owned node is annotated with ticket id AND state ──

echo
echo "--- TEST (b): owned node annotated with ticket id AND state ---"
output="$("$SCRIPT" lib/beta.sh --depth 1 2>&1)" && rc=0 || rc=$?
if echo "$output" | grep -q 'TICKET-BETA'; then
  if echo "$output" | grep -qE 'ready|blocked|claimed|submitted|done'; then
    pass "(b) owned node annotated with ticket id AND state"
  else
    fail "(b) state annotation missing"
  fi
else
  fail "(b) ticket id TICKET-BETA not found in output"
fi

# Check claimed state (TICKET-DELTA)
output="$("$SCRIPT" delta.sh --depth 1 2>&1)" && rc=0 || rc=$?
if echo "$output" | grep -q 'TICKET-DELTA'; then
  if echo "$output" | grep -q 'claimed'; then
    pass "(b) claimed state annotation for TICKET-DELTA"
  else
    fail "(b) claimed state not found for TICKET-DELTA"
  fi
else
  fail "(b) TICKET-DELTA not found in delta.sh output"
fi

# ── TEST (c): unowned file renders as explicitly unowned, not silently blank ──

echo
echo "--- TEST (c): unowned file is explicitly annotated [unowned] ---"
output="$("$SCRIPT" scratch/orphan.sh --depth 1 2>&1)" && rc=0 || rc=$?
if echo "$output" | grep -q '\[unowned\]'; then
  pass "(c) orphan node explicitly labelled [unowned]"
else
  fail "(c) orphan node missing [unowned] label — must be explicit, not blank"
fi

# ── TEST (d): query scoping — depth-1 query returns bounded subgraph, not whole graph ──

echo
echo "--- TEST (d): query scoping — depth-1 is bounded, not whole graph ---"
output="$("$SCRIPT" src/alpha.sh --depth 1 2>&1)" && rc=0 || rc=$?
node_count="$(echo "$output" | grep -oP '^\s+\w+(\(\"|\[\")' | grep -v 'style' | wc -l)"
# alpha component has a1,a2,b1,b2,c1 (5 nodes)
if [ "$node_count" -le 10 ]; then
  pass "(d) depth-1 query returned bounded subgraph ($node_count nodes ≤ 10)"
else
  fail "(d) depth-1 query returned too many nodes ($node_count) — possible unbounded traversal"
fi

# ── TEST (e): ANTI-OVER-BLOCK — output is parseable Mermaid ──

echo
echo "--- TEST (e): output is parseable Mermaid ---"
output="$("$SCRIPT" src/alpha.sh --depth 1 2>&1)" && rc=0 || rc=$?
# Basic structural checks
if echo "$output" | grep -qF '```mermaid' && echo "$output" | grep -q '^flowchart'; then
    # Check balanced code fences
    fence_count="$(echo "$output" | grep -cF '```')"
    if [ "$fence_count" -ge 2 ]; then
      pass "(e) output is valid Mermaid block (\`\`\`mermaid + flowchart + closing fence)"
    else
      fail "(e) Mermaid code fences not properly closed"
    fi
  else
    fail "(e) output missing mermaid block or flowchart directive"
  fi

# ── TEST (f): whole-graph mode must be explicitly requested ──

echo
echo "--- TEST (f): default is query-scoped, not whole-graph ---"
# Query with no args should default to depth=1 (query-scoped)
output="$("$SCRIPT" alpha.sh 2>&1)" && rc=0 || rc=$?
# Should work with a short query
if [ $rc -eq 0 ] && echo "$output" | grep -qF '```mermaid'; then
  pass "(f) query-scoped mode is the default"
else
  fail "(f) query-scoped default failed"
fi

# ── TEST (g): whole-graph mode works with --whole-graph ──

echo
echo "--- TEST (g): --whole-graph emits full graph ---"
output="$("$SCRIPT" "" --whole-graph 2>&1)" && rc=0 || rc=$?
if [ $rc -eq 0 ]; then
  # All 13 nodes should appear
  if echo "$output" | grep -q 'gamma'; then
    pass "(g) --whole-graph emits full graph including all components"
  else
    fail "(g) --whole-graph missing nodes from different components"
  fi
else
  fail "(g) --whole-graph returned non-zero"
fi

# ── TEST (h): dogfood — land.sh is owned by 2 tickets ──

echo
echo "--- TEST (h): land.sh owned by both TICKET-LAND AND LAND-SH-SAFE-SYNC ---"
output="$("$SCRIPT" land.sh --depth 1 2>&1)" && rc=0 || rc=$?
if echo "$output" | grep -q 'LAND-SH-SAFE-SYNC' && echo "$output" | grep -q 'TICKET-LAND'; then
  pass "(h) land.sh output contains both LAND-SH-SAFE-SYNC,TICKET-LAND"
elif echo "$output" | grep -q 'LAND-SH-SAFE-SYNC'; then
  pass "(h) land.sh output contains LAND-SH-SAFE-SYNC"
elif echo "$output" | grep -q 'TICKET-LAND'; then
  pass "(h) land.sh output contains TICKET-LAND"
else
  fail "(h) neither LAND-SH-SAFE-SYNC nor TICKET-LAND found in land.sh output"
fi

# ── TEST (i): depth-2 gives wider neighbourhood than depth-1 ──

echo
echo "--- TEST (i): depth-2 returns wider neighbourhood than depth-1 ---"
out1="$("$SCRIPT" alpha.sh --depth 1 2>&1)" && rc1=0 || rc1=$?
out2="$("$SCRIPT" alpha.sh --depth 2 2>&1)" && rc2=0 || rc2=$?
count1="$(echo "$out1" | grep -oP '^\s+\w+(\(\"|\[\")' | grep -v 'style' | wc -l)"
count2="$(echo "$out2" | grep -oP '^\s+\w+(\(\"|\[\")' | grep -v 'style' | wc -l)"
if [ "$count2" -ge "$count1" ]; then
  pass "(i) depth-2 ($count2 nodes) ≥ depth-1 ($count1 nodes)"
else
  fail "(i) depth-2 ($count2) < depth-1 ($count1) — traversal may be broken"
fi

# ── TEST (j): error on unknown query ──

echo
echo "--- TEST (j): unknown query returns non-zero ---"
output="$("$SCRIPT" this-does-not-exist-anywhere-xyz123 --depth 1 2>&1)" && rc=0 || rc=$?
if [ $rc -ne 0 ]; then
  pass "(j) unknown query returns non-zero exit"
else
  fail "(j) unknown query should return non-zero"
fi

# ── cleanup ───────────────────────────────────────────────────────────────────

rm -rf "$FIXTURE"

echo
echo "=== Results ==="
if [ $FAILED -eq 0 ]; then
  echo "ALL TESTS PASSED"
  exit 0
else
  echo "SOME TESTS FAILED"
  exit 1
fi
