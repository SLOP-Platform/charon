#!/usr/bin/env bash
# lifecycle-enforce.sh — LIFECYCLE-ENFORCEMENT: the rig's enforcement GATE for the D-003
# mechanism. Not a rule to recall, not a detector that advises — a gate that REDs on an
# unfinished commitment and refuses to let it pass.
#
# WHAT IT ENFORCES (the blocking edges D-003 specified; see fleet/board/LIFECYCLE-ENFORCEMENT.md):
#   E1  ASKED-BLOCKS-TICKET   An open ASKED row in fleet/state/DECISIONS.md whose `**Blocks:**`
#                             field names a LIVE board ticket means that ticket must not proceed.
#                             Any such ticket still on the live board (not parked) is RED. The
#                             ledger already REQUIRES every ASKED row to name what it blocks;
#                             nothing read that field before this gate.
#   E3  VERDICT-WITHOUT-TICKET (the D-007 rule, previously unenforced). A landed
#                             docs/review-log/* fragment carrying an ADOPT/REJECT verdict must
#                             reference a minted board ticket id (fleet/board/<id>.md or
#                             fleet/board/archive/<id>.md), or RED. A verdict without a minted
#                             ticket is NOT done — this is the cheapest, diff-only edge and it is
#                             the single most expensive pattern in the project.
#
# EDGES NOT BUILT (deliberately — see `edges` and docs/review-log/LIFECYCLE-ENFORCEMENT.md):
#   E2  DECIDED-CONTRADICTED   not mechanically decidable from a diff; needs semantics.
#   E4  DONE-BACKED-BY-EVIDENCE done-markers live in fleet/state/done/ (gitignored, absent in a
#                             fresh checkout) and the evidence half pairs with D-005 mutation
#                             testing — live-tree only, deferred.
#   E5  OUT-OF-BAND-NOTIFY     needs infrastructure (ntfy / Healthchecks.io) outside these files.
#
# HARD CONSTRAINTS HONOURED:
#   - D-008 "this must not be bash if it holds state": this gate HOLDS NO STATE. It reads files
#     and exits. Stateless, so bash + a stdlib-only python core is compliant.
#   - D-002/D-004 "check for an existing tool before building": Forgetful (scored B+2, the highest
#     of any target) was re-opened. It is a plans/tasks state-machine for a session's memory — it
#     cannot be a CI merge-gate that blocks a violating diff in THIS repo. D-003 already decided
#     this mechanism; the acceptance criteria demand a gate. See the review fragment.
#   - Enforcement is a GATE: the exit code is the verdict. Nothing here tells a session to be
#     careful.
#   - READ-ONLY + hermetic + offline: no writes, no network, no gh, no git.
#
# Usage:
#   lifecycle-enforce.sh            run all built edges (check)  — exit 0 GREEN / 1 RED / 2 usage
#   lifecycle-enforce.sh check      same as above (explicit)
#   lifecycle-enforce.sh edges      print which of the five edges are BUILT / NOT-BUILT (acceptance d)
#   lifecycle-enforce.sh help       this text
#
# Env seam (hermetic test override):
#   LIFECYCLE_ROOT   repo root to scan (default: this script's repo root).
#                    The gate never touches anything outside this root.
#
# Exit: 0 = GREEN (all built edges hold), 1 = RED (a built edge was violated),
#       2 = usage / cannot resolve the root.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")/../.." && pwd)"
ROOT="${LIFECYCLE_ROOT:-${HERE}}"
if [[ -z "${ROOT}" ]] || [[ ! -d "${ROOT}" ]]; then
  echo "lifecycle-enforce: no such repo root: ${ROOT}" >&2
  exit 2
fi

usage(){
  cat <<EOF
usage: lifecycle-enforce.sh [check|edges|help]

  (no arg) | check   run all built edges (E1 ASKED-blocks-ticket, E3 verdict-without-ticket)
  edges               print which of the five D-003 edges are BUILT / NOT-BUILT
  help                this text

Env:
  LIFECYCLE_ROOT   repo root to scan (default: this script's repo root)

Exit: 0 GREEN, 1 RED, 2 usage.
EOF
}

cmd_edges(){
  printf '%s\n' \
    'E1 ASKED-BLOCKS-TICKET: BUILT' \
    'E2 DECIDED-CONTRADICTED: NOT-BUILT (not mechanically decidable from a diff; needs semantics)' \
    'E3 VERDICT-WITHOUT-TICKET: BUILT (primary edge)' \
    'E4 DONE-BACKED-BY-EVIDENCE: NOT-BUILT (done-markers are gitignored/absent in CI; pairs with D-005 mutation testing)' \
    'E5 OUT-OF-BAND-NOTIFY: NOT-BUILT (needs infrastructure outside these two files)'
}

cmd_check(){
  LIFECYCLE_ROOT="${ROOT}" python3 - <<'PY'
import os, re, sys, glob

ROOT = os.environ["LIFECYCLE_ROOT"]
REDS = []

def red(edge, msg):
    REDS.append((edge, msg))
    print("RED: %s %s" % (edge, msg))

def readf(path):
    try:
        with open(path, encoding="utf-8", errors="replace") as fh:
            return fh.read()
    except OSError:
        return None

# ---- shared helpers ------------------------------------------------------------------
def board_ids():
    ids = set()
    for d in ("fleet/board", "fleet/board/archive"):
        for f in glob.glob(os.path.join(ROOT, d, "*.md")):
            ids.add(os.path.basename(f)[:-3])
    return ids

TICKET_TOKEN = re.compile(r'\b([A-Z][A-Z0-9]*(?:-[A-Z0-9]+)+)\b')

def is_parked(path):
    text = readf(path)
    if text is None:
        return False
    parked_field = False
    note_line = False
    for line in text.splitlines():
        low = line.lower()
        if low.startswith("parked:"):
            val = line.split(":", 1)[1].strip().lower()
            if val in ("true", "yes", "1"):
                parked_field = True
        if re.match(r'^note\s*:', low):
            note_line = True
    return parked_field or (note_line and "PARKED" in text.upper())

# ---- E3  verdict -> minted ticket ------------------------------------------------------
# A fragment "carries an ADOPT/REJECT verdict" only via a verdict STATEMENT, so ordinary prose
# that happens to use the verbs "adopt"/"reject" is never misread as a verdict:
#   ## Verdict / ## Decision / **Verdict:** / **Decision:** with the value on the same line,
#   or the value on the NEXT line after the bare heading,
#   or a heading that IS the verdict ("## ADOPT (this commit)"),
#   or a bold-name-labelled bullet ("- **<name>:** ADOPT ...").
# Negations ("DO NOT ADOPT", "NOT ADOPT") are explicitly not verdicts.

HDR_ONLY = re.compile(r'^(?:#{1,6}\s+|\*{0,2})(?:Verdict|Decision)\*{0,2}\s*[:.]?\s*$', re.I)
HDR_VAL = re.compile(r'^(?:#{1,6}\s+)?\*{0,2}(?:Verdict|Decision)\*{0,2}\s*[:.]\s*(ADOPT|REJECT)\b', re.I)
HEADING_VERDICT = re.compile(r'^#{1,6}\s+(ADOPT|REJECT)\b', re.I)
BOLD_LABEL_VERDICT = re.compile(r'^\*\*[^*]+\*\*\s*[:.]\s*(ADOPT|REJECT)\b', re.I)
VERDICT_WORD = re.compile(r'^(ADOPT|REJECT)\b', re.I)
NEGATION = re.compile(r'^(DO NOT ADOPT|NOT ADOPT)\b', re.I)

def fragment_verdicts(lines):
    hits = []
    for i, line in enumerate(lines):
        t = line.strip()
        if NEGATION.match(t):
            continue
        if HDR_ONLY.match(t):
            nxt = lines[i + 1].strip() if i + 1 < len(lines) else ""
            if VERDICT_WORD.match(nxt) and not NEGATION.match(nxt):
                hits.append(nxt)
            continue
        m = HDR_VAL.match(t)
        if m:
            val = re.sub(r'^(?:#{1,6}\s+)?\*{0,2}(?:Verdict|Decision)\*{0,2}\s*[:.]\s*', '', t)
            hits.append(val)
            continue
        m = HEADING_VERDICT.match(t)
        if m:
            hits.append(re.sub(r'^#{1,6}\s+', '', t))
            continue
        bullet = re.sub(r'^[-*]\s+', '', t)
        m = BOLD_LABEL_VERDICT.match(bullet)
        if m and not NEGATION.match(bullet):
            hits.append(re.sub(r'^\*\*[^*]+\*\*\s*[:.]\s*', '', bullet))
    return hits

def refs_minted_ticket(basename, body, board):
    if basename in board:
        return True
    for m in re.finditer(r'^[*#]+\s*Ticket\s*:?\s*([A-Za-z0-9][A-Za-z0-9_-]*)', body, re.M):
        if m.group(1) in board:
            return True
    for tok in TICKET_TOKEN.findall(body):
        if tok in board:
            return True
    return False

def check_e3(board):
    rl_dir = os.path.join(ROOT, "docs", "review-log")
    frags = sorted(glob.glob(os.path.join(rl_dir, "*.md"))) if os.path.isdir(rl_dir) else []
    n_verdict = 0
    for f in frags:
        body = readf(f)
        if body is None:
            continue
        verdicts = fragment_verdicts(body.splitlines())
        if not verdicts:
            continue
        n_verdict += 1
        base = os.path.basename(f)[:-3]
        if not refs_minted_ticket(base, body, board):
            rel = os.path.relpath(f, ROOT)
            red("E3", "%s carries an ADOPT/REJECT verdict (%r) but references NO minted board ticket "
                "(checked fleet/board/*.md and fleet/board/archive/*.md). A verdict without a minted "
                "ticket is NOT done (D-007)." % (rel, verdicts[0][:60]))
    return n_verdict

# ---- E1  open ASKED row blocks a live ticket -------------------------------------------
def check_e1(board):
    dec = os.path.join(ROOT, "fleet", "state", "DECISIONS.md")
    text = readf(dec)
    if text is None:
        return 0  # no ledger -> no ASKED rows -> nothing to block; documented in `edges`
    lines = text.splitlines()
    # Slice the "## ASKED" section: it runs until the next top-level "## " section.
    start = None
    end = len(lines)
    for i, line in enumerate(lines):
        if line.startswith("## ASKED"):
            start = i
        elif start is not None and line.startswith("## ") and not line.startswith("## ASKED"):
            end = i
            break
    if start is None:
        return 0
    asked = lines[start:end]
    # Walk the rows: a row is introduced by a "### <id>" heading.
    rows = []  # (id, row_lines)
    cur = None
    for line in asked:
        if line.startswith("### "):
            if cur is not None:
                rows.append(cur)
            cur = [line, ""]
        elif cur is not None:
            cur[1] += line + "\n"
    if cur is not None:
        rows.append(cur)
    n_blocked = 0
    for rid, body in rows:
        rid = rid.lstrip("#").strip()
        if re.search(r'\b(?:CLOSED|ANSWERED)\b', rid, re.I):
            continue
        bm = re.search(r'^\*{0,2}BLOCKS\*{0,2}\s*:', body, re.M | re.I)
        if not bm:
            continue
        value = body[bm.end():]
        value = re.split(r'\n\s*(?:\*\*|---)', value, maxsplit=1)[0]
        for tok in TICKET_TOKEN.findall(value):
            if tok in board and os.path.isfile(os.path.join(ROOT, "fleet", "board", tok + ".md")):
                if not is_parked(os.path.join(ROOT, "fleet", "board", tok + ".md")):
                    n_blocked += 1
                    rid_id = rid.split(" ", 1)[0].lstrip("#").strip()
                    red("E1", "%s is blocked by the open ASKED row %s in fleet/state/DECISIONS.md "
                        "(its **Blocks:** field names it). Refuse claim/launch until the question is "
                        "answered." % (tok, rid_id))
    return n_blocked

board = board_ids()
nv = check_e3(board)
nb = check_e1(board)

if REDS:
    print("lifecycle-enforce: RED — %d violation(s): %d verdict(s) without a ticket (E3), "
          "%d ticket(s) blocked by an open ASKED row (E1)." % (len(REDS), nv, nb))
    sys.exit(1)
print("lifecycle-enforce: GREEN — %d verdict fragment(s) checked (E3), %d live ticket(s) "
      "checked against open ASKED rows (E1). Built edges: E1, E3." % (nv, nb))
sys.exit(0)
PY
}

case "${1:-}" in
  "" | check) cmd_check ;;
  edges) cmd_edges ;;
  help | -h | --help) usage ;;
  *) echo "usage: lifecycle-enforce.sh [check|edges|help]" >&2; exit 2 ;;
esac
