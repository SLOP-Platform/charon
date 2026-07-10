#!/usr/bin/env bash
# reconcile-merged.sh — AUTO-`done` ON MERGE (fleet build-rig only).
#
# MECHANIZES fragility #2 AND the Wave-A HIGH #2 fix: map each MERGED PR back to its board ticket by
# VERIFIED MERGE / `owns`-file OVERLAP — NOT a bare branch-name string match — and close it through
# the HARDENED done.sh with the discovered `--merged-sha`, so the marker carries REAL proof (never
# the old `--no-verify`). This kills two hazards at once:
#   * branch-name reuse can no longer mis-close a re-created ticket (an old merged PR with the same
#     short branch name — e.g. `feat/tick` — would have string-matched the NEW open ticket), and
#   * a merge whose branch DRIFTED from the board meta (SR-1 case) now still auto-closes via owns.
#
# Per-PR mapping precedence:  1) board `branch:` == PR head-branch, else  2) `owns:` files OVERLAP
# the PR's changed files. Close: done.sh <id> --merged-sha <mergeSha> (proof written into marker).
#
# Network-tolerant: gh missing/offline -> empty list -> clean no-op (never blocks preflight).
#
# TEST HOOK: RECONCILE_MERGED_SRC=<file>, TSV "<branch>\t<mergeSha>\t<f1,f2,..>\t<pr#>" (fields after
# <branch> optional) injects the merged-PR set instead of gh. DONE_CHARON_REPO / RECONCILE_DONE_SH /
# RECONCILE_REPO_SLUG override the product repo, done.sh path, and slug for isolated tests.
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; DONE="$FLEET/state/done"; TAB=$'\t'
CHARON_REPO="${DONE_CHARON_REPO:-/home/stack/code/charon}"
REPO_SLUG="${RECONCILE_REPO_SLUG:-$(git -C "$CHARON_REPO" remote get-url origin 2>/dev/null | sed -E 's#(git@[^:]*:|https?://[^/]*/)##; s/\.git$//')}"
[ -n "$REPO_SLUG" ] || REPO_SLUG="SLOP-Platform/charon"
DONE_SH="${RECONCILE_DONE_SH:-$FLEET/done.sh}"

meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null; }

# merged PRs as TSV "branch\tsha\tfiles\tpr". Fixture wins (offline); else gh.
merged_prs(){
  if [ -n "${RECONCILE_MERGED_SRC:-}" ]; then
    [ -f "$RECONCILE_MERGED_SRC" ] && grep -v '^[[:space:]]*$' "$RECONCILE_MERGED_SRC" || true
    return 0
  fi
  command -v gh >/dev/null 2>&1 || return 0
  gh pr list --repo "$REPO_SLUG" --state merged --limit 200 \
     --json headRefName,mergeCommit,files,number \
     -q '.[] | [.headRefName, (.mergeCommit.oid // ""), ([.files[].path]|join(",")), (.number|tostring)] | @tsv' \
     2>/dev/null || true
}

# do comma-list <1> and comma-list <2> share any path?  0 = yes.
_overlap(){
  local a="$1" b="$2" x y; local IFS=','
  for x in $a; do
    x="$(printf '%s' "$x" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"; [ -n "$x" ] || continue
    for y in $b; do
      y="$(printf '%s' "$y" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"; [ -n "$y" ] || continue
      [ "$x" = "$y" ] && return 0
    done
  done
  return 1
}

# map a merged PR (head-branch, changed-files) -> board ticket id. Branch-meta match FIRST, then
# owns-file overlap (branch drifted). Empty if none maps.
ticket_for_pr(){
  local want_branch="$1" pr_files="$2" f b ownsf
  for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
    [ -e "$f" ] || continue
    b="$(meta branch "$f")"; [ -n "$b" ] && [ "$b" = "$want_branch" ] || continue
    basename "$f" .md; return 0
  done
  [ -n "$pr_files" ] || return 1
  for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
    [ -e "$f" ] || continue
    ownsf="$(meta owns "$f")"; [ -n "$ownsf" ] || continue
    if _overlap "$ownsf" "$pr_files"; then basename "$f" .md; return 0; fi
  done
  return 1
}

mkdir -p "$DONE"
reconciled=0; seen=0
while IFS="$TAB" read -r branch sha files pr; do
  [ -n "${branch:-}" ] || continue
  seen=$((seen+1))
  id="$(ticket_for_pr "$branch" "${files:-}")" || continue   # no board ticket maps -> ignore
  [ -e "$DONE/$id" ] && continue                             # already done -> idempotent no-op
  echo "reconcile-merged: merged PR (branch=$branch) maps to $id — auto-closing WITH proof."
  rc=0
  if [ -n "${sha:-}" ]; then
    bash "$DONE_SH" "$id" --merged-sha "$sha" || rc=$?
  else
    # no merge sha available -> hand done.sh a proven merged-branch list so it writes merged:#pr proof.
    tmpsrc="$(mktemp)"; printf '%s\t%s\n' "$branch" "${pr:-0}" > "$tmpsrc"
    DONE_MERGED_SRC="$tmpsrc" bash "$DONE_SH" "$id" || rc=$?
    rm -f "$tmpsrc"
  fi
  if [ "$rc" -eq 0 ]; then reconciled=$((reconciled+1))
  else echo "reconcile-merged: WARNING — done.sh failed for $id (rc=$rc; see above)." >&2; fi
done < <(merged_prs)

if [ "$reconciled" -gt 0 ]; then
  echo "reconcile-merged: auto-closed $reconciled merged-but-open ticket(s) with recorded proof."
else
  echo "reconcile-merged: clean (no merged ticket left open; scanned $seen merged PR(s))."
fi
exit 0
