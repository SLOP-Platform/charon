#!/usr/bin/env bash
# decompose.sh — DEC-DRIVER (Wave 1). Run the PRODUCT decomposer engine on ONE broad
# board ticket and emit N disjoint, single-domain sub-tickets back to the board.
#
# Pipeline (reuses the product engine end-to-end; this file is thin glue only):
#   1. read the broad ticket + its `owns:` (the change TARGETS) from the board
#   2. call the product engine to get the plan:
#        decompose_surface.change_surface(targets)  -> AST blast-radius facts
#        decompose_planner.plan_decomposition(...)   -> N file-scoped PlanUnits
#      (the planner runs intake.assert_disjoint_waves internally; ADR-0008 contract #1)
#   3. VALIDATE the plan in the driver too — belt-and-braces, the revertable guard:
#        intake.assert_disjoint_waves(units) + a STRICT all-pairs disjoint-owns check.
#        Refuse (fail-loud, emit NOTHING) on zero units or ANY overlapping owns.
#   4. EMIT each validated unit as a board `*.md` ticket: parent: <ticket-id>, disjoint
#      owns, depends_on chain, inherited repo/work_class/difficulty.
#
# Fail-loud on any error; NEVER emit overlapping owns.
#
# Seams (for the self-test; the REAL path always calls the product engine):
#   DEC_PLAN_CMD  — if set, run it to obtain the plan JSON instead of the built-in
#                   engine call (lets test_dec_driver.sh mock the engine). The driver's
#                   step-3 validation ALWAYS runs, whatever the plan source.
#   BOARD_DIR     — where sub-tickets are written (default <fleet>/board).
#   TICKET_FILE   — explicit path to the broad ticket (default $BOARD_DIR/<id>.md).
#   CHARON_SRC    — product src on PYTHONPATH (default /home/stack/code/charon/src).
set -euo pipefail

FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHARON_SRC="${CHARON_SRC:-/home/stack/code/charon/src}"
BOARD_DIR="${BOARD_DIR:-$FLEET/board}"

die() { echo "decompose.sh: FATAL: $*" >&2; exit 1; }

[ $# -ge 1 ] || die "usage: decompose.sh <ticket-id>"
TICKET_ID="$1"
TICKET_FILE="${TICKET_FILE:-$BOARD_DIR/$TICKET_ID.md}"
[ -f "$TICKET_FILE" ] || die "no such ticket: $TICKET_FILE"

# ---- 1+2. obtain the plan JSON ------------------------------------------------
# Shape: {"units":[ {id, goal, accept:[...], owns:[...], depends_on:[...], tier, body}, ... ]}
if [ -n "${DEC_PLAN_CMD:-}" ]; then
  # test seam: engine mocked. Step-3 validation still runs on the result.
  PLAN_JSON="$(bash -c "$DEC_PLAN_CMD")"
else
  # REAL path: call the product decomposer engine.
  PLAN_JSON="$(
    TICKET_FILE="$TICKET_FILE" TICKET_ID="$TICKET_ID" \
    PYTHONPATH="$CHARON_SRC" python3 - "$TICKET_FILE" "$TICKET_ID" <<'PYENGINE'
import json, os, re, sys

def parse_ticket(path):
    fields = {}
    lines = open(path).read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^([A-Za-z0-9_-]+):(.*)$', line)
        if m and not line[:1].isspace():
            key, rest = m.group(1), m.group(2)
            if rest.strip() == "|":
                block, i = [], i + 1
                while i < len(lines) and (lines[i][:1].isspace() or lines[i].strip() == ""):
                    block.append(lines[i]); i += 1
                fields[key] = "\n".join(b[2:] if b.startswith("  ") else b for b in block).strip()
                continue
            fields[key] = rest.strip()
        i += 1
    return fields

tfile, tid = sys.argv[1], sys.argv[2]
f = parse_ticket(tfile)
targets = [o.strip() for o in f.get("owns", "").split(",") if o.strip()]
if not targets:
    sys.exit(f"decompose.sh: FATAL: ticket {tid} has no `owns:` targets to decompose")

try:
    from charon.decompose_surface import change_surface
    from charon.decompose_planner import BroadTicket, plan_decomposition
except ImportError as e:
    sys.exit(
        "decompose.sh: FATAL: product decomposer engine not importable "
        f"(decompose_surface/decompose_planner): {e}. Those are Wave-0 chunks "
        "(feat/dec-ast-wrap, feat/dec-planner) — ensure they are landed on the "
        f"product tree at PYTHONPATH={os.environ.get('PYTHONPATH')}"
    )

# repo_root = parent of the product `src/` dir on PYTHONPATH (semantic_proof reads src/charon there)
_src = (os.environ.get("PYTHONPATH", "").split(os.pathsep) or ["."])[0]
facts = change_surface(targets, repo_root=(os.path.dirname(_src) or "."))
ticket = BroadTicket(
    id=tid,
    goal=(f.get("note") or (f.get("scope", "").splitlines() or [""])[0] or f"decompose {tid}"),
    body=f.get("accept", ""),
    product_acceptance=f.get("accept", ""),
)
units = plan_decomposition(ticket, facts)
print(json.dumps({"units": [u.to_dict() for u in units]}))
PYENGINE
  )"
fi
[ -n "${PLAN_JSON// }" ] || die "engine produced an empty plan"

# ---- 3+4. validate (the revertable guard) then emit ---------------------------
# The plan travels via env (DEC_PLAN_JSON), NOT stdin: stdin is consumed by the heredoc
# that IS the python script below.
DEC_PLAN_JSON="$PLAN_JSON" \
  TICKET_FILE="$TICKET_FILE" PARENT="$TICKET_ID" BOARD_DIR="$BOARD_DIR" \
  PYTHONPATH="$CHARON_SRC" python3 <<'PYEMIT'
import json, os, re, sys

def die(msg):
    sys.stderr.write("decompose.sh: FATAL: " + msg + "\n"); sys.exit(1)

def refuse(msg):
    # validation REFUSAL: fail-loud, emit NOTHING (reverting this path is what lets an
    # overlapping / empty split reach the board — see test_dec_driver.sh fail-on-revert).
    sys.stderr.write("decompose.sh: REFUSE: " + msg + "\n"); sys.exit(3)

def parse_ticket(path):
    fields = {}
    lines = open(path).read().splitlines()
    i = 0
    while i < len(lines):
        line = lines[i]
        m = re.match(r'^([A-Za-z0-9_-]+):(.*)$', line)
        if m and not line[:1].isspace():
            key, rest = m.group(1), m.group(2)
            if rest.strip() == "|":
                block, i = [], i + 1
                while i < len(lines) and (lines[i][:1].isspace() or lines[i].strip() == ""):
                    block.append(lines[i]); i += 1
                fields[key] = "\n".join(b[2:] if b.startswith("  ") else b for b in block).strip()
                continue
            fields[key] = rest.strip()
        i += 1
    return fields

try:
    plan = json.loads(os.environ.get("DEC_PLAN_JSON", ""))
except Exception as e:
    die(f"plan is not valid JSON: {e}")

raw = plan.get("units")
if not isinstance(raw, list) or not raw:
    refuse("plan has ZERO sub-tickets — nothing disjoint to emit")

from charon.intake import PlanUnit, assert_disjoint_waves, IntakeError

units = []
for i, u in enumerate(raw):
    if not isinstance(u, dict):
        die(f"unit #{i} is not an object")
    uid = str(u.get("id") or "").strip()
    if not uid:
        die(f"unit #{i} has no id")
    owns = [str(p).strip() for p in (u.get("owns") or u.get("owned_paths") or []) if str(p).strip()]
    if not owns:
        refuse(f"unit {uid!r} owns no files")
    accept = [str(a).strip() for a in (u.get("accept") or []) if str(a).strip()]
    if not accept:
        accept = [f"fail-on-revert acceptance for {uid} (author before executing)"]
    units.append(PlanUnit(
        id=uid,
        goal=str(u.get("goal") or uid),
        accept=accept,
        body=str(u.get("body") or ""),
        tier=str(u.get("tier") or "med"),
        owned_paths=owns,
        depends_on=[str(d).strip() for d in (u.get("depends_on") or []) if str(d).strip()],
    ))

# --- VALIDATE STEP (revertable guard) -----------------------------------------
# (a) product ADR-0008 contract #1 authority: no two CONCURRENT units share a path.
try:
    assert_disjoint_waves(units)
except IntakeError as e:
    refuse(str(e))
# (b) STRICT: no two sub-tickets share ANY owned path at all (never emit overlapping
#     owns, even if one is sequenced after the other) — the board's disjoint invariant.
seen = {}
for pu in units:
    for p in pu.owned_paths:
        if p in seen and seen[p] != pu.id:
            refuse(f"overlapping owns {p!r} shared by {seen[p]!r} and {pu.id!r}")
        seen[p] = pu.id

# --- EMIT STEP ----------------------------------------------------------------
parent = os.environ["PARENT"]
board = os.environ["BOARD_DIR"]
pf = parse_ticket(os.environ["TICKET_FILE"])
work_class = (pf.get("work_class") or "generalist").strip() or "generalist"
diff = (pf.get("difficulty") or "3").split()[0] if pf.get("difficulty") else "3"
repo = (pf.get("repo") or "charon").strip() or "charon"

os.makedirs(board, exist_ok=True)
emitted = []
for pu in units:
    deps = ", ".join(pu.depends_on)
    owns_csv = ", ".join(pu.owned_paths)
    accept_block = "\n".join("  " + ln for a in pu.accept for ln in a.splitlines())
    lines = [
        f"tier: {pu.tier}",
        f"difficulty: {diff}",
        f"work_class: {work_class}",
        f"branch: feat/{pu.id}",
        f"repo: {repo}",
        f"parent: {parent}",
        f"depends_on: {deps}",
    ]
    # A decompose depends_on IS a real build/sequence prereq; mark it so the WCI
    # false-blocking-dep gate (disjoint owns + dep) does not RED the emitted ticket.
    if pu.depends_on:
        lines.append("dep-kind: build")
    lines += [
        f"owns: {owns_csv}",
        "accept: |",
        accept_block if accept_block else f"  fail-on-revert acceptance for {pu.id}",
        "scope: |",
        f"  Auto-decomposed single-domain sub-ticket of {parent} (fleet/decompose.sh).",
        f"note: sub-ticket of {parent} (auto-decomposed).",
    ]
    path = os.path.join(board, f"{pu.id}.md")
    with open(path, "w") as fh:
        fh.write("\n".join(lines) + "\n")
    emitted.append(path)

if len(emitted) < 1:
    die("emitted no sub-tickets")
for p in emitted:
    print(p)
sys.stderr.write(f"decompose.sh: emitted {len(emitted)} disjoint sub-ticket(s) for {parent}\n")
PYEMIT
