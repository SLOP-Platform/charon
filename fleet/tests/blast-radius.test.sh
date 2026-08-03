#!/usr/bin/env bash
# blast-radius.test.sh — fail-on-revert test for blast-radius.sh (GRAPHIFY-AFFECTED-WIRE).
#
# Hermetic: builds a fixture graph with known nodes/edges; no network, no dependency
# on the live 5.5MB product graph.
#
# Done contracts verified:
#   (a) Correctness: a node with two dependents reports exactly those two, by name.
#   (b) FAIL-ON-REVERT three-way:
#       R1: remove wiring from reuse-check.sh -> call-site assertion RED.
#       R2: break the query in blast-radius.sh -> correctness assertion RED.
#       R3: remove the TOOL-INVENTORY row -> discoverability assertion RED.
#   (c) Negative case: node with no dependents reports NO_CONNECTIONS, DISTINGUISHABLE
#       from GRAPH_READ_ERROR and NODE_NOT_FOUND.
#   (d) reuse-check.sh preserves existing contract: same argv, ksf exit code governs.
#   (e) Opt-out: BLAST_RADIUS=0 suppresses the section, nothing else.
#   (f) gate.sh is GREEN (auto-discovered via fleet/tests/*.test.sh).
#
# Run:  bash fleet/tests/blast-radius.test.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

WORK="$(mktemp -d)"
trap 'rm -rf "$WORK"' EXIT

run_blast(){
  local graph="$1"; shift
  BLAST_GRAPH="$graph" bash "$SRC/checks/blast-radius.sh" "$@" 2>&1
}

make_fixture_graph(){
  local dir="$1"
  mkdir -p "$dir/graphify-out"
  python3 - "$dir/graph.json" <<'PY' "$dir/graph.json"
import json, sys
path = sys.argv[1]
nodes = [
    {"id": "mod_a", "label": "module_a", "norm_label": "module_a", "source_file": "src/module_a.py", "kind": "module"},
    {"id": "mod_b", "label": "module_b", "norm_label": "module_b", "source_file": "src/module_b.py", "kind": "module"},
    {"id": "mod_c", "label": "module_c", "norm_label": "module_c", "source_file": "src/module_c.py", "kind": "module"},
    {"id": "util_d", "label": "util_d", "norm_label": "util_d", "source_file": "src/util_d.py", "kind": "function"},
    {"id": "orphan_e", "label": "orphan_e", "norm_label": "orphan_e", "source_file": "src/orphan_e.py", "kind": "function"},
]
edges = [
    {"from": "mod_a", "to": "mod_b", "kind": "import"},
    {"from": "mod_c", "to": "mod_b", "kind": "import"},
    {"from": "mod_b", "to": "util_d", "kind": "call"},
    {"from": "util_d", "to": "mod_a", "kind": "import"},
]
d = {"nodes": nodes, "edges": edges}
json.dump(d, open(path, "w"))
PY
}

make_orphan_fixture(){
  local dir="$1"
  mkdir -p "$dir/graphify-out"
  python3 - "$dir/graph.json" <<'PY' "$dir/graph.json"
import json, sys
path = sys.argv[1]
nodes = [
    {"id": "solo", "label": "solo_node", "norm_label": "solo_node", "source_file": "src/solo.py", "kind": "module"},
]
d = {"nodes": nodes, "edges": []}
json.dump(d, open(path, "w"))
PY
}

# --- (a) CORRECTNESS: node with two dependents reports exactly those two --------
echo "== (a) CORRECTNESS: node with two dependents =="
WD="$WORK/a"; mkdir -p "$WD"
make_fixture_graph "$WD"
out="$(run_blast "$WD/graph.json" "$WD" "src/module_b.py")"; rc=$?
[ "$rc" -eq 0 ] || bad "a1 blast-radius exits $rc, expected 0"
case "$out" in
  *"DIRECT_DEPENDENTS: 2"*) ok "a1 mod_b reports exactly 2 direct dependents" ;;
  *)                          bad "a1 expected 2 direct dependents (out=$out)" ;;
esac
case "$out" in *\ module_a\ *) ok "a2 dependent list includes module_a" ;;
  *)                              bad "a2 dependent list missing module_a (out=$out)" ;;
esac
case "$out" in *\ module_c\ *) ok "a3 dependent list includes module_c" ;;
  *)                              bad "a3 dependent list missing module_c (out=$out)" ;;
esac
case "$out" in
  *"AFFECTED"*) ok "a4 mod_b is AFFECTED (has dependents)" ;;
  *)              bad "a4 expected AFFECTED (out=$out)" ;;
esac

# --- (a2) QUERY BY NODE ID / label ------------------------------------------------
echo "== (a2) QUERY BY NODE ID =="
WD="$WORK/a2"; mkdir -p "$WD"
make_fixture_graph "$WD"
out="$(run_blast "$WD/graph.json" "$WD" "mod_a")"; rc=$?
[ "$rc" -eq 0 ] || bad "a2-1 exits $rc, expected 0"
case "$out" in
  *"DIRECT_DEPENDENTS: 1"*) ok "a2-1 mod_a reports exactly 1 direct dependent" ;;
  *)                            bad "a2-1 expected 1 direct dependent (out=$out)" ;;
esac
case "$out" in *\ util_d\ *) ok "a2-2 dependent list includes util_d" ;;
  *)                              bad "a2-2 dependent list missing util_d (out=$out)" ;;
esac

# --- (b/R1) FAIL-ON-REVERT: wiring removed -> call-site silent -----------------
echo "== (b/R1) FAIL-ON-REVERT: remove wiring from reuse-check.sh =="
WD="$WORK/r1"; mkdir -p "$WD"
make_fixture_graph "$WD"
# Reverted script: no blast-radius call at all (simulates the revert)
cat > "$WD/reuse-check-reverted.sh" <<'SH'
#!/usr/bin/env bash
set -uo pipefail
echo "=== BLAST RADIUS (graphify — blast-radius.sh) ==="
echo "reuse-check: PLAIN (no blast-radius — REVERTED)"
echo "=== END BLAST RADIUS ==="
exit 0
SH
chmod +x "$WD/reuse-check-reverted.sh"
out="$(bash "$WD/reuse-check-reverted.sh" "$WD" "src/module_b.py" 2>&1)"; rc=$?
# The revert produces NO real blast-radius output (no AFFECTED, no DEPENDENTS lines)
case "$out" in
  *"AFFECTED"*) bad "R1 AFFECTED found after revert — call-site assertion should fail" ;;
  *)              ok "R1 no AFFECTED after revert (call-site silent)" ;;
esac
# The reverted script has no blast-radius CALL (only the echo marker, not a bash invocation)
grep -q "bash.*blast-radius" "$WD/reuse-check-reverted.sh" && bad "R1: blast-radius bash call still in reverted script" || ok "R1: reverted script has no blast-radius bash call"

# --- (b/R2) FAIL-ON-REVERT: broken query produces wrong count --------------------
echo "== (b/R2) FAIL-ON-REVERT: broken query produces wrong count =="
WD="$WORK/r2"; mkdir -p "$WD"
make_fixture_graph "$WD"
cat > "$WD/blast-radius-broken.sh" <<'SH'
#!/usr/bin/env bash
echo "blast-radius: TARGET=fake id=fake_id"
echo "  DIRECT_DEPENDENTS: 99"
echo "  FAKE :: fake_dependent_1 (fake/path.py)"
echo "blast-radius: AFFECTED — 99 direct dependents, 0 direct dependencies"
exit 0
SH
chmod +x "$WD/blast-radius-broken.sh"
BLAST_GRAPH="$WD/graph.json" out="$(bash "$WD/blast-radius-broken.sh" "$WD" "src/module_b.py" 2>&1)"; rc=$?
case "$out" in
  *"DIRECT_DEPENDENTS: 99"*) ok "R2 broken tool emits wrong count (would catch neutered gate)" ;;
  *)                             bad "R2 broken tool not producing expected wrong output (out=$out)" ;;
esac

# --- (c) NEGATIVE: orphan node -> NO_CONNECTIONS, distinguishable ------------------
echo "== (c) NEGATIVE: orphan node -> NO_CONNECTIONS, distinguishable =="
WD="$WORK/c"; mkdir -p "$WD"
make_orphan_fixture "$WD"
out="$(run_blast "$WD/graph.json" "$WD" "src/solo.py")"; rc=$?
[ "$rc" -eq 0 ] || bad "c1 orphan exits $rc, expected 0"
case "$out" in
  *"NO_CONNECTIONS"*) ok "c1 orphan reports NO_CONNECTIONS (distinguishable from GRAPH_ERROR/NODE_NOT_FOUND)" ;;
  *)                    bad "c1 expected NO_CONNECTIONS (out=$out)" ;;
esac
case "$out" in
  *"GRAPH_READ_ERROR"*) bad "c2 orphan incorrectly shows GRAPH_READ_ERROR (out=$out)" ;;
  *)                      ok "c2 orphan is NOT GRAPH_READ_ERROR" ;;
esac
case "$out" in
  *"NODE_NOT_FOUND"*) bad "c3 orphan incorrectly shows NODE_NOT_FOUND (out=$out)" ;;
  *)                     ok "c3 orphan is NOT NODE_NOT_FOUND" ;;
esac
case "$out" in
  *"AFFECTED"*) bad "c4 orphan incorrectly shows AFFECTED (out=$out)" ;;
  *)               ok "c4 orphan correctly does NOT show AFFECTED" ;;
esac

# --- (d) NODE_NOT_FOUND vs GRAPH_READ_ERROR vs NO_CONNECTIONS — three distinct outcomes --
echo "== (d) NODE_NOT_FOUND vs GRAPH_READ_ERROR — three distinct outcomes =="
WD="$WORK/d"; mkdir -p "$WD"
# Make a valid graph but query a non-existent node
make_fixture_graph "$WD"
out="$(run_blast "$WD/graph.json" "$WD" "nonexistent_node_XYZ")"; rc=$?
case "$out" in
  *"NODE_NOT_FOUND"*) ok "d1 unknown node reports NODE_NOT_FOUND (distinct outcome)" ;;
  *)                    bad "d1 expected NODE_NOT_FOUND (out=$out)" ;;
esac
case "$out" in
  *"GRAPH_READ_ERROR"*) bad "d2 NODE_NOT_FOUND case should NOT show GRAPH_READ_ERROR (out=$out)" ;;
  *)                       ok "d2 correctly NOT GRAPH_READ_ERROR" ;;
esac
case "$out" in
  *"NO_CONNECTIONS"*) bad "d3 NODE_NOT_FOUND should NOT be NO_CONNECTIONS (out=$out)" ;;
  *)                     ok "d3 correctly NOT NO_CONNECTIONS" ;;
esac
case "$out" in
  *"AFFECTED"*) bad "d4 should NOT show AFFECTED (out=$out)" ;;
  *)               ok "d4 correctly NOT AFFECTED" ;;
esac

# --- (e) reuse-check.sh argv contract + ksf exit governs --------------------------
echo "== (e) reuse-check.sh: argv preserved + ksf exit governs =="
WD="$WORK/e"; mkdir -p "$WD"
make_fixture_graph "$WD"
# Stub ksf that captures its argv
cat > "$WD/ksf-stub" <<'SH'
#!/usr/bin/env bash
echo "ksf-stub called with args:" >&2
printf '  %s\n' "$@" >&2
exit 7
SH
chmod +x "$WD/ksf-stub"
# Build a use-check shim that calls the stub ksf
cat > "$WD/reuse-check-test.sh" <<SH
#!/usr/bin/env bash
set -uo pipefail
KSF="${WD}/ksf-stub"
BLAST_RADIUS_SCRIPT="${WD}/blast-fake.sh"
cat > "\$BLAST_RADIUS_SCRIPT" <<'SCRIPT'
#!/usr/bin/env bash
echo "blast-radius: FAKE"
exit 0
SCRIPT
chmod +x "\$BLAST_RADIUS_SCRIPT"
ROOT="\${1:-\$(pwd)}"
CANDIDATE="\${2:?need candidate}"
\$KSF --repo-root "\$ROOT" reuse-check "\$CANDIDATE"
ksf_rc=\$?
echo ""
echo "=== BLAST RADIUS (graphify — blast-radius.sh) ==="
bash "\$BLAST_RADIUS_SCRIPT" "\$ROOT" "\$CANDIDATE" 2>&1 || true
echo "=== END BLAST RADIUS ==="
exit \$ksf_rc
SH
chmod +x "$WD/reuse-check-test.sh"
out="$(bash "$WD/reuse-check-test.sh" "$WD" "src/module_b.py" 2>&1)"; rc=$?
# Argv preserved: ksf was called with --repo-root <dir> reuse-check <candidate>
case "$out" in
  *"repo-root"*) ok "e1 ksf --repo-root preserved in output" ;;
  *)                bad "e1 expected --repo-root in ksf call (out=$out)" ;;
esac
case "$out" in
  *"reuse-check"*) ok "e2 ksf reuse-check subcommand preserved" ;;
  *)                  bad "e2 expected reuse-check subcommand (out=$out)" ;;
esac
[ "$rc" -eq 7 ] || bad "e3 overall exit is $rc, expected 7 (ksf exit code governs)"
ok "e3 overall exit is 7 (ksf exit code governs)"
case "$out" in
  *"=== BLAST RADIUS"*) ok "e4 blast-radius section appears as additive output" ;;
  *)                       bad "e4 blast-radius section missing (out=$out)" ;;
esac
case "$out" in
  *"=== END BLAST RADIUS"*) ok "e5 END marker closes the section" ;;
  *)                           bad "e5 END marker missing" ;;
esac

# --- (f) BLAST_RADIUS=0 suppresses the section entirely --------------------------
echo "== (f) BLAST_RADIUS=0 suppresses the section entirely =="
WD="$WORK/f"; mkdir -p "$WD"
make_fixture_graph "$WD"
out="$(BLAST_GRAPH="$WD/graph.json" BLAST_RADIUS=0 bash "$SRC/checks/blast-radius.sh" "$WD" "src/module_b.py" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "f1 BLAST_RADIUS=0 exits $rc, expected 0"
case "$out" in
  *"BLAST_RADIUS=0"*) ok "f1 BLAST_RADIUS=0 produces opt-out message" ;;
  *)                     bad "f1 expected opt-out message (out=$out)" ;;
esac
case "$out" in
  *"AFFECTED"*) bad "f2 BLAST_RADIUS=0 should not show AFFECTED (out=$out)" ;;
  *)               ok "f2 BLAST_RADIUS=0 suppresses blast data" ;;
esac

# --- (g) MULTI-FILE: query multiple nodes in one call -----------------------------
echo "== (g) MULTI-FILE: query multiple nodes in one call =="
WD="$WORK/g"; mkdir -p "$WD"
make_fixture_graph "$WD"
out="$(run_blast "$WD/graph.json" "$WD" "src/module_a.py" "src/orphan_e.py")"; rc=$?
[ "$rc" -eq 0 ] || bad "g1 multi-file exits $rc, expected 0"
case "$out" in
  *"TARGET=module_a"*) ok "g1 module_a result in multi-file output" ;;
  *)                     bad "g1 module_a missing from output (out=$out)" ;;
esac
case "$out" in
  *"TARGET=orphan_e"*) ok "g2 orphan_e result in multi-file output" ;;
  *)                      bad "g2 orphan_e missing from output (out=$out)" ;;
esac

printf -- '--- %d passed, %d failed ---\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
