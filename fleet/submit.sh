#!/usr/bin/env bash
# Mark a ticket as submitted (PR opened). Run by the droid as its last step.
# GUARDS THE PHANTOM-PR-OPEN BUG (2026-06-27): a droid can commit its work but have its
# `gh pr create` (or the push) fail while `claude` still exits 0 — without a check, submit
# would stamp PR-OPEN over a PR that doesn't exist and the board would lie. So: verify a real
# OPEN PR exists for the ticket's branch first. If none, flag state/needs-push/<id> and refuse
# (exit 4) — the work is committed in the worktree; the manager pushes it and lands the PR.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"; S="$FLEET/state"; BOARD="$FLEET/board"
REPO_SLUG="SLOP-Platform/charon"
canon(){ local w="$1" f b; for f in "$BOARD"/*.md; do b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  echo "submit.sh: no board ticket matching '$w'" >&2; return 1; }
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2"; }
id="$(canon "${1:?usage: submit.sh <id>}")" || exit 2
branch="$(meta branch "$BOARD/$id.md")"
# GROUND check: is there actually an open PR for this branch?
if [ -z "$(gh pr list --repo "$REPO_SLUG" --head "$branch" --state open --json number -q '.[0].number' 2>/dev/null)" ]; then
  mkdir -p "$S/needs-push"
  printf 'branch=%s\nworktree=/home/stack/code/charon-fleet-%s\nreason=committed but no open PR (push or gh-pr-create failed)\nflagged=%s\n' \
    "$branch" "$id" "$(date -u +%FT%TZ)" > "$S/needs-push/$id"
  echo "submit.sh: NO open PR for '$branch' — NOT marking submitted; flagged state/needs-push/$id." >&2
  echo "           recover:  bash $FLEET/land-needs-push.sh $id" >&2
  exit 4
fi
mkdir -p "$S/submitted"; date -u +%FT%TZ > "$S/submitted/$id"; rm -f "$S/claims/$id" "$S/needs-push/$id"
echo "submitted $id (PR open; awaiting operator merge)"
