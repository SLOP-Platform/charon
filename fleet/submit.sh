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
prnum="$(gh pr list --repo "$REPO_SLUG" --head "$branch" --state open --json number -q '.[0].number' 2>/dev/null)"
if [ -z "$prnum" ]; then
  mkdir -p "$S/needs-push"
  printf 'branch=%s\nworktree=/home/stack/code/charon-fleet-%s\nreason=committed but no open PR (push or gh-pr-create failed)\nflagged=%s\n' \
    "$branch" "$id" "$(date -u +%FT%TZ)" > "$S/needs-push/$id"
  echo "submit.sh: NO open PR for '$branch' — NOT marking submitted; flagged state/needs-push/$id." >&2
  echo "           recover:  bash $FLEET/land-needs-push.sh $id" >&2
  exit 4
fi
mkdir -p "$S/submitted"; date -u +%FT%TZ > "$S/submitted/$id"; rm -f "$S/claims/$id" "$S/needs-push/$id"

# AUTO CHECK-IN (manual-steps audit #10): a per-ticket check-in is otherwise a manual step that
# gets skipped, leaving summary.sh/next.sh/handoff blind to submitted work. Fold it into submit so
# the record always exists, in checkin.sh's EXACT block format + output location (fleet/session-notes/
# <UTC>-<session>.md — the same path checkin.sh writes). It is inlined rather than shelling out to
# checkin.sh so the write lands in THIS fleet's session-notes (checkin.sh hardcodes an absolute path)
# and stays consistent with the idempotency scan below.
# Idempotent: skip if a check-in whose TICKET column is this id already exists in any session-note.
NOTES_DIR="$FLEET/session-notes"
if [ -d "$NOTES_DIR" ] && grep -rqF "] $id  " "$NOTES_DIR" 2>/dev/null; then
  :  # a check-in for this ticket already exists — don't double-write
else
  ci_tier="$(meta tier "$BOARD/$id.md")"; ci_goal="$(meta scope "$BOARD/$id.md")"
  ci_files="$(meta owns "$BOARD/$id.md")"; ci_session="${SESSION:-submit-auto}"
  mkdir -p "$NOTES_DIR"
  cat <<BLOCK >> "$NOTES_DIR/$(date -u +%Y%m%dT%H%MZ)-${ci_session}.md"

[${ci_tier:-submit}] ${id}  ${id}
  Goal  ${ci_goal:-(auto check-in on submit)}
  Built (submitted via PR #$prnum)
  Files ${ci_files:-(see PR)}
  Gate  PR #$prnum open
BLOCK
fi

echo "submitted $id (PR open; awaiting operator merge)"
