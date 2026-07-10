#!/usr/bin/env bash
# reconcile-merged.sh — AUTO-`done` ON MERGE (fleet build-rig only).
#
# MECHANIZES the #2 fragility: done.sh correctly REFUSES a premature close, but the manager must
# REMEMBER to run it after every merge; a forgotten close freezes every dependent (the board
# stalls, retire-done never fires). This is the safety-net that removes the memory step.
#
# For every MERGED PR head-branch, map it back to its board ticket and — if that ticket is not
# already state/done/<id> — run done.sh --no-verify for it (the merge is already proven, so no
# need to re-check the PR). Idempotent: a ticket already done is skipped. Safe to run every
# preflight. Called from preflight.sh's scan path, same shape as retire-done.sh.
#
# Network-tolerant: if `gh` is unavailable/offline the merged-branch list is empty and this is a
# clean no-op (never blocks preflight).
#
# TEST HOOK: set RECONCILE_MERGED_SRC=<file> (one head-branch per line) to inject a fixture list
# instead of calling `gh` — see fleet/tests/reconcile-merged.test.sh. Keeps the mapping+close
# logic exercisable offline.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; DONE="$FLEET/state/done"
REPO_SLUG="${RECONCILE_REPO_SLUG:-SLOP-Platform/charon}"
DONE_SH="${RECONCILE_DONE_SH:-$FLEET/done.sh}"

meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }

# merged head-branches, one per line. Fixture file wins (offline test); else gh.
merged_branches(){
  if [ -n "${RECONCILE_MERGED_SRC:-}" ]; then
    [ -f "$RECONCILE_MERGED_SRC" ] && grep -v '^[[:space:]]*$' "$RECONCILE_MERGED_SRC" || true
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 0
  gh pr list --repo "$REPO_SLUG" --state merged --limit 200 \
     --json headRefName -q '.[].headRefName' 2>/dev/null || true
}

# branch -> board ticket id (active board OR archive). Empty if none maps.
ticket_for_branch(){
  local want="$1" f b
  for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
    [ -e "$f" ] || continue
    b="$(meta branch "$f")"
    [ "$b" = "$want" ] || continue
    basename "$f" .md; return 0
  done
  return 1
}

mkdir -p "$DONE"
reconciled=0; seen=0
while IFS= read -r br; do
  [ -n "$br" ] || continue
  seen=$((seen+1))
  id="$(ticket_for_branch "$br")" || continue      # merged branch with no board ticket -> ignore
  [ -e "$DONE/$id" ] && continue                    # already done -> idempotent no-op
  echo "reconcile-merged: $br is MERGED but $id is not done — auto-closing (merge proven)."
  # --no-verify: the merge is already proven by the merged-PR listing; skip the gh re-check.
  if bash "$DONE_SH" "$id" --no-verify; then
    reconciled=$((reconciled+1))
  else
    echo "reconcile-merged: WARNING — done.sh failed for $id (see above)." >&2
  fi
done < <(merged_branches)

if [ "$reconciled" -gt 0 ]; then
  echo "reconcile-merged: auto-closed $reconciled merged-but-open ticket(s)."
else
  echo "reconcile-merged: clean (no merged ticket left open; scanned $seen merged branch(es))."
fi
exit 0
