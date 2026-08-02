#!/usr/bin/env bash
# substrate-gate-ownership-failopen.test.sh — fail-on-revert suite for the ownership FAIL-OPEN
# closed in substrate_first_gate.py:base_board_owns (ticket GATE-OWNERSHIP-FAILOPEN).
#
# THE DEFECT CLASS: **fail-open on the OWNER, fail-closed on the OWNED.**
#   base_board_owns() did `except TicketError: continue` — a base-ref board ticket whose
#   frontmatter failed the strict-YAML parse was SILENTLY DROPPED, so its `owns:` paths never
#   entered the ownership set. cmd_pr_has_ticket then printed "this change touches CODE owned by
#   NO live board ticket", which is FALSE: a ticket DID own it, the gate just could not read it.
#   A gate that drops evidence silently and reports the absence of evidence as proof of absence.
#   Measured 2026-08-01: 23 LIVE tickets (~21% of the board) silently unowned; PR #345 blocked
#   with a message that was not true. Second fail-open in the same function: the scope filter
#   excluded only "/archive/", so fleet/board/retired/ tickets still granted LIVE ownership.
#
# THE INVARIANT (ratchet — must stay STRONGER, never weaker):
#   1. An unparseable base-ref ticket is a LOUD RED that NAMES the file, never a silent skip,
#      and never the "no live board ticket owns this" claim.
#   2. Only a TOP-LEVEL fleet/board/<id>.md grants LIVE ownership — never archive/, retired/
#      or briefs/.
#   3. ANTI-OVER-BLOCK: a clean board still resolves ownership and stays GREEN, and a
#      briefs/ file with empty frontmatter must NOT wedge the gate.
#
# FAIL-ON-REVERT: `revert` mode restores the PRE-FIX base_board_owns verbatim (silent
# `continue` + "/archive/"-only filter). Cases (a2), (a3) and (d) MUST fail in that mode —
# that is the proof the fix is load-bearing.
#
# HERMETIC: every fixture is a throwaway `git init` repo under mktemp -d. It never reads the
# live board, never touches fleet/state/, never hits the network.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: imports the gate MODULE and runs git on a
# throwaway repo ONLY. It must NEVER call rig-ci-scope.sh, validate_board.sh, preflight.sh or
# land*.sh — those invoke the gate, and a test that invokes its own caller is the fork bomb.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CHECKS="$HERE/../checks"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
REVERT="${SUBSTRATE_FAILOPEN_REVERT:-}"   # set to 1 to run the whole suite in revert mode

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }
has(){  case "$1" in *"$2"*) return 0;; *) return 1;; esac; }

# ---------------------------------------------------------------- hermetic fixture repo
REPO="$TMP/repo"
mkdir -p "$REPO/fleet/board/retired" "$REPO/fleet/board/archive" "$REPO/fleet/board/briefs" "$REPO/src/charon"
git -C "$REPO" init -q .
git -C "$REPO" config user.email t@t
git -C "$REPO" config user.name t

# A LIVE ticket that OWNS the file the PR touches — but whose frontmatter does NOT parse.
# The break is the real recurring shape: a column-0 line escaping an open `note: |` block,
# then a backtick that cannot start a YAML token. Verbatim from SHARED-NAMESPACE-CONTENTION.md.
cat >"$REPO/fleet/board/BROKEN-OWNER.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 3
branch: feat/the-feature
owns: src/charon/feature.py
note: |
  This ticket really does own the file. The gate must never say otherwise just because it
  cannot read the ticket.

D&S — Deps & Sequence:
  - Related: STOP-WORKER-GRACEFUL-EXIT also owns `spawn-worker.sh`'s sibling
    `stop-worker.sh` — disjoint files, but coordinate if both are in flight.
TIC
# A brief with EMPTY frontmatter — out of scope, must never wedge the gate (23 of these are live).
printf '# just a brief, no frontmatter at all\n' >"$REPO/fleet/board/briefs/SOME-BRIEF.md"
echo 'def feature(): return 0' >"$REPO/src/charon/feature.py"
echo 'def widget(): return 0'  >"$REPO/src/charon/widget.py"
git -C "$REPO" add -A
git -C "$REPO" commit -qm base
BASE_BROKEN="$(git -C "$REPO" rev-parse HEAD)"

# CODE-ONLY change to the file the BROKEN ticket owns (no board/*.md in the diff).
git -C "$REPO" checkout -q -b feat-broken
echo 'def feature(): return 1  # changed' >"$REPO/src/charon/feature.py"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'code only: owned by an unparseable ticket'
HEAD_BROKEN="$(git -C "$REPO" rev-parse HEAD)"

# The SELF-UNBLOCK case: a PR that MINTS a ticket in-diff while the base board is still broken.
# It must stay GREEN, or the very PR that repairs the board could never land (and the whole fleet
# would be wedged by one malformed ticket). The unparseable tickets are still DISCLOSED.
git -C "$REPO" checkout -q "$BASE_BROKEN" 2>/dev/null
git -C "$REPO" checkout -q -b feat-mints
echo 'def newthing(): return 0' >"$REPO/src/charon/newthing.py"
cat >"$REPO/fleet/board/NEW-TICKET.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 2
branch: feat/new-thing
owns: src/charon/newthing.py
note: minted in the SAME diff as its code — the ticket-and-code-together shape.
TIC
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'code + ticket minted together'
HEAD_MINTS="$(git -C "$REPO" rev-parse HEAD)"

# ---- clean-board base: BROKEN-OWNER repaired (the escaped lines indented back inside `note:`)
git -C "$REPO" checkout -q "$BASE_BROKEN" 2>/dev/null
git -C "$REPO" checkout -q -b clean-base
cat >"$REPO/fleet/board/BROKEN-OWNER.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 3
branch: feat/the-feature
owns: src/charon/feature.py
note: |
  This ticket really does own the file. The gate must never say otherwise just because it
  cannot read the ticket.

  D&S — Deps & Sequence:
    - Related: STOP-WORKER-GRACEFUL-EXIT also owns `spawn-worker.sh`'s sibling
      `stop-worker.sh` — disjoint files, but coordinate if both are in flight.
TIC
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'repaired frontmatter'
BASE_CLEAN="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" checkout -q -b feat-clean
echo 'def feature(): return 2  # changed' >"$REPO/src/charon/feature.py"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'code only: owned by a parseable ticket'
HEAD_CLEAN="$(git -C "$REPO" rev-parse HEAD)"

# ---- retired/archive base: ONLY a RETIRED (and an ARCHIVED) ticket owns widget.py -----------
git -C "$REPO" checkout -q "$BASE_CLEAN"
git -C "$REPO" checkout -q -b retired-base
cat >"$REPO/fleet/board/retired/OLD-WIDGET.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 2
branch: feat/old-widget
owns: src/charon/widget.py
note: retired work. It is NOT a live owner and must not satisfy the ownership question.
TIC
cat >"$REPO/fleet/board/archive/DONE-WIDGET.md" <<'TIC'
repo: charon-private
work_class: greenfield-feature
difficulty: 2
branch: feat/done-widget
owns: src/charon/widget.py
note: archived work. Already excluded before this fix; guards the regression.
TIC
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'retired + archived owners'
BASE_RETIRED="$(git -C "$REPO" rev-parse HEAD)"
git -C "$REPO" checkout -q -b feat-retired
echo 'def widget(): return 3  # changed' >"$REPO/src/charon/widget.py"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'code only: owned only by a retired ticket'
HEAD_RETIRED="$(git -C "$REPO" rev-parse HEAD)"

# ---------------------------------------------------------------- driver
# run_gate <base> <head> — drives the REAL cmd_pr_has_ticket. With SUBSTRATE_FAILOPEN_REVERT=1
# it first restores the PRE-FIX base_board_owns verbatim (the two fail-opens under test).
run_gate(){
  RIG_CI_BASE="$1" RIG_CI_HEAD="$2" SUBSTRATE_FAILOPEN_REVERT="$REVERT" \
  python3 - "$CHECKS" "$REPO" <<'PY'
import os, sys
checks, repo = sys.argv[1], sys.argv[2]
sys.path.insert(0, checks)
import substrate_first_gate as g

if os.environ.get("SUBSTRATE_FAILOPEN_REVERT"):
    # THE PRE-FIX FUNCTION, verbatim: silent `continue` on TicketError, "/archive/"-only scope,
    # 2-tuple return. Restoring it MUST make this suite fail — that is the whole point.
    def _pre_fix(root):
        base = g._base_ref_tip(root)
        if not base:
            return [], False
        listing = g._git(root, "ls-tree", "-r", "--name-only", base, "fleet/board/")
        if listing is None:
            return [], False
        entries = []
        for path in listing.split("\n"):
            path = path.strip()
            if not path.endswith(".md") or not path.startswith("fleet/board/"):
                continue
            if "/archive/" in path:
                continue
            content = g._git(root, "show", f"{base}:{path}")
            if content is None:
                return [], False
            try:
                fm = g.parse_frontmatter(content)
            except g.TicketError:
                continue          # <-- THE FAIL-OPEN
            if g.is_parked(fm):
                continue
            for entry in g._owns_entries(g.field(fm, "owns")):
                if " " in entry or "\t" in entry or entry.startswith("("):
                    continue
                entries.append(entry)
        return entries, True

    _real = g.cmd_pr_has_ticket

    def _shim(gate):
        # The pre-fix call site unpacked a 2-tuple; emulate it so the OLD logic runs end to end.
        owns, resolved = _pre_fix(gate.root)
        g.base_board_owns = lambda root: (owns, resolved, [])
        return _real(gate)

    g.cmd_pr_has_ticket = _shim

gate = g.Gate("/nonexistent/registry.md", repo)  # pr-has-ticket does not read the registry
sys.exit(g.cmd_pr_has_ticket(gate))
PY
}

echo "== substrate-gate ownership fail-open${REVERT:+  [REVERT MODE — these MUST fail]} =="

# (a) an UNPARSEABLE base ticket that OWNS the changed file
out="$(run_gate "$BASE_BROKEN" "$HEAD_BROKEN" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then ok "(a1) unparseable base ticket => RED (fail-closed)"
else bad "(a1) unparseable base ticket => RED (got rc=$rc)"; fi

if has "$out" "BROKEN-OWNER.md"; then ok "(a2) the RED NAMES the ticket it could not parse"
else bad "(a2) the RED NAMES the ticket it could not parse — the gate stayed silent about it"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

if has "$out" "owned by NO live board ticket"; then
  bad "(a3) the gate must NOT claim 'owned by NO live board ticket' — a ticket DOES own it"
  printf '%s\n' "$out" | sed 's/^/        /'
else ok "(a3) the gate does not assert the FALSE 'owned by NO live board ticket'"; fi

if has "$out" "could NOT BE PARSED"; then ok "(a4) the RED states the TRUE reason (unreadable board)"
else bad "(a4) the RED states the TRUE reason (unreadable board)"; fi

# (b) ANTI-OVER-BLOCK: a clean board still resolves ownership => GREEN
out="$(run_gate "$BASE_CLEAN" "$HEAD_CLEAN" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "(b) ANTI-OVER-BLOCK: repaired ticket owns the file => GREEN"
else bad "(b) ANTI-OVER-BLOCK: repaired ticket owns the file => GREEN (got rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (c) a briefs/ file with EMPTY frontmatter is OUT OF SCOPE and must not wedge the gate
if has "$out" "SOME-BRIEF.md"; then
  bad "(c) briefs/ (empty frontmatter) must be OUT OF SCOPE, not an unparseable-ticket RED"
else ok "(c) briefs/ with empty frontmatter does not wedge the gate (out of scope)"; fi

# (d) SECONDARY FAIL-OPEN: a RETIRED ticket must NOT grant LIVE ownership
out="$(run_gate "$BASE_RETIRED" "$HEAD_RETIRED" 2>&1)"; rc=$?
if [ "$rc" -ne 0 ]; then ok "(d) a RETIRED ticket does NOT grant live ownership => RED"
else bad "(d) a RETIRED ticket granted LIVE ownership — fail-open (got rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

if has "$out" "owned by NO live board ticket"; then
  ok "(e) with a fully-parseable board the 'no live owner' verdict is still reachable (ratchet holds)"
else bad "(e) the 'no live owner' RED must still fire for genuinely unowned code"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (f) SELF-UNBLOCK + DISCLOSURE: a ticket minted in-diff still passes over a broken base board,
#     and the unreadable tickets are named anyway (never silent, on any path).
out="$(run_gate "$BASE_BROKEN" "$HEAD_MINTS" 2>&1)"; rc=$?
if [ "$rc" -eq 0 ]; then ok "(f1) a ticket minted in-diff is GREEN even over a broken base board"
else bad "(f1) a broken base board must not wedge a PR that mints its own ticket (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

if [ -n "$REVERT" ]; then
  ok "(f2) disclosure not asserted in revert mode (pre-fix code has nothing to disclose)"
elif has "$out" "could not be parsed"; then
  ok "(f2) the GREEN path still DISCLOSES the tickets it could not parse (never silent)"
else bad "(f2) the GREEN path must still disclose unparseable tickets — that is the silent skip"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

echo "  ---- $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
