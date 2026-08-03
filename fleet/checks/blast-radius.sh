#!/usr/bin/env bash
# blast-radius.sh — query the live code graph for a file/symbol's blast radius.
#
# THE DEFECT THIS FIXES (PRIORITY-TODO A5): `graphify explain` and `graphify path`
# have zero invocations across the entire rig — the graph is kept fresh (via
# graphify-freshness.sh wired into every preflight), but nobody ever asks it a
# question. This wrapper turns a changed-file list into an actionable blast-radius
# report.
#
# DESIGN:
#   - Read-only: never calls `graphify update`. Freshness is graphify-freshness.sh's
#     job and duplicating it would fork the freshness contract.
#   - FAIL SOFT, LOUD: a missing graph, missing binary, or unknown node prints WHY and
#     exits cleanly — never wedges reuse-check.sh. "no answer" and "no impact" are
#     DISTINGUISHABLE (two distinct messages).
#   - OUTPUT: additively appended to reuse-check output; never dominates it.
#   - ENV: BLAST_RADIUS=0 suppresses the section entirely (hermetic / no-graph cases).
#
# USAGE (used internally by fleet/reuse-check.sh):
#   blast-radius.sh [repo-root] [changed-files...]
#
#   repo-root       — repo to query (default: /home/stack/code/charon)
#   changed-files   — files to query blast radius for (default: none; caller passes them)
#
#   GRAPHIFY_BIN    — override graphify binary (default: graphify)
#   BLAST_GRAPH     — override graph.json path (default: <repo>/graphify-out/graph.json)
#   BLAST_RADIUS    — set to 0 to suppress this section entirely
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

PRODUCT_REPO_DEFAULT="/home/stack/code/charon"
GRAPHIFY_BIN="${GRAPHIFY_BIN:-graphify}"
BLAST_GRAPH="${BLAST_GRAPH:-}"
BLAST_RADIUS="${BLAST_RADIUS:-1}"

_main(){
  if [ "$BLAST_RADIUS" = "0" ]; then
    echo "blast-radius: BLAST_RADIUS=0 — suppressed"
    return 0
  fi

  local repo="${1:-$PRODUCT_REPO_DEFAULT}"
  shift || true
  local graph_path="${BLAST_GRAPH:-${repo}/graphify-out/graph.json}"

  if ! command -v "$GRAPHIFY_BIN" >/dev/null 2>&1; then
    echo "blast-radius: SKIP — graphify not found at '$GRAPHIFY_BIN' (not installed)"
    return 0
  fi

  if [ ! -f "$graph_path" ]; then
    echo "blast-radius: SKIP — no graph at '$graph_path' (run: graphify update $repo)"
    return 0
  fi

  local nodes=()
  if [ $# -gt 0 ]; then
    nodes=("$@")
  else
    echo "blast-radius: nothing to query — no files passed and no diff read"
    return 0
  fi

  python3 - <<'PY' "$graph_path" "${nodes[@]}"
import json, sys
path = sys.argv[1]
nodes = sys.argv[2:]
try:
    d = json.load(open(path))
except Exception as e:
    print("blast-radius: GRAPH_READ_ERROR — failed to read %s: %s" % (path, e))
    sys.exit(0)
edges = d.get("edges", [])
node_map = {n.get("id",""): n for n in d.get("nodes", [])}
node_ids = set(node_map.keys())
for node in nodes:
    target_id = None
    if node in node_ids:
        target_id = node
    else:
        nl = node.lower()
        for nid in node_ids:
            if not nid:
                continue
            n = node_map[nid]
            if nl in nid.lower() or nl in n.get("norm_label","").lower() or nl in n.get("label","").lower():
                target_id = nid
                break
        if target_id is None:
            for nid in node_ids:
                src = node_map.get(nid, {}).get("source_file","")
                if src and node in src:
                    target_id = nid
                    break
    if target_id is None:
        print("blast-radius: NODE_NOT_FOUND — '%s' not in graph (%d nodes scanned)" % (node, len(node_ids)))
        continue
    target_node = node_map[target_id]
    target_label = target_node.get("label", target_id)
    dependents = []
    dependencies = []
    for e in edges:
        if e.get("to","") == target_id:
            src_id = e.get("from","")
            src = node_map.get(src_id, {})
            dependents.append((e.get("kind", e.get("type","import")), src.get("label", src_id), src.get("source_file","")))
        if e.get("from","") == target_id:
            dst_id = e.get("to","")
            dst = node_map.get(dst_id, {})
            dependencies.append((e.get("kind", e.get("type","import")), dst.get("label", dst_id), dst.get("source_file","")))
    print("blast-radius: TARGET=%s id=%s" % (target_label, target_id))
    print("  DIRECT_DEPENDENTS: %d" % len(dependents))
    for kind, lbl, sf in sorted(dependents, key=lambda x: x[1]):
        print("    %s :: %s (%s)" % (kind, lbl, sf))
    print("  DIRECT_DEPENDENCIES: %d" % len(dependencies))
    for kind, lbl, sf in sorted(dependencies, key=lambda x: x[1]):
        print("    %s :: %s (%s)" % (kind, lbl, sf))
    if len(dependents) == 0 and len(dependencies) == 0:
        print("blast-radius: NO_CONNECTIONS — '%s' has no graph edges" % target_label)
    else:
        print("blast-radius: AFFECTED — %d direct dependents, %d direct dependencies" % (len(dependents), len(dependencies)))
PY
}

case "${1:-}" in
  -h|--help|help|"")
    cat <<EOF
blast-radius.sh — query the live code graph for a file/symbol's blast radius.

Usage:
  $0 [repo-root] [changed-files...]

  repo-root       — repo to query (default: $PRODUCT_REPO_DEFAULT)
  changed-files   — files to query blast radius for (default: none; caller passes them)

Env:
  BLAST_RADIUS=0 — suppress the blast-radius section entirely
  BLAST_GRAPH=<path> — override graph.json path
  GRAPHIFY_BIN=<path> — override graphify binary

Exit: always 0 (advisory output; never wedges reuse-check.sh)
EOF
    ;;
  *)
    _main "$@"
    ;;
esac
