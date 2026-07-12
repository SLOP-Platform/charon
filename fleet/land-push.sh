#!/usr/bin/env bash
# THE sanctioned push path for the manager. Raw `git push` and `git -C … push` are both
# deny-listed, so this wrapper is the only way the manager can push. It self-gates on the
# AUTONOMOUS lever (state/AUTONOMOUS):
#   flag ON  -> gate + push (full-autonomous mode: no human in the routine loop)
#   flag OFF -> REFUSE and print the operator's push command (the human checkpoint on main)
# Runs the pre-push gate (ruff + mypy + repo gate) before every push. Green -> push.
# Red -> ABORT, no push. --force bypasses the gate (explicit + logged).
# Usage: land-push.sh <branch> [repo-or-worktree] [--gate <cmd>] [--force]
#   default repo = /home/stack/code/charon
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"

# Parse args: land-push.sh <branch> [repo] [--gate <cmd>] [--force]
BRANCH="${1:?usage: land-push.sh <branch> [repo] [--gate <cmd>] [--force]}"; shift
REPO="/home/stack/code/charon"; GATE=""; FORCE=""
while [ $# -gt 0 ]; do case "$1" in
  --gate)  GATE="$2";  shift 2;;
  --force) FORCE=1;    shift;;
  *)       REPO="$1";  shift;;
esac; done

if [ ! -e "$FLAG" ]; then
  echo "land-push: AUTONOMOUS mode is OFF — the manager will not push." >&2
  echo "  operator runs:  git -C $REPO push origin $BRANCH" >&2
  echo "  or flip the lever: bash $FLEET/autonomous.sh on" >&2
  exit 3
fi

# GATE — refuse on red before push (explicit ruff + mypy + repo gate)
GATE_PARTS=()
if [ -n "$FORCE" ]; then
  echo "land-push: FORCE — gate BYPASSED (logged)" >&2
else
  if [ -z "$GATE" ]; then
    if   [ -f "$REPO/src/charon/cli.py" ]; then
      GATE_PARTS+=("ruff check $REPO/src $REPO/tests")
      GATE_PARTS+=("mypy $REPO/src")
      GATE_PARTS+=("PYTHONPATH=$REPO/src python3 -m charon.cli gate")
    elif [ -f "$REPO/ksf/cli.py" ]; then
      GATE_PARTS+=("ruff check $REPO/ksf $REPO/tests")
      GATE_PARTS+=("mypy $REPO/ksf")
      GATE_PARTS+=("PYTHONPATH=$REPO python3 -m ksf.cli --repo-root $REPO gate && PYTHONPATH=$REPO python3 -m ksf.cli --repo-root $REPO verify-self")
    elif [ -f "$REPO/fleet/validate_board.sh" ]; then
      GATE_PARTS+=("bash '$REPO/fleet/validate_board.sh' '$REPO/fleet'")
    elif [ -d "$REPO/tests" ]; then
      GATE_PARTS+=("python3 -m pytest -q")
    fi
  else
    GATE_PARTS+=("$GATE")
  fi
  if [ ${#GATE_PARTS[@]} -gt 0 ]; then
    for part in "${GATE_PARTS[@]}"; do
      echo "land-push: gate -> $part"
      RC=0; ( cd "$REPO" && eval "$part" ) || RC=$?
      if [ "$RC" -ne 0 ]; then
        echo "land-push: GATE RED — '$part' failed (exit $RC) — refusing to push '$BRANCH'" >&2
        exit 4
      fi
    done
    echo "land-push: gate GREEN"
  else
    echo "land-push: WARN — no gate detected for $REPO; pushing UNGATED"
  fi
fi

echo "land-push: AUTONOMOUS on — pushing '$BRANCH' from $REPO"
git -C "$REPO" push origin "$BRANCH"
