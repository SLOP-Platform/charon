#!/usr/bin/env bash
# code-map.sh — query-scoped Mermaid code-map generator.
#
# Reads graphify's graph.json (already live, refreshed on every land) and the board
# (ticket state + owns:) to emit a Mermaid subgraph annotated with ownership status.
#
# Usage: code-map.sh <query> [--depth N] [--whole-graph]
#   query         file path, symbol name, or ticket id to centre on
#   --depth N     neighbourhood depth (default 1)
#   --whole-graph emit the full graph (explicit opt-in; default is query-scoped)
#
# Env seams (hermetic overrides for testing):
#   CODE_MAP_GRAPH=<path>  graph.json (default: graphify-out/graph.json)
#   CODE_MAP_BOARD=<path>  board dir (default: <FLEET>/board)
#   CODE_MAP_STATE=<path> state dir (default: <FLEET>/state)
set -uo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
GRAPH_FILE="${CODE_MAP_GRAPH:-$FLEET/../graphify-out/graph.json}"
BOARD_DIR="${CODE_MAP_BOARD:-$FLEET/board}"
STATE_DIR="${CODE_MAP_STATE:-$FLEET/state}"

DEPTH=1
WHOLE_GRAPH=0
QUERY=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --depth)      DEPTH="${2:-}"; shift 2 || exit 1 ;;
    --whole-graph) WHOLE_GRAPH=1; shift ;;
    -h|--help)   echo "Usage: $0 <query> [--depth N] [--whole-graph]"; exit 0 ;;
    -*)           echo "Unknown option: $1" >&2; exit 1 ;;
    *)            QUERY="$1"; shift ;;
  esac
done

if [[ -z "$QUERY" && "$WHOLE_GRAPH" != 1 ]]; then echo "Usage: $0 <query> [--depth N] [--whole-graph]" >&2; exit 1; fi
[[ -z "$QUERY" ]] && QUERY=""

python3 - "$GRAPH_FILE" "$BOARD_DIR" "$STATE_DIR" "$DEPTH" "$WHOLE_GRAPH" "$QUERY" << 'PYEOF'
import json, sys, os, re
from collections import deque

GRAPH_FILE = sys.argv[1]
BOARD_DIR  = sys.argv[2]
STATE_DIR  = sys.argv[3]
DEPTH      = int(sys.argv[4])
WHOLE      = int(sys.argv[5])
QUERY      = sys.argv[6]

# ── board helpers ───────────────────────────────────────────────────────────────

def owning_ticket(source_file):
    if not source_file:
        return None, None
    owners = []
    for fname in os.listdir(BOARD_DIR):
        if not fname.endswith('.md'):
            continue
        tid = fname[:-3]
        path = os.path.join(BOARD_DIR, fname)
        with open(path) as fh:
            content = fh.read()
        m = re.search(r'^owns:(.+)$', content, re.MULTILINE)
        if not m:
            continue
        for pat in m.group(1).split():
            pat = pat.strip().strip(',')
            if not pat:
                continue
            fn = os.path.basename(pat)
            if fn and fn in source_file:
                owners.append(tid)
                break
    if not owners:
        return None, None
    owners.sort()
    state = ticket_state(owners[0])
    return ','.join(owners), state

def ticket_state(tid):
    for st, subdir in [('done', 'done'), ('submitted', 'submitted'), ('claimed', 'claims')]:
        p = os.path.join(STATE_DIR, subdir, tid)
        if os.path.exists(p):
            if subdir == 'claims':
                with open(p) as fh:
                    who = fh.read().strip().split()[0]
                return f'claimed:{who}'
            return st
    dep_path = os.path.join(BOARD_DIR, f'{tid}.md')
    if os.path.exists(dep_path):
        with open(dep_path) as fh:
            if re.search(r'^depends_on:', fh.read(), re.MULTILINE):
                return 'blocked'
    return 'ready'

def escape_mermaid(s):
    for old, new in [('\\', '\\\\'),('"', '\\"'),('<', '&lt;'),('>', '&gt;'),('(', '\\('),(')', '\\)')]:
        s = s.replace(old, new)
    return s

def safe_id(s):
    return re.sub(r'[^a-zA-Z0-9_]', '_', str(s))

STATE_COLOUR = {
    'done':      '#90EE90',
    'submitted': '#ADD8E6',
    'blocked':   '#FFB6C1',
    'ready':     '#98FB98',
}
STATE_CLASS = {
    'done':      'done',
    'submitted': 'submitted',
    'blocked':   'blocked',
    'ready':     'ready',
}

# ── load graph ─────────────────────────────────────────────────────────────────

with open(GRAPH_FILE) as fh:
    graph = json.load(fh)

node_map  = {n['id']: n for n in graph['nodes']}
link_map = {}
for link in graph['links']:
    link_map.setdefault(link['source'], []).append(link)
    link_map.setdefault(link['target'], []).append(link)

# ── find seed nodes ────────────────────────────────────────────────────────────

if WHOLE:
    seeds = {n['id'] for n in graph['nodes']}
else:
    q = QUERY.lower()
    seeds = set()
    for n in graph['nodes']:
        sf = n.get('source_file') or ''
        lbl = n.get('label') or ''
        if q in sf.lower() or q in lbl.lower():
            seeds.add(n['id'])
    if not seeds:
        print("No nodes match query: " + QUERY, file=sys.stderr)
        sys.exit(1)

# ── BFS ────────────────────────────────────────────────────────────────────────

visited = {}   # id -> dist
queue   = deque((sid, 0) for sid in seeds)
for sid in seeds:
    visited[sid] = 0

while queue:
    cid, dist = queue.popleft()
    if dist >= DEPTH:
        continue
    for link in link_map.get(cid, []):
        for t in [link['source'], link['target']]:
            if t == cid:
                continue
            if t not in visited or visited[t] > dist + 1:
                visited[t] = dist + 1
                queue.append((t, dist + 1))

# ── emit subgraph ───────────────────────────────────────────────────────────────

nodes_out = [(nid, visited[nid], node_map[nid]) for nid in visited if nid in node_map]
links_out = []
seen = set()
for nid in visited:
    for link in link_map.get(nid, []):
        s, t = link['source'], link['target']
        if s in visited and t in visited:
            key = tuple(sorted([s, t]))
            if key not in seen:
                seen.add(key)
                links_out.append(link)

# ── render Mermaid ─────────────────────────────────────────────────────────────

print("```mermaid")
print("flowchart LR")

for nid, dist, node in sorted(nodes_out, key=lambda x: x[1]):
    sf    = node.get('source_file') or ''
    label = node.get('label') or '?'
    sid   = safe_id(nid)
    owner, state = owning_ticket(sf)

    colour = STATE_COLOUR.get(state, '#D3D3D3')
    cls    = STATE_CLASS.get(state, 'unowned')

    suffix = f' [{owner}/{state}]' if owner else ' [unowned]'
    if dist > 0:
        suffix += f' (d{dist})'

    elabel = escape_mermaid(label)
    print(f'  {sid}("{elabel}{suffix}"):::{cls}')
    print(f'  style {sid} fill:{colour}')

for link in links_out:
    s, t   = safe_id(link['source']), safe_id(link['target'])
    rel    = escape_mermaid(link.get('relation') or '')
    if rel:
        print(f'  {s} -->|"{rel}"| {t}')
    else:
        print(f'  {s} --> {t}')

print("  classDef done fill:#90EE90")
print("  classDef submitted fill:#ADD8E6")
print("  classDef claimed fill:#FFD700")
print("  classDef blocked fill:#FFB6C1")
print("  classDef ready fill:#98FB98")
print("  classDef unowned fill:#D3D3D3")
print("```")
PYEOF
