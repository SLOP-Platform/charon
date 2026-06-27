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
#   - WCI ENFORCER (mechanizes work-composition-intelligence; see WORKFLOW.md §WCI):
#     HARD-FAILs on an unjustified disjoint-owns dep (false-blocking-dep) and on two
#     live tickets with an identical owns set (redundancy). Semantic intent is
#     ADVISORY only (`WCI-ADVISORY`), never a failure. Owns-collision among concurrent
#     claims is check 4 above (reused, not duplicated).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
exec python3 - "$FLEET" <<'PY'
import sys, glob, os, re, fnmatch
fleet = sys.argv[1]
board = os.path.join(fleet, "board")
def field(path, key):
    for line in open(path):
        if line.startswith(key + ":"):
            return line.split(":", 1)[1].strip()
    return ""
def markers(path):
    # WCI dep-justification markers (see WORKFLOW.md §WCI):
    #   real-dep: <DEP-ID> <reason>   -> justifies a disjoint-owns dep on that ID
    #   dep-kind: build               -> all of this ticket's deps are real build-deps
    just, blanket = set(), False
    for line in open(path):
        s = line.strip()
        if s.lower().startswith("real-dep:"):
            rest = s.split(":", 1)[1].strip().split()
            if rest:
                just.add(rest[0].rstrip(",").lower())
        elif s.lower().startswith("dep-kind:"):
            if s.split(":", 1)[1].strip().lower() == "build":
                blanket = True
    return just, blanket
tickets = {}
for f in sorted(glob.glob(os.path.join(board, "*.md"))):
    tid = os.path.basename(f)[:-3]
    just, depbuild = markers(f)
    tickets[tid] = {
        "prompt": field(f, "prompt"),
        "branch": field(f, "branch"),
        "deps": [d.strip() for d in field(f, "depends_on").split(",") if d.strip()],
        "owns": [o.strip() for o in field(f, "owns").split(",") if o.strip()],
        "just": just,
        "depbuild": depbuild,
    }
ids = {t.lower(): t for t in tickets}
red, info, wci = [], [], []

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

# ===== WCI ENFORCER (work-composition-intelligence, mechanized) =====
# HARD-FAIL on deterministic violations; semantic judgment is ADVISORY only.
# owns-collision among concurrent claims = check 4 above (reused, not duplicated).
def owns_overlap(a, b):  # any shared path or glob match either direction
    for pa in a:
        for pb in b:
            if pa == pb or fnmatch.fnmatch(pa, pb) or fnmatch.fnmatch(pb, pa):
                return True
    return False

# WCI-1. False-blocking dep: a live ticket depends_on X but their owns are
# DISJOINT and the dep is not justified as a real build/correctness prereq.
# (disjoint owns != a dependency — a disjoint dep must be JUSTIFIED, not assumed.)
# Only live (not-done) dependents matter: a done ticket's dep blocks nothing now.
for t, d in tickets.items():
    if is_done(t):
        continue
    for dep in d["deps"]:
        x = ids.get(dep.lower())
        if not x or owns_overlap(d["owns"], tickets[x]["owns"]):
            continue  # bad-dep caught above; shared owns => plausibly a real dep
        if d["depbuild"] or dep.lower() in d["just"]:
            wci.append(f"justified-disjoint-dep (ok): {t} -> {x} (marked real build/correctness prereq)")
        else:
            red.append(f"WCI false-blocking-dep: {t} depends_on {x} but their owns are DISJOINT and "
                       f"the dep is UNJUSTIFIED — add 'real-dep: {x} <reason>' (or 'dep-kind: build') "
                       f"if it is a true build/correctness prereq, else DROP the dep (merge-order only)")

# WCI-2. Redundancy: two live tickets declaring the IDENTICAL non-empty owns set
# (likely duplicate/contradictory work). Same-branch duplicates = check 3 above.
live = sorted(t for t in tickets if not is_done(t))
for i, a in enumerate(live):
    for b in live[i+1:]:
        oa, ob = set(tickets[a]["owns"]), set(tickets[b]["owns"])
        if oa and oa == ob:
            red.append(f"WCI redundancy: {a} and {b} declare the IDENTICAL owns set "
                       f"({', '.join(sorted(oa))}) — likely duplicate/contradictory work")

# Semantic intent (contradictory prompts, hidden coupling) is NOT machine-checkable
# in bash — surfaced as advisory only, never a failure.
if any(d["deps"] for d in tickets.values()):
    wci.append("semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked "
               "— eyeball overlapping or dep-linked tickets by hand.")

print("== validate_board ==")
for i in info:  print(f"  INFO {i}")
for w in wci:   print(f"  WCI-ADVISORY {w}")
for r in red:   print(f"  RED  {r}")
print("  GREEN board structurally valid" if not red else f"  RED  {len(red)} issue(s) — fix before launching")
sys.exit(1 if red else 0)
PY
