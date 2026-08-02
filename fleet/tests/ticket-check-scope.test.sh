#!/usr/bin/env bash
# ticket-check-scope.test.sh — fail-on-revert suite for the SEMANTIC grandfathering scope in
# rig-ci-scope.sh cmd_board (ticket TICKET-CHECK-SCOPE-SEMANTIC).
#
# THE DEFECT: the per-ticket checks were scoped to "this file appears in the diff", conflating
# "this ticket's WORK changed" with "this ticket's FILE was touched". A meaning-preserving YAML
# repair therefore re-opened years of accumulated debt on unrelated tickets — 21 pre-existing REDs
# fired when 23 unparseable tickets were repaired, making the repair of a gate defect unlandable.
#
# THE INVARIANT (a NARROWING of WHEN the check fires — never a loosening of WHAT it checks):
#   1. a ticket ALREADY on the base ref whose substrate-relevant fields are semantically unchanged
#      is SKIPPED (grandfathered), however the file was reformatted;
#   2. ANY real change to a substrate-relevant field (owns / work_class / substrate / …) is
#      checked EXACTLY as before;
#   3. a NEW ticket (absent from the base ref) is ALWAYS fully checked;
#   4. LOSING a D&S section is always checked (ratchet); gaining one is not a de-grandfatherer;
#   5. FAIL CLOSED: an unresolvable base means CHECK EVERYTHING.
#
# FAIL-ON-REVERT: `SCOPE_REVERT=1` restores the pre-fix rule (check every ticket in the diff) by
# neutering _ticket_grandfathered. Cases (a) and (f) MUST fail in that mode.
#
# HERMETIC: throwaway `git init` repos under mktemp -d. Never reads the live board, never touches
# fleet/state/, never hits the network.
#
# REENTRANCY [[fleet-selfcheck-forkbomb-class]]: runs `rig-ci-scope.sh board` against a THROWAWAY
# repo only. It must never call land*.sh, preflight.sh or gate.sh — those invoke this gate.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET="$(dirname "$HERE")"
TMP="$(mktemp -d)"; trap 'rm -rf "$TMP"' EXIT
REVERT="${SCOPE_REVERT:-}"

PASS=0; FAIL=0
ok(){   PASS=$((PASS+1)); echo "  ok   $1"; }
bad(){  FAIL=$((FAIL+1)); echo "  FAIL $1"; }
has(){  case "$1" in *"$2"*) return 0;; *) return 1;; esac; }

# ---- a hermetic repo carrying the rig's checks and a board -----------------------------------
REPO="$TMP/repo"
mkdir -p "$REPO/fleet/checks" "$REPO/fleet/state" "$REPO/src/charon"
cp "$FLEET/checks/rig-ci-scope.sh" "$FLEET/checks/substrate-first-gate.sh" \
   "$FLEET/checks/substrate_first_gate.py" "$REPO/fleet/checks/" 2>/dev/null
cp "$FLEET/state/EVAL-REGISTRY.md" "$REPO/fleet/state/" 2>/dev/null || :

if [ -n "$REVERT" ]; then
  # THE PRE-FIX RULE, restored: every ticket in the diff is checked, whatever changed.
  # Reverting must make (a) and (f) fail — that is the proof the narrowing is load-bearing.
  python3 - "$REPO/fleet/checks/rig-ci-scope.sh" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
s = s.replace("_ticket_grandfathered(){\n", "_ticket_grandfathered(){\n  return 1  # REVERTED\n", 1)
open(p, "w", encoding="utf-8").write(s)
PY
fi

git -C "$REPO" init -q .
git -C "$REPO" config user.email t@t
git -C "$REPO" config user.name t

# DEBT.md: a ticket with REAL pre-existing debt — work_class demands a substrate: answer and it
# has none, and it has no D&S section. Exactly the shape of the 13 found on master.
write_debt(){ # <file> <owns> [extra-line]
  cat >"$1" <<TIC
repo: charon-private
work_class: rig-meta
difficulty: 3
branch: feat/debt
owns: $2
note: |
  A ticket written before the substrate rule existed. It carries no substrate: field and no
  Dependencies & Sequence section — real, pre-existing debt that predates this PR.
${3:-}
TIC
}
write_debt "$REPO/fleet/board_seed.md" "src/charon/thing.py"
mkdir -p "$REPO/fleet/board"
cp "$REPO/fleet/board_seed.md" "$REPO/fleet/board/DEBT.md"; rm -f "$REPO/fleet/board_seed.md"
echo 'def thing(): return 0' >"$REPO/src/charon/thing.py"
git -C "$REPO" add -A; git -C "$REPO" commit -qm base
BASE="$(git -C "$REPO" rev-parse HEAD)"

run_board(){ # <head-ref> -> prints output, returns rc
  ( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE="$BASE" RIG_CI_HEAD="$1" \
      bash fleet/checks/rig-ci-scope.sh board 2>&1 )
}
branch_from_base(){ git -C "$REPO" checkout -q "$BASE" 2>/dev/null; git -C "$REPO" checkout -q -B "$1"; }
commit_all(){ git -C "$REPO" add -A; git -C "$REPO" commit -qm "$1" >/dev/null; git -C "$REPO" rev-parse HEAD; }

echo "== rig-ci-scope: semantic grandfathering${REVERT:+  [REVERT MODE — (a) and (f) MUST fail]} =="

# (a) PURE FORMATTING REPAIR: same fields, reflowed file => grandfathered, NO pre-existing RED.
branch_from_base fmt
python3 - "$REPO/fleet/board/DEBT.md" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read()
# the real repair shape: reflow prose inside the block scalar, reorder nothing semantic
s = s.replace("A ticket written before the substrate rule existed.",
              "A ticket written before\n  the substrate rule existed.")
open(p, "w", encoding="utf-8").write(s)
PY
H="$(commit_all fmt)"
out="$(run_board "$H")"; rc=$?
if [ "$rc" -eq 0 ]; then ok "(a1) a pure formatting repair does NOT re-open pre-existing debt"
else bad "(a1) a pure formatting repair must not re-open pre-existing debt (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi
if has "$out" "(grandfathered — this PR changed no substrate-relevant field"; then ok "(a2) the skip is NARRATED per ticket, not silent"
else bad "(a2) the per-ticket skip must be narrated"; printf '%s\n' "$out" | sed 's/^/        /'; fi

# (b) REAL CHANGE — a path ADDED to owns: => checked exactly as today => RED.
branch_from_base owns-add
sed -i 's#^owns: .*#owns: src/charon/thing.py, src/charon/second.py#' "$REPO/fleet/board/DEBT.md"
echo 'def second(): return 0' >"$REPO/src/charon/second.py"
H="$(commit_all owns-add)"
out="$(run_board "$H")"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "NO 'substrate:' field"; then
  ok "(b) adding a path to owns: STILL triggers the full check (RED)"
else bad "(b) a real owns: change must still be fully checked (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (c) REAL CHANGE — work_class edited => checked => RED.
branch_from_base wc
sed -i 's#^work_class: .*#work_class: money-path#' "$REPO/fleet/board/DEBT.md"
H="$(commit_all wc)"
out="$(run_board "$H")"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "NO 'substrate:' field"; then
  ok "(c) changing work_class STILL triggers the full check (RED)"
else bad "(c) a work_class change must still be fully checked (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (d) A NEW TICKET is never grandfathered, however broken.
branch_from_base newtic
write_debt "$REPO/fleet/board/BRAND-NEW.md" "src/charon/thing.py"
H="$(commit_all newtic)"
out="$(run_board "$H")"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "BRAND-NEW"; then
  ok "(d) a NEW ticket absent from the base ref is ALWAYS fully checked"
else bad "(d) a new ticket must never be grandfathered (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (e) RATCHET — LOSING a D&S section is always checked.
branch_from_base dslost
cat >"$REPO/fleet/board/HASDS.md" <<'TIC'
repo: charon-private
work_class: rig-meta
difficulty: 3
branch: feat/hasds
owns: src/charon/thing.py
note: pre-existing debt, but it did have a section.

## Dependencies & Sequence

- none.
TIC
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'seed hasds' >/dev/null
BASE2="$(git -C "$REPO" rev-parse HEAD)"
python3 - "$REPO/fleet/board/HASDS.md" <<'PY'
import sys
p = sys.argv[1]
s = open(p, encoding="utf-8").read().replace("## Dependencies & Sequence\n\n- none.\n", "")
open(p, "w", encoding="utf-8").write(s)
PY
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'drop D&S' >/dev/null
H="$(git -C "$REPO" rev-parse HEAD)"
out="$( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE="$BASE2" RIG_CI_HEAD="$H" \
        bash fleet/checks/rig-ci-scope.sh board 2>&1 )"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "no Dependencies & Sequence section"; then
  ok "(e) LOSING a D&S section is still checked (ratchet holds)"
else bad "(e) losing a D&S section must always RED (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (f) THE REAL CASE: an ABSOLUTE owns path rewritten to its repo-relative form denotes the SAME
#     files, so it stays grandfathered — and the absolute-path RED it used to carry is GONE.
branch_from_base absfix
sed -i "s#^owns: .*#owns: $REPO/src/charon/thing.py#" "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'seed absolute owns' >/dev/null
BASE3="$(git -C "$REPO" rev-parse HEAD)"
sed -i 's#^owns: .*#owns: src/charon/thing.py#' "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'absolute -> repo-relative' >/dev/null
H="$(git -C "$REPO" rev-parse HEAD)"
out="$( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE="$BASE3" RIG_CI_HEAD="$H" \
        bash fleet/checks/rig-ci-scope.sh board 2>&1 )"; rc=$?
if [ "$rc" -eq 0 ]; then ok "(f) absolute -> repo-relative owns is the SAME file set => grandfathered"
else bad "(f) rewriting an absolute owns path to repo-relative must not re-open debt (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (g) FAIL CLOSED: an unresolvable base refuses outright — it never grandfathers everything.
out="$( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE=deadbeefdeadbeef RIG_CI_HEAD="$H" \
        bash fleet/checks/rig-ci-scope.sh board 2>&1 )"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "no resolvable diff base"; then
  ok "(g) FAIL CLOSED: an unresolvable base refuses, never grandfathers by default"
else bad "(g) an unresolvable base must refuse (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (h) A FOREIGN absolute prefix (another checkout's path) that still resolves to a real file HERE
#     also denotes the same file => grandfathered. This is the live PROJECT-MEMBERSHIP-GATE shape.
branch_from_base absforeign
sed -i "s#^owns: .*#owns: /home/some-other-checkout/charon-private/src/charon/thing.py#" "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'seed foreign absolute owns' >/dev/null
BASE4="$(git -C "$REPO" rev-parse HEAD)"
sed -i 's#^owns: .*#owns: src/charon/thing.py#' "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'foreign absolute -> repo-relative' >/dev/null
H="$(git -C "$REPO" rev-parse HEAD)"
out="$( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE="$BASE4" RIG_CI_HEAD="$H" \
        bash fleet/checks/rig-ci-scope.sh board 2>&1 )"; rc=$?
if [ "$rc" -eq 0 ]; then ok "(h) a FOREIGN absolute owns path resolving to the same file => grandfathered"
else bad "(h) fixing a foreign absolute owns path must not re-open debt (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

# (i) An absolute owns path that resolves NOWHERE in this repo is NOT normalised away — it names a
#     different file set, so the ticket is CHECKED. Fail-closed on ambiguity.
branch_from_base absnowhere
sed -i "s#^owns: .*#owns: /nowhere/at/all/ghost.py#" "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'seed unresolvable absolute owns' >/dev/null
BASE5="$(git -C "$REPO" rev-parse HEAD)"
sed -i 's#^owns: .*#owns: src/charon/thing.py#' "$REPO/fleet/board/DEBT.md"
git -C "$REPO" add -A; git -C "$REPO" commit -qm 'unresolvable absolute -> different file' >/dev/null
H="$(git -C "$REPO" rev-parse HEAD)"
out="$( cd "$REPO" && RIG_CI_ROOT="$REPO" RIG_CI_BASE="$BASE5" RIG_CI_HEAD="$H" \
        bash fleet/checks/rig-ci-scope.sh board 2>&1 )"; rc=$?
if [ "$rc" -ne 0 ] && has "$out" "NO 'substrate:' field"; then
  ok "(i) an owns path that resolves NOWHERE is a REAL change => fully checked (fail-closed)"
else bad "(i) an unresolvable absolute owns path must be treated as a real change (rc=$rc)"
     printf '%s\n' "$out" | sed 's/^/        /'; fi

echo "  ---- $PASS passed, $FAIL failed"
[ "$FAIL" -eq 0 ]
