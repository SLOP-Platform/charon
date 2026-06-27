#!/usr/bin/env bash
# THE sanctioned push path for the manager. Raw `git push` and `git -C … push` are both
# deny-listed, so this wrapper is the only way the manager can push. It self-gates on the
# AUTONOMOUS lever (state/AUTONOMOUS):
#   flag ON  -> push (full-autonomous mode: no human in the routine loop)
#   flag OFF -> REFUSE and print the operator's push command (the human checkpoint on main)
# Usage: land-push.sh <branch> [repo-or-worktree]    (default repo = /home/stack/code/charon)
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"
BRANCH="${1:?usage: land-push.sh <branch> [repo]}"
REPO="${2:-/home/stack/code/charon}"
if [ ! -e "$FLAG" ]; then
  echo "land-push: AUTONOMOUS mode is OFF — the manager will not push." >&2
  echo "  operator runs:  git -C $REPO push origin $BRANCH" >&2
  echo "  or flip the lever: bash $FLEET/autonomous.sh on" >&2
  exit 3
fi
echo "land-push: AUTONOMOUS on — pushing '$BRANCH' from $REPO"
git -C "$REPO" push origin "$BRANCH"
