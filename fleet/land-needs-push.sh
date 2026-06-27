#!/usr/bin/env bash
# Manager recovery for a NEEDS-PUSH ticket: the droid committed its work in the worktree but
# no PR exists (push/gh-pr-create failed). This pushes the worktree branch through the gated
# land-push.sh (refuses unless the AUTONOMOUS lever is on, printing the operator's command),
# opens the draft PR, then re-runs submit.sh — which now verifies the PR and marks it truthful.
# Usage: land-needs-push.sh <id>
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
REPO_SLUG="SLOP-Platform/charon"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "land-needs-push: no board ticket matching '$w'" >&2; return 1; }
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
id="$(canon "${1:?usage: land-needs-push.sh <id>}")" || exit 2
[ -e "$S/needs-push/$id" ] || { echo "land-needs-push: $id is not flagged needs-push." >&2; exit 3; }
branch="$(meta branch "$BOARD/$id.md")"; wt="/home/stack/code/charon-fleet-$id"
[ -d "$wt" ] || { echo "land-needs-push: worktree $wt missing — work may be lost." >&2; exit 4; }
echo "land-needs-push: $id  branch=$branch  worktree=$wt"
bash "$FLEET/land-push.sh" "$branch" "$wt" || { echo "land-needs-push: push blocked (see above) — flip the lever or push, then re-run." >&2; exit 5; }
gh pr create --repo "$REPO_SLUG" --base master --head "$branch" --draft --fill || true
bash "$FLEET/submit.sh" "$id"
