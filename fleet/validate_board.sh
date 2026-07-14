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
import sys, glob, os, re, fnmatch, subprocess
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
        "work_class": field(f, "work_class"),
        "difficulty": field(f, "difficulty"),
        "note": field(f, "note"),
        "parked_field": field(f, "parked"),
        "build_after": field(f, "build-after"),
        "repo": field(f, "repo"),
        "just": just,
        "depbuild": depbuild,
    }
ids = {t.lower(): t for t in tickets}
# .md.parked files are NOT scanned as tickets, but build-after may reference them.
parked_files = {os.path.basename(f)[:-len(".md.parked")].lower()
                for f in glob.glob(os.path.join(board, "*.md.parked"))}
# DONE tickets are retired off the active board (board/archive/ via retire-done.sh) but
# remain valid depends_on targets — a dependency satisfied by COMPLETED work is satisfied,
# not "no such ticket". Without this, archiving done tickets would falsely red every active
# ticket that depends on shipped work.
done_ids = {os.path.basename(f).lower()
            for f in glob.glob(os.path.join(fleet, "state", "done", "*"))}
# Retired tickets live in board/archive/ — a valid (non-orphan) home for a done marker.
archived_ids = {os.path.basename(f)[:-3].lower()
                for f in glob.glob(os.path.join(board, "archive", "*.md"))}

def is_parked(d):
    # Matches claim.sh's park rule EXACTLY: explicit `parked: true` field OR a `note:`
    # whose text contains PARKED. A parked ticket is staged, not live.
    return (d["parked_field"].strip().lower() in ("true", "yes", "1")
            or "PARKED" in d["note"].upper())
red, info, wci, warn = [], [], [], []
# Product repo root — owns paths are either absolute (rig paths under /home/stack/...) or
# RELATIVE to the product working tree. Used by the owns-path existence check (WARN only)
# and by the uncommitted-work check (#6). Overridable via CHARON_REPO (self-tests point it
# at an isolated fixture; default preserves the live path exactly).
PRODUCT_REPO = os.environ.get("CHARON_REPO", "/home/stack/code/charon")

# MULTI-REPO: a ticket may name a target repo via `repo:` (see fleet/repo-registry.sh). Map the
# accepted keys to their checkout roots so owns-paths resolve against the RIGHT tree and an
# unknown key fails RED. Absent field -> "charon" (product) => unchanged behavior (back-compat).
REPO_ROOTS = {
    "charon": PRODUCT_REPO, "product": PRODUCT_REPO,
    "keystone": "/home/stack/code/keystone", "ksf": "/home/stack/code/keystone",
    "charon-private": "/home/stack/charon-private", "rig": "/home/stack/charon-private",
    "fleet": "/home/stack/charon-private",
}
def repo_root(d):
    return REPO_ROOTS.get((d["repo"].strip().lower() or "charon"), PRODUCT_REPO)

# 0. repo: field must name a known repo (else the harness can't resolve it). Live tickets only.
for t, d in tickets.items():
    key = d["repo"].strip().lower()
    if key and key not in REPO_ROOTS and not is_parked(d):
        red.append(f"unknown-repo: {t} repo '{d['repo']}' is not one of "
                   f"{', '.join(sorted(REPO_ROOTS))} (see fleet/repo-registry.sh)")

# 1. prompt files exist
for t, d in tickets.items():
    if is_parked(d):
        continue  # a parked ticket may legitimately not have its prompt written yet
    if d["prompt"] and not os.path.exists(d["prompt"]):
        red.append(f"missing-prompt: {t} -> {d['prompt']}")

# 2. depends_on valid — a dangling dep id (references no live/done/archived ticket) is a
# HARD FAIL: the sequencing it encodes can never be satisfied. (Correctness check b.)
for t, d in tickets.items():
    for dep in d["deps"]:
        if dep.lower() not in ids and dep.lower() not in done_ids and dep.lower() not in archived_ids and dep.lower() not in parked_files:
            red.append(f"bad-dep: {t} depends_on '{dep}' (no such ticket)")

# 2c. self-dependency — a ticket that depends_on itself can never be scheduled. HARD FAIL.
# (Slips past check 2 because the id DOES resolve — to itself. Correctness check c.)
for t, d in tickets.items():
    for dep in d["deps"]:
        if dep.lower() == t.lower():
            red.append(f"self-dep: {t} depends_on itself — a ticket cannot block on itself; drop the self-reference")

# 2d. dependency cycles — a cycle in the depends_on graph is unschedulable (every ticket
# in it waits on another). HARD FAIL, and name the cycle. DFS with a GRAY (on-stack) /
# BLACK (done) colouring; only edges to KNOWN board tickets (ids) are followed — a dep to a
# done/archived/dangling id is terminal (no outgoing edges), so it can never form a cycle.
# Self-deps are skipped here (reported by 2c) so the cycle names are genuine ≥2-node loops.
# (Correctness check d.)
_WHITE, _GRAY, _BLACK = 0, 1, 2
_color = {t: _WHITE for t in tickets}
_cycles_seen = set()
def _walk(node, stack):
    _color[node] = _GRAY
    stack.append(node)
    for dep in tickets[node]["deps"]:
        nxt = ids.get(dep.lower())
        if nxt is None or nxt == node:
            continue  # dangling (check 2) / done-archived terminal / self-dep (check 2c)
        if _color[nxt] == _GRAY:
            i = stack.index(nxt)
            cyc = stack[i:] + [nxt]           # e.g. A -> B -> C -> A
            key = frozenset(cyc)
            if key not in _cycles_seen:
                _cycles_seen.add(key)
                red.append("dep-cycle: " + " -> ".join(cyc) +
                           " — depends_on forms an unschedulable loop; break it")
        elif _color[nxt] == _WHITE:
            _walk(nxt, stack)
    stack.pop()
    _color[node] = _BLACK
for _t in list(tickets):
    if _color[_t] == _WHITE:
        _walk(_t, [])

# 2b. work_class required + valid (capability/assign.py's auto-resolve source; see D&S
# standing rule precedent below — same "every LIVE ticket must self-document" discipline,
# same not-scanned-so-exempt treatment for .md.parked via the "*.md" glob above).
sys.path.insert(0, os.path.join(fleet, "capability"))
try:
    from grades import WORK_CLASSES, GENERALIST  # type: ignore
    _VALID_WORK_CLASSES = set(WORK_CLASSES) | {GENERALIST}
except Exception as e:
    _VALID_WORK_CLASSES = None
    red.append(f"work-class-check-failed: could not import capability/grades.py — {e}")
if _VALID_WORK_CLASSES is not None:
    for t, d in tickets.items():
        if is_parked(d):
            continue  # parked = staged, not live; exempt from the live-ticket work_class gate
        wc = d["work_class"]
        if not wc:
            red.append(f"work-class-missing: {t} has no 'work_class:' field "
                       f"(required — one of: {', '.join(sorted(_VALID_WORK_CLASSES))})")
        elif wc not in _VALID_WORK_CLASSES:
            red.append(f"work-class-invalid: {t} work_class '{wc}' is not one of "
                       f"{', '.join(sorted(_VALID_WORK_CLASSES))}")

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
def inactive(t):
    # Not live: already done OR staged/parked. Both are exempt from the "live ticket must be
    # fully claimable" checks (work_class, D&S, owns-collision, WCI, missing-prompt) — a
    # parked ticket may legitimately have an unwritten prompt / provisional owns.
    return is_done(t) or is_parked(tickets[t])

# 2e. difficulty required (1-5) for every live ticket. The difficulty ordinal captures
# estimated effort/complexity — auto-seeded from tier (economy=1 … frontier=5), manually
# refined as purpose clarifies. D&S standing-rule precedent (§2b above): same mandatory
# self-document discipline, same not-scanned-so-exempt for .md.parked.
for t, d in tickets.items():
    if inactive(t):
        continue
    diff_raw = d["difficulty"]
    if not diff_raw:
        red.append(f"difficulty-missing: {t} has no 'difficulty:' field "
                   f"(required — integer 1-5, auto-seeded from tier)")
    else:
        try:
            diff_val = int(diff_raw.split(None, 1)[0])
            if diff_val < 1 or diff_val > 5:
                red.append(f"difficulty-invalid: {t} difficulty '{diff_raw}' "
                           f"is outside 1-5 range (got {diff_val})")
        except (ValueError, IndexError):
            red.append(f"difficulty-invalid: {t} difficulty '{diff_raw}' "
                       f"is not a valid integer 1-5")

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
    live = [o for o in owners if not inactive(o)]
    unsequenced = [(a, b) for i, a in enumerate(live) for b in live[i+1:] if not ordered(a, b)]
    if len(live) >= 2 and unsequenced:
        pairs = ", ".join(f"{a}|{b}" for a, b in unsequenced)
        red.append(f"owns-collision LIVE (no dep ordering): {p} <- {' '.join(live)}  [{pairs}]")
    else:
        tag = "all-done" if not live else "dep-sequenced/historical"
        info.append(f"owns hand-off ({tag}, ok): {p} <- {' '.join(owners)}")

# 4b. owns paths should exist. WARN ONLY (never RED): owns may legitimately name a
# not-yet-created file, a directory, a glob, or (for design-first tickets) prose. A path
# is resolved absolute-as-is, else RELATIVE to the product repo; a glob (`*`) that matches
# nothing is a soft warning. Prose entries (whitespace / leading `(`) are skipped — they
# aren't paths. Correctness check a; deliberately non-blocking so it can NEVER false-block a
# preflight. Only live tickets are checked (parked/done may carry provisional owns).
for t, d in tickets.items():
    if inactive(t):
        continue
    for p in d["owns"]:
        if not p or " " in p or "\t" in p or p.startswith("("):
            continue  # prose / descriptive owns, not a real path
        base = p if os.path.isabs(p) else os.path.join(repo_root(d), p)
        if "*" in p or "?" in p or "[" in p:
            if not glob.glob(base):
                warn.append(f"owns-glob-empty: {t} owns '{p}' matches no path (yet) — verify")
        elif not os.path.exists(base):
            warn.append(f"owns-path-missing: {t} owns '{p}' does not exist (yet) — verify it "
                        f"is a to-be-created file or a typo")

# 5. state markers must match a board ticket exactly (catches case-orphans)
for sub in ("claims", "submitted", "done"):
    for m in glob.glob(os.path.join(fleet, "state", sub, "*")):
        mid = os.path.basename(m)
        # a done marker whose ticket has been retired to board/archive/ is NOT an orphan
        if sub == "done" and mid.lower() in archived_ids:
            continue
        if mid not in tickets:
            red.append(f"orphan-marker: state/{sub}/{mid} matches no board ticket")

# 5b. project-membership gate (PROJECT-MEMBERSHIP-GATE, ticket F43). Operator rule
# 2026-07-10: every new ticket folds into one of the existing Projects; a new Project
# needs a strong case + a re-analysis. Mechanize it: every LIVE (non-parked, non-done,
# non-archived) board ticket MUST be present as a row in state/ROADMAP.tsv — i.e. be
# folded into a Project. A ticket is "folded" iff some ROADMAP row matches it. Match
# rule is intentionally tolerant of the two pre-existing id conventions: (a) short id
# (col 2) — e.g. ROADMAP uses `R43` for `board/R43-WIRING-AUDIT.md`, and (b) long
# basename (col 2) — the F43-style row this gate promotes. We accept EITHER:
#   - ROADMAP row's id column == board basename, OR
#   - ROADMAP row's name column (col 5, case-insensitive) == basename lowercased.
# This means a new row can be added in either form and the gate will be satisfied —
# the operator can re-shape the ROADMAP without re-ticketing the gate. A ticket whose
# ticket-id in the board is the LONG form (e.g. A1-LAND-GATE) gets a row whose `id`
# column equals A1-LAND-GATE; the older short-id rows (e.g. R43) continue to match
# their board basenames via the name column. Parked/retired/done tickets are exempt:
# a parked ticket is staged, not live; done lives in state/done/; archive/retired are
# not scanned at all. Backed by ticket PROJECT-MEMBERSHIP-GATE (accept: "Fail-on-
# revert: add a live ticket absent from ROADMAP.tsv -> validate_board non-zero; add
# its row -> green"). The orphan-direction of the gate (a state marker with no board
# ticket) is check 5 above; this is the ticket-direction (a board ticket with no
# state-marker row in ROADMAP).
_roadmap = os.path.join(fleet, "state", "ROADMAP.tsv")
_rm_id, _rm_name_lc = set(), set()
if os.path.exists(_roadmap):
    for _rl in open(_roadmap):
        if not _rl.strip() or _rl.lstrip().startswith("#"):
            continue
        _f = _rl.rstrip("\n").split("\t")
        if len(_f) >= 5:
            _rm_id.add(_f[1].strip())
            _rm_name_lc.add(_f[4].strip().lower())
for t, d in tickets.items():
    if inactive(t):
        continue
    _bn = t
    _bn_lc = _bn.lower()
    if _bn in _rm_id or _bn_lc in _rm_name_lc:
        continue
    red.append(f"project-membership-missing: {t} is a LIVE ticket with no row in "
               f"state/ROADMAP.tsv — not folded into a Project. Add a row to "
               f"state/ROADMAP.tsv (id={t} or name={_bn_lc}) with a project/wave, "
               f"or park/retire the ticket.")

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
    if inactive(t):
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
live = sorted(t for t in tickets if not inactive(t))
for i, a in enumerate(live):
    for b in live[i+1:]:
        oa, ob = set(tickets[a]["owns"]), set(tickets[b]["owns"])
        if oa and oa == ob:
            red.append(f"WCI redundancy: {a} and {b} declare the IDENTICAL owns set "
                       f"({', '.join(sorted(oa))}) — likely duplicate/contradictory work")

# ===== PARK consistency (claim-loop root cause, 2026-07-09) =====
# The claim -> no-commit -> release -> re-claim spin happened because BENCH-OOB-GRADING was
# PARKED (note: PARKED) but had NO clean signal claim.sh honored and NO state marker, so it
# was offered forever. Enforce that parked tickets are represented so claim.sh + validator +
# humans agree, and that build-after sequencing (which claim.sh does NOT enforce) can't let a
# ticket be claimed ahead of its predecessor.
for t, d in tickets.items():
    if is_done(t):
        continue
    parked = is_parked(d)
    # PARK-1: a parked ticket must not also hold an active claim (a droid claimed a parked
    # ticket — the exact runtime symptom of the loop). PARKED-but-claimable made concrete.
    if parked and os.path.exists(os.path.join(fleet, "state", "claims", t)):
        red.append(f"parked-but-claimed: {t} is PARKED yet has an active state/claims/{t} "
                   f"marker — a droid claimed a parked ticket (claim-loop risk). Release it "
                   f"(fleet/release.sh {t}) or un-park the ticket.")
    # PARK-2: parked-by-note-only is fragile (a prose typo silently un-parks it). Require the
    # explicit `parked: true` field so claim.sh + validator + humans all agree. This is the
    # exact inconsistency that caused the loop (BENCH-OOB relied on note text alone).
    if parked and d["parked_field"].strip().lower() not in ("true", "yes", "1"):
        red.append(f"parked-note-only: {t} is parked via a 'note:' containing PARKED but has "
                   f"no explicit 'parked: true' field — add 'parked: true' (note text is a "
                   f"fragile park signal).")
    # PARK-3: claim.sh honors depends_on but NOT build-after. A live (non-parked) ticket whose
    # build-after predecessor is not yet done would be claimed prematurely — park it, or
    # convert build-after -> depends_on if it is a genuine hard prereq.
    if not parked and d["build_after"]:
        ba = re.split(r"[,\s]+", d["build_after"].strip())[0].strip().lower()
        if ba:
            ba_id = ids.get(ba)
            ba_done = ba_id is not None and is_done(ba_id)
            ba_parked = ba in parked_files or (ba_id is not None and is_parked(tickets[ba_id]))
            if not ba_done:
                red.append(f"build-after-unenforced: {t} has build-after '{ba}' which is "
                           f"{'PARKED' if ba_parked else 'not done'}, but {t} is NOT parked — "
                           f"claim.sh ignores build-after, so {t} would be claimed ahead of it. "
                           f"Park {t} ('parked: true') or convert build-after -> depends_on if "
                           f"it is a hard prereq.")

# D&S. STANDING RULE (mechanized): every LIVE ticket must self-document Dependencies
# & Sequence so a FRESH processor (no project history) can order it + avoid collisions.
# Its prompt must carry a "## Dependencies & sequence" section (depends_on / wave /
# concurrency-safety). Done tickets are exempt (historical). Parked (.md.parked) are
# not scanned, so this fires the moment a ticket is un-parked to live.
import re as _re
_DS = _re.compile(r"##\s*dependencies\s*&\s*sequence", _re.I)
for t, d in tickets.items():
    if inactive(t):
        continue
    p = d["prompt"]
    if not p or not os.path.exists(p):
        continue  # missing-prompt already RED above
    try:
        if not _DS.search(open(p).read()):
            red.append(f"D&S missing: {t} prompt lacks a '## Dependencies & sequence' "
                       f"section (standing rule — state depends_on + wave + concurrency "
                       f"safety). Add it to {os.path.basename(p)}")
    except OSError:
        pass

# Semantic intent (contradictory prompts, hidden coupling) is NOT machine-checkable
# in bash — surfaced as advisory only, never a failure.
if any(d["deps"] for d in tickets.values()):
    wci.append("semantic: prompt-intent contradiction / hidden coupling is NOT machine-checked "
               "— eyeball overlapping or dep-linked tickets by hand.")

# F46 PARALLELIZABILITY-GATE: ADVISORY board-wide surface of SPLITTABLE-yet-serial tickets
# (difficulty>=M AND >1 independent owned surface, not decomposed, not justified). Delegates
# to fleet/checks/parallelizability-gate.sh scan — REUSE, don't reinvent the owns/difficulty
# parsing. Advisory ONLY here (never RED — never fails the board on its own): the HARD
# launch-time gate lives in fleet/fleet-droid.sh, the one place a serial launch happens.
try:
    _pg = subprocess.run(
        ["bash", os.path.join(fleet, "checks", "parallelizability-gate.sh"), "scan"],
        capture_output=True, text=True, timeout=15
    ).stdout
    for _line in _pg.splitlines():
        if "SPLITTABLE-SERIAL:" in _line:
            wci.append(f"parallelizability: {_line.strip()}")
except Exception as e:
    wci.append(f"parallelizability-check-failed: could not run parallelizability-gate.sh — {e}")

# 6. Uncommitted work — no session left dirty tracked files on disk.
# Modified tracked files in src/ = a session exited without committing.
# Untracked files (??) are OK — they belong to the active session.
import subprocess
charon_repo = PRODUCT_REPO
try:
    result = subprocess.run(
        ["git", "-C", charon_repo, "status", "--porcelain", "--", "src/"],
        capture_output=True, text=True, timeout=10
    )
    for line in result.stdout.strip().split("\n"):
        if not line:
            continue
        status = line[:2]
        path = line[3:].strip()
        if status.strip() in ("M", "MM", "MD", " D", "D "):
            red.append(f"uncommitted-work: dirty tracked file '{path}' — a session exited without committing. Commit or stash before launching.")
except Exception as e:
    red.append(f"uncommitted-check-failed: could not run git status — {e}")

print("== validate_board ==")
for i in info:  print(f"  INFO {i}")
for w in warn:  print(f"  WARN {w}")
for w in wci:   print(f"  WCI-ADVISORY {w}")
for r in red:   print(f"  RED  {r}")
print("  GREEN board structurally valid" if not red else f"  RED  {len(red)} issue(s) — fix before launching")
sys.exit(1 if red else 0)
PY
