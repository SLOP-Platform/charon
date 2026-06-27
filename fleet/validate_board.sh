#!/usr/bin/env bash
# validate_board.sh — PREFLIGHT GATE. Run before launching ANY wave / opening tabs.
# Exit 0 = GREEN (safe to launch).  Exit 1 = RED (fix before launching).
#
# Rewritten 2026-06-27 (audit THEME 2): the previous version printed "REVIEW" but
# NEVER set the failure flag (and did so inside a `| while` subshell), so it exited
# GREEN on the very double-claim it was built to catch. This version:
#   - fails RED on: missing prompt; bad depends_on; duplicate branch; an owned path
#     shared by two tickets with NO transitive dep ordering (genuine concurrent
#     collision); a state/ marker that matches no board ticket (case-orphan).
#   - reports INFO (non-failing) for: transitively-sequenced shared paths (hand-offs);
#     glob owns (`*`) that can't be exactly partitioned.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 - "$FLEET" <<'PY'
import sys, glob, os, re
fleet = sys.argv[1]
board = os.path.join(fleet, "board")
def field(path, key):
    for line in open(path):
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return ""
tickets = {}
for f in sorted(glob.glob(os.path.join(board, "*.md"))):
    tid = os.path.basename(f)[:-3]
    tickets[tid] = {
        "prompt": field(f, "prompt"),
        "branch": field(f, "branch"),
        "deps": [d.strip() for d in field(f, "depends_on").split(",") if d.strip()],
        "owns": [o.strip() for o in field(f, "owns").split(",") if o.strip()],
    }
ids = {t.lower(): t for t in tickets}
red, info = [], []

# 1. prompt files exist
for t, d in tickets.items():
    if d["prompt"] and not os.path.exists(d["prompt"]):
        red.append(f"missing-prompt: {t} -> {d['prompt']}")

# 2. depends_on valid
for t, d in tickets.items():
    for dep in d["deps"]:
        if dep.lower() not in ids:
            red.append(f"bad-dep: {t} depends_on '{dep}' (no such ticket)")

# 3. duplicate branches
seen = {}
for t, d in tickets.items():
    seen.setdefault(d["branch"], []).append(t)
for b, ts in seen.items():
    if b and len(ts) > 1:
        red.append(f"dup-branch: {b} <- {' '.join(ts)}")

# transitive reachability over depends_on edges
def reaches(a, b, _seen=None):
    _seen = _seen or set()
    if a in _seen: return False
    _seen.add(a)
    for dep in tickets.get(a, {}).get("deps", []):
        dl = ids.get(dep.lower())
        if dl == b or reaches(dl, b, _seen): return True
    return False
def ordered(a, b):  # one runs strictly before the other?
    return reaches(a, b) or reaches(b, a)
def is_done(t):
    return os.path.exists(os.path.join(fleet, "state", "done", t))

# 4. owns partition. A collision is only a LAUNCH RISK if >=2 of the owners are
# not-done (could still run concurrently). Done/done or done/live pairs already
# sequenced by merge order -> historical, reported INFO not RED.
path_owners = {}
for t, d in tickets.items():
    for p in d["owns"]:
        path_owners.setdefault(p, []).append(t)
for p, owners in sorted(path_owners.items()):
    if len(owners) < 2: continue
    if "*" in p:
        info.append(f"glob-owns (can't partition, verify by hand): {p} <- {' '.join(owners)}")
        continue
    live = [o for o in owners if not is_done(o)]
    unsequenced = [(a, b) for i, a in enumerate(live) for b in live[i+1:] if not ordered(a, b)]
    if len(live) >= 2 and unsequenced:
        pairs = ", ".join(f"{a}|{b}" for a, b in unsequenced)
        red.append(f"owns-collision LIVE (no dep ordering): {p} <- {' '.join(live)}  [{pairs}]")
    else:
        tag = "all-done" if not live else "dep-sequenced/historical"
        info.append(f"owns hand-off ({tag}, ok): {p} <- {' '.join(owners)}")

# 5. state markers must match a board ticket exactly (catches case-orphans)
for sub in ("claims", "submitted", "done"):
    for m in glob.glob(os.path.join(fleet, "state", sub, "*")):
        mid = os.path.basename(m)
        if mid not in tickets:
            red.append(f"orphan-marker: state/{sub}/{mid} matches no board ticket")

print("== validate_board ==")
for i in info:  print(f"  INFO {i}")
for r in red:   print(f"  RED  {r}")
print("  GREEN board structurally valid" if not red else f"  RED  {len(red)} issue(s) — fix before launching")
sys.exit(1 if red else 0)
PY
