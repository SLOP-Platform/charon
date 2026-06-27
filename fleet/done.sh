#!/usr/bin/env bash
# MANAGER runs this AFTER merging a ticket's PR. Marks done -> unblocks dependents.
# REFUSES unless a MERGED PR exists for the ticket's branch (audit 2026-06-27, THEME 5:
# done-before-merge unblocks dependents onto a master that lacks the dep code).
# Override for offline/manual cases with: done.sh <id> --no-verify
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
REPO_SLUG="SLOP-Platform/charon"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "done.sh: no board ticket matching '$w'" >&2; return 1; }
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
id="$(canon "${1:?usage: done.sh <id> [--no-verify]}")" || exit 2
if [ "${2:-}" != "--no-verify" ]; then
  branch="$(meta branch "$BOARD/$id.md")"
  n="$(gh pr list --repo "$REPO_SLUG" --head "$branch" --state merged --json number -q '.[0].number' 2>/dev/null || true)"
  if [ -z "$n" ]; then
    echo "done.sh: REFUSED — no MERGED PR found for branch '$branch' (ticket $id)." >&2
    echo "         Merge the PR first, or pass --no-verify to override." >&2
    exit 3
  fi
  echo "done.sh: verified PR #$n (branch $branch) is MERGED."
fi
mkdir -p "$S/done"; date -u +%FT%TZ > "$S/done/$id"; rm -f "$S/submitted/$id" "$S/claims/$id"
echo "done $id (dependents unblocked)"
