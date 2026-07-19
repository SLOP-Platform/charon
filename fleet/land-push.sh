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
#
# LAND-SAFETY-FIX (2026-07-18): this used to end in a bare `git push origin "$BRANCH"`, which
# publishes the LOCAL REF MATCHING THAT NAME — not HEAD. With HEAD on a feature branch,
# `land-push.sh master` printed "pushing 'master'" and exited 0 while publishing NOTHING (the
# local master ref was stale). It now resolves EXACTLY which sha it intends to publish, refuses
# when that is not what the caller meant, and PROVES the result with `git ls-remote`.
# The explicit `HEAD:master` refspec form (how master was reconciled) still works — it is now the
# REQUIRED form whenever the named branch is not what HEAD points at.
#
# EXIT CODES (callers depend on these being distinguishable):
#   0  pushed AND proven (origin/<dst> == intended sha, ls-remote verified)
#   3  AUTONOMOUS lever is off — refused, nothing pushed
#   4  gate RED — refused, nothing pushed
#   6  refused before pushing (malformed refspec / unresolvable src / stale bare-name ref)
#   7  the push command FAILED — remote unchanged, nothing published
#   8  push exited 0 but origin/<dst> is NOT the intended sha — UNPROVEN, possibly wrong content
#      published. 6 vs 7 vs 8 are deliberately distinct: 6/7 mean NOTHING was published, 8 means
#      something may have been. Do not collapse them.
#
# LOW-6: the stale-bare-name guard below applies only to the BARE form (`master`). An EXPLICIT
# same-name refspec (`master:master`) sets BRANCH != SRC and skips it, so the stale-ref defect is
# still reachable that way. That is deliberate — an explicit refspec is an explicit statement of
# which ref the caller means — but no refspec form is inherently safe, and the refusal message
# must not imply otherwise.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLAG="$FLEET/state/AUTONOMOUS"
# shellcheck source=/dev/null
source "$FLEET/push-verify.sh"   # pv_resolve_sha / pv_push_verified — prove the push, never trust it.

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

# ── RESOLVE EXACTLY WHAT WE INTEND TO PUBLISH (fail closed) ──────────────────────────────────
# BRANCH is either a plain branch name (`master`) or an explicit refspec (`HEAD:master`).
SRC="${BRANCH%%:*}"; DST="${BRANCH#*:}"
[ "$BRANCH" = "$SRC" ] && DST="$SRC"          # no colon -> src and dst are the same name
DST="${DST#refs/heads/}"
if [ -z "$SRC" ] || [ -z "$DST" ]; then
  echo "land-push: REFUSING — malformed refspec '$BRANCH' (delete-refspecs are not supported here)" >&2
  exit 6
fi
INTENDED="$(pv_resolve_sha "$REPO" "$SRC")" || {
  echo "land-push: REFUSING — cannot resolve '$SRC' to a commit in $REPO (nothing to push)" >&2; exit 6; }

# THE 2026-07-18 DEFECT, closed: pushing a BARE NAME whose local ref is not where HEAD is
# publishes a stale ref while reporting success. Allowed only when the local ref IS HEAD;
# otherwise the caller must say which they mean with an explicit `HEAD:$DST` refspec.
if [ "$BRANCH" = "$SRC" ]; then
  HEAD_SHA="$(pv_resolve_sha "$REPO" HEAD)" || { echo "land-push: cannot resolve HEAD in $REPO" >&2; exit 6; }
  if [ "$HEAD_SHA" != "$INTENDED" ]; then
    CUR_BR="$(git -C "$REPO" rev-parse --abbrev-ref HEAD 2>/dev/null)"
    echo "land-push: REFUSING — local ref '$SRC' is $INTENDED but HEAD ($CUR_BR) is $HEAD_SHA." >&2
    echo "land-push:   pushing the bare name would publish the STALE ref and report success." >&2
    echo "land-push:   say which you mean, by SHA, not by form:" >&2
    echo "land-push:     publish what HEAD is at:  bash $FLEET/land-push.sh HEAD:$DST $REPO" >&2
    echo "land-push:     publish the '$SRC' ref  :  bash $FLEET/land-push.sh $SRC:$DST $REPO" >&2
    echo "land-push:   NOTE: the refspec form is NOT a safety check — it only records which ref you" >&2
    echo "land-push:   meant. '$SRC:$DST' publishes $INTENDED and skips this guard by design. Confirm" >&2
    echo "land-push:   the sha above is the work you intend to publish before rerunning." >&2
    exit 6
  fi
fi

echo "land-push: AUTONOMOUS on — publishing $INTENDED ('$SRC') -> origin/$DST from $REPO"
PV_RC=0; pv_push_verified "$REPO" origin "$INTENDED" "$DST" || PV_RC=$?
if [ "$PV_RC" -ne 0 ]; then
  echo "land-push: FAILED — origin/$DST was NOT proven to be $INTENDED (rc=$PV_RC). NOT reporting success." >&2
  # LOW-5: this was `exit $((4 + PV_RC))`, which produced 6 for "pushed but UNPROVEN" — colliding
  # with the 6 used above for "REFUSED, nothing was pushed". A caller could not tell NOTHING WAS
  # PUBLISHED from THE WRONG THING MAY BE PUBLISHED, and the second is by far the more dangerous
  # state. They now have distinct codes (see the exit-code table in the header).
  case "$PV_RC" in
    1) exit 7 ;;   # the push command itself failed — remote unchanged, nothing published
    *) exit 8 ;;   # push exited 0 but origin/$DST is NOT $INTENDED — UNPROVEN, possibly wrong
  esac
fi
echo "land-push: DONE — origin/$DST == $INTENDED (ls-remote verified)"
