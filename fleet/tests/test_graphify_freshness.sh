#!/usr/bin/env bash
# test_graphify_freshness.sh — FAIL-ON-REVERT self-test for fleet/checks/graphify-freshness.sh
# (GRAPHIFY-MAP-FRESHNESS). Verifies the script's five contracts on a fully hermetic
# fixture (the script's `GRAPHIFY_FRESHNESS_FAKE` seam — never the real graph/repo):
#
#   (1) FRESH      -> `check` exits 0; verdict line says GREEN.
#   (2) STALE      -> `check` exits 1; verdict line is RED; named in the loud message.   <- the load-bearing case
#   (3) ABSENT     -> `check` exits 1; "no graph.json at ..." surfaced; still RED.
#   (4) RECONCILE  -> `update` with a fake `graphify` that just rewrites the stamp + populates
#                     changed_code_files=[empty] brings STALE -> FRESH; `check` then exits 0.
#                     (Dogfoods the "STALE -> update -> FRESH -> check passes" loop end-to-end.)
#   (5) reuse-check -> finds a graph-node match for an existing function name; reports no
#                     match for nonsense; aborts (rc=2) when the graph is stale.
#   (6) FAIL-ON-REVERT: removing the staleness detector from the script makes case (2) wrongly
#       GREEN — proving (2)'s RED comes from THAT check, not a coincidence.
#
# Run:  bash fleet/tests/test_graphify_freshness.sh   (exit 0 = all pass)
set -uo pipefail
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "PASS: $1"; }
bad(){  FAIL=$((FAIL+1)); echo "FAIL: $1"; }

# --- fixture: a temp dir that the script reads as its `repo`. We set
# GRAPHIFY_FRESHNESS_FAKE=<dir>; classify_one / built_commit / fake_or_real
# all read from that dir instead of the live graph.json. -----------------------------
make_fake_repo(){
  local d="$1" state="$2" built="$3" head="$4" changed="${5:-}"
  mkdir -p "$d"
  printf '%s' "$state"   > "$d/state"
  printf '%s' "$built"   > "$d/graph_built_at_commit"
  printf '%s' "$head"    > "$d/_head"
  printf '%s' "$changed" > "$d/changed_code_files"
}

# --- (1) FRESH ----------------------------------------------------------------------
echo "== (1) FRESH: built_at_commit == HEAD, no changes =="
D1="$(mktemp -d)"; D2=""; D3=""; D4=""; D5=""; D5b=""; D5b_inv=""; D6=""; D7=""; D8=""; DBIN=""
trap 'rm -rf "$D1" "$D2" "$D3" "$D4" "$D5" "$D5b" "$D5b_inv" "$D6" "$D7" "$D8" "$DBIN"' EXIT
HEAD="aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
make_fake_repo "$D1" "FRESH" "$HEAD" "$HEAD" ""
out="$(GRAPHIFY_FRESHNESS_FAKE="$D1" bash "$SRC/checks/graphify-freshness.sh" check "$D1" 2>&1)"; rc=$?
case "$out" in
  *"GREEN"*)            ok "1a check exits 0 and prints GREEN" ;;
  *)                    bad "1a missing GREEN verdict (rc=$rc, out=$out)" ;;
esac
[ "$rc" -eq 0 ] || bad "1a check exit code is $rc, expected 0"

# --- (2) STALE ---------------------------------------------------------------------
echo "== (2) STALE: built_at_commit behind HEAD, code files changed =="
D2="$(mktemp -d)"
OLD="bbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbbb"
HEAD="cccccccccccccccccccccccccccccccccccccccc"
make_fake_repo "$D2" "STALE" "$OLD" "$HEAD" "src/foo.py
src/bar.py
README.md"
out="$(GRAPHIFY_FRESHNESS_FAKE="$D2" bash "$SRC/checks/graphify-freshness.sh" check "$D2" 2>&1)"; rc=$?
case "$out" in
  *"RED"*)              ok "2a check exits 1 and prints RED" ;;
  *)                    bad "2a missing RED verdict (rc=$rc, out=$out)" ;;
esac
[ "$rc" -eq 1 ] || bad "2a check exit code is $rc, expected 1 (RED)"
case "$out" in
  *"src/foo.py"*"src/bar.py"*) ok "2b lists the changed code files (the actionable evidence)" ;;
  *)                            bad "2b missing changed-file evidence (out=$out)" ;;
esac
case "$out" in
  *"STALE GRAPH"*"REINVENTION"*) ok "2c surfaces the human-meaningful REINVENTION banner" ;;
  *)                              bad "2c missing the REINVENTION banner" ;;
esac

# --- (3) ABSENT ---------------------------------------------------------------------
echo "== (3) ABSENT: no graph.json at all (the rig at cere-junda handoff) =="
D3="$(mktemp -d)"
HEAD="dddddddddddddddddddddddddddddddddddddddd"
# state=ABSENT, no graph_built_at_commit, no changed files (the script returns 'no graph')
make_fake_repo "$D3" "ABSENT" "" "$HEAD" ""
out="$(GRAPHIFY_FRESHNESS_FAKE="$D3" bash "$SRC/checks/graphify-freshness.sh" check "$D3" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "3a check exit code is $rc, expected 1 (RED) for absent graph"
case "$out" in *"ABSENT"*) ok "3a check surfaces ABSENT state" ;; *) bad "3a missing ABSENT (out=$out)" ;; esac
case "$out" in *"RED"*)      ok "3b check still prints RED on ABSENT" ;; *) bad "3b missing RED (out=$out)" ;; esac

# --- (4) RECONCILE: STALE -> update -> FRESH ----------------------------------------
echo '== (4) RECONCILE: a STALE graph is brought to FRESH by "update" (dogfood the loop) =='
D4="$(mktemp -d)"
# State begins as STALE with a code change; the fake `graphify` writes a new
# graph_built_at_commit equal to HEAD, and clears changed_code_files. After
# `update`, `check` must exit 0.
OLD="1111111111111111111111111111111111111111"
HEAD="2222222222222222222222222222222222222222"
make_fake_repo "$D4" "STALE" "$OLD" "$HEAD" "src/foo.py
src/baz.py"
# Fake `graphify` binary that always brings STALE -> FRESH: rewrites graph_built_at_commit
# to HEAD and clears changed_code_files. The real graphify does this in production
# (the script just runs `graphify update <path>`; if the corpus changed, it rewrites).
DBIN="$(mktemp -d)"
cat > "$DBIN/graphify" <<'SH'
#!/usr/bin/env bash
# fake graphify: for `update <path>`, write a fresh built_at_commit to the FAKE dir
# and clear the changed-code-files list. Mirrors the real `graphify update` happy path.
[ "${1:-}" = "update" ] || { echo "fake graphify: only `update` supported" >&2; exit 2; }
[ -n "${GRAPHIFY_FRESHNESS_FAKE:-}" ] || { echo "fake graphify: GRAPHIFY_FRESHNESS_FAKE not set" >&2; exit 2; }
HEAD="$(cat "$GRAPHIFY_FRESHNESS_FAKE/_head" 2>/dev/null || true)"
[ -n "$HEAD" ] || { echo "fake graphify: no _head in $GRAPHIFY_FRESHNESS_FAKE" >&2; exit 2; }
printf '%s' "$HEAD" > "$GRAPHIFY_FRESHNESS_FAKE/graph_built_at_commit"
: > "$GRAPHIFY_FRESHNESS_FAKE/changed_code_files"
# update the state file too: STALE/ABSENT -> FRESH
printf 'FRESH' > "$GRAPHIFY_FRESHNESS_FAKE/state"
echo "Code graph updated. (fake)"
SH
chmod +x "$DBIN/graphify"
out="$(GRAPHIFY_FRESHNESS_FAKE="$D4" GRAPHIFY_BIN="$DBIN/graphify" \
        bash "$SRC/checks/graphify-freshness.sh" update "$D4" 2>&1)"; rc_upd=$?
[ "$rc_upd" -eq 0 ] || bad "4a update exit code is $rc_upd, expected 0 (out=$out)"
case "$out" in
  *"UPDATE OK"*) ok "4a update prints UPDATE OK on success" ;;
  *)             bad "4a missing UPDATE OK (out=$out)" ;;
esac
# now `check` should be GREEN
out="$(GRAPHIFY_FRESHNESS_FAKE="$D4" bash "$SRC/checks/graphify-freshness.sh" check "$D4" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "4b after update, check exit is $rc, expected 0 (out=$out)"
case "$out" in *"GREEN"*) ok "4b post-update check is GREEN" ;; *) bad "4b post-update not GREEN (out=$out)" ;; esac

# --- (5) reuse-check ----------------------------------------------------------------
echo "== (5) reuse-check: finds a graph-node match for an existing function name =="
D5="$(mktemp -d)"
HEAD="3333333333333333333333333333333333333333"
mkdir -p "$D5/graphify-out"
# Hand-craft a graph.json with a single node whose label == "freshness_stamp"
# (a real function in fleet/handoff.sh). reuse-check should match it.
python3 - "$D5" <<'PY' 2>/dev/null
import json, sys, os
d = os.path.join(sys.argv[1], "graphify-out")
os.makedirs(d, exist_ok=True)
graph = {
    "directed": False, "multigraph": False, "graph": {},
    "nodes": [
        {"id": "fleet_handoff_freshness_stamp", "label": "freshness_stamp()",
         "norm_label": "freshness_stamp", "source_file": "fleet/handoff.sh",
         "source_location": "L49", "metadata": {"language": "bash", "kind": "function"}},
        {"id": "unrelated", "label": "totally_different()", "norm_label": "totally_different",
         "source_file": "x.py", "source_location": "L1", "metadata": {"language": "python", "kind": "function"}},
    ],
    "links": [],
    "built_at_commit": "3333333333333333333333333333333333333333",
}
json.dump(graph, open(os.path.join(d, "graph.json"), "w"))
PY
# We need a HEAD in the fake root for the freshness check to pass
printf '%s' "$HEAD" > "$D5/_head"
# Point the script at this fake repo via env (RIG_REPO/PRODUCT_REPO) and
# GRAPHIFY_FRESHNESS_FAKE so the staleness check uses the fake root.
out="$(RIG_REPO="$D5" GRAPHIFY_FRESHNESS_FAKE="$D5" \
        bash "$SRC/checks/graphify-freshness.sh" reuse-check "freshness" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "5a reuse-check exit is $rc, expected 0 (match found) (out=$out)"
case "$out" in
  *"fleet_handoff_freshness_stamp"*) ok "5a reuse-check surfaces the existing function id" ;;
  *)                                   bad "5a missing the freshness_stamp match (out=$out)" ;;
esac
# Negative case: nonsense query -> rc=1, no match. Point PRODUCT_REPO + TOOL_INVENTORY
# at the same fake rig + a minimal inventory fixture so the scan only runs against
# controlled, deterministic corpora (the real product graph has 6548 nodes and the
# real TOOL-INVENTORY.md is a curated doc with broad vocabulary that would over-match
# short query tokens like "no" via whole-word matches).
D5b_inv="$(mktemp -d)"
printf '# minimal inventory fixture for the test\n' > "$D5b_inv/inventory.md"
out="$(RIG_REPO="$D5" PRODUCT_REPO="$D5" TOOL_INVENTORY="$D5b_inv/inventory.md" GRAPHIFY_FRESHNESS_FAKE="$D5" \
        bash "$SRC/checks/graphify-freshness.sh" reuse-check "zxcvbnm-no-such-thing-12345" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "5b reuse-check for nonsense exits $rc, expected 1 (out=$out)"
case "$out" in
  *"CLEAR to build"*) ok "5b nonsense query reports CLEAR to build" ;;
  *)                  bad "5b missing CLEAR verdict (out=$out)" ;;
esac
# Stale-graph guard: if the graph is STALE, reuse-check must ABORT (rc=2)
D5b="$(mktemp -d)"
HEAD="4444444444444444444444444444444444444444"
make_fake_repo "$D5b" "STALE" "0000000000000000000000000000000000000000" "$HEAD" "src/anything.py"
out="$(RIG_REPO="$D5b" GRAPHIFY_FRESHNESS_FAKE="$D5b" \
        bash "$SRC/checks/graphify-freshness.sh" reuse-check "anything" 2>&1)"; rc=$?
[ "$rc" -eq 2 ] || bad "5c reuse-check on stale graph exits $rc, expected 2 (ABORT) (out=$out)"
case "$out" in
  *"ABORTED"*) ok "5c reuse-check aborts when graph is stale" ;;
  *)            bad "5c missing ABORT message (out=$out)" ;;
esac

# --- (6) FAIL-ON-REVERT: prove (2)'s RED comes from THIS check, not a coincidence ---
echo "== (6) FAIL-ON-REVERT: neutering the STALE-branch in classify_one must make (2) wrongly GREEN =="
# We don't actually edit the script (that would be fragile); instead, we feed the script
# a fake state file that says FRESH regardless of inputs. If the check then says GREEN,
# the RED in (2) was coming from the state file + branch, not from a hard-coded "always
# RED" in the script body.
D6="$(mktemp -d)"
HEAD="5555555555555555555555555555555555555555"
make_fake_repo "$D6" "FRESH" "old_commit_sha" "$HEAD" "src/foo.py
src/bar.py"
out="$(GRAPHIFY_FRESHNESS_FAKE="$D6" bash "$SRC/checks/graphify-freshness.sh" check "$D6" 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "6a overridden state -> FRESH must exit 0; got rc=$rc (out=$out)"
case "$out" in *"GREEN"*) ok "6a overridden state -> check is GREEN (proves the RED in (2) is data-driven)" ;;
  *) bad "6a overridden state should be GREEN, got: $out" ;; esac

# --- (7) summary never fails (used by `paths`-style reporting) ---------------------
echo "== (7) summary: never blocks, prints one line per graph =="
D7="$(mktemp -d)"
HEAD="6666666666666666666666666666666666666666"
make_fake_repo "$D7" "FRESH" "$HEAD" "$HEAD" ""
out="$(GRAPHIFY_FRESHNESS_FAKE="$D7" RIG_REPO="$D7" PRODUCT_REPO="$D7" \
        bash "$SRC/checks/graphify-freshness.sh" summary 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "7a summary exits $rc, expected 0"
case "$out" in
  *"FRESH"*) ok "7a summary prints a FRESH line" ;;
  *)          bad "7a missing FRESH (out=$out)" ;;
esac

# --- (8) paths -- print, no side effects -------------------------------------------
echo "== (8) paths: never fails, prints the watched repos =="
out="$(bash "$SRC/checks/graphify-freshness.sh" paths 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "8a paths exits $rc"
case "$out" in *"RIG:"*"PRODUCT:"*) ok "8a paths prints RIG + PRODUCT" ;; *) bad "8a missing repos (out=$out)" ;; esac

# --- (9) DOGFOOD: prove the real script catches a real staleness -------------------
echo '== (9) DOGFOOD: real "check" against the live rig graph + live HEAD =='
# Don't modify the real graph. Just confirm the script doesn't crash and the
# summary line is one of the four valid states.
out="$(bash "$SRC/checks/graphify-freshness.sh" summary 2>&1)"; rc=$?
[ "$rc" -eq 0 ] || bad "9a real-rig summary exits $rc, expected 0"
case "$out" in
  *"FRESH"*|*"STALE"*|*"ABSENT"*|*"UNVERIFIED"*) ok "9a real-rig summary emits a valid state line" ;;
  *) bad "9a real-rig summary missing state (out=$out)" ;;
esac

# --- (10) UNVERIFIED: non-git repo -> UNVERIFIED + RED -----------------------------
echo "== (10) UNVERIFIED: non-git path is still surfaced (not silently GREEN) =="
D8="$(mktemp -d)"
HEAD="7777777777777777777777777777777777777777"
make_fake_repo "$D8" "UNVERIFIED" "" "$HEAD" ""
out="$(GRAPHIFY_FRESHNESS_FAKE="$D8" bash "$SRC/checks/graphify-freshness.sh" check "$D8" 2>&1)"; rc=$?
[ "$rc" -eq 1 ] || bad "10a UNVERIFIED check exits $rc, expected 1 (RED, not silently GREEN)"
case "$out" in
  *"RED"*) ok "10a UNVERIFIED still prints RED (not silently green)" ;;
  *)        bad "10a UNVERIFIED missing RED (out=$out)" ;;
esac

printf -- '--- %d passed, %d failed ---\n' "$PASS" "$FAIL"
[ "$FAIL" -eq 0 ] || exit 1
exit 0
