#!/usr/bin/env bash
# THE ONE COMMAND PER TAB.  Usage:  fleet-droid.sh <low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>]
# Loops: claim a ticket for this tier -> run ONE ephemeral claude session on it (worktree, work,
# DRAFT PR base=master, never merges) -> mark submitted -> claim the next. Stands down when no
# tier-eligible work remains.
#
# SELF-FEEDING POOL (--wait): instead of standing down on an empty claim, sleep <min> minutes and
# re-check, up to <n> CONSECUTIVE empty checks (default 6), THEN stand down. Finding work resets
# the counter. An idle tab is just a sleeping shell — no model session burns until it claims. So
# open the pool of tabs ONCE; each rides through dependency gaps (grabbing the next ticket the
# instant a merge unblocks it) and drains to a clean exit when the board is done. No per-ticket
# hand-launching; the manager stays gate-only.
#
# DEFAULT is --wait 3: a bare `fleet-droid.sh <tier>` self-feeds (waits through empty checks)
# rather than quitting on the first empty claim. Pass `--wait 0` for the old one-shot behavior
# (claim once, stand down when empty); raise `--retries` to ride out longer dependency gaps.
set -euo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
usage(){ echo "usage: fleet-droid.sh <low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>] [--patience <cycles>]"; exit 2; }
TIER=""; WAIT_MIN=3; RETRIES=6; PATIENCE=1
while [ $# -gt 0 ]; do case "$1" in
  --wait)     WAIT_MIN="${2:?--wait needs minutes}"; shift 2;;
  --retries)  RETRIES="${2:?--retries needs a count}"; shift 2;;
  --patience) PATIENCE="${2:?--patience needs a cycle count}"; shift 2;;
  opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;       # arg allowlist widened: canonical + legacy
  *) usage;;
esac; done
[ -n "$TIER" ] || usage
# De-hardwire the launch model: resolve tier -> concrete Anthropic model NAME via config
# (`charon tier resolve … --executor anthropic`, TIER-3). `claude -p` speaks the Anthropic
# Messages API while the gateway is OpenAI-only, so the fleet path does NOT route through the
# gateway — it's a name lookup, no Anthropic↔OpenAI shim. `|| MODEL="$TIER"` keeps half-migrated
# setups working: legacy opus/sonnet/haiku still launch unchanged when tiers.json is absent.
MODEL="$(charon tier resolve "$TIER" --executor anthropic 2>/dev/null)" || MODEL="$TIER"
DROID="$TIER-$$"; current=""; empties=0
# Release the in-flight claim if the tab is Ctrl-C'd / killed (no stuck tickets).
cleanup(){ if [ -n "${current:-}" ] && [ ! -e "$FLEET/state/submitted/$current" ]; then
  bash "$FLEET/release.sh" "$current" >/dev/null 2>&1 || true; fi; }
trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
wmsg=""; [ "$WAIT_MIN" -gt 0 ] && wmsg=", wait=${WAIT_MIN}m retries=${RETRIES} patience=${PATIENCE}"
echo "[$DROID] charon-fleet droid up (model=$MODEL$wmsg). Ctrl-C to stand down."
while true; do
  # Tier patience: try OWN tier first; only dip to lower tiers once we've been
  # empty-at-own-tier for >= PATIENCE wait-cycles (gives lower tiers a head start).
  mode=both; [ "$empties" -lt "$PATIENCE" ] && mode=own-only
  if ! res="$(bash "$FLEET/claim.sh" "$TIER" "$DROID" "$mode")"; then
    if [ "$WAIT_MIN" -gt 0 ] && [ "$empties" -lt "$RETRIES" ]; then
      empties=$((empties+1))
      echo "[$DROID] no $TIER-eligible work — waiting ${WAIT_MIN}m (empty $empties/$RETRIES)…"
      sleep "$((WAIT_MIN*60))"; continue
    fi
    echo "[$DROID] no $TIER-eligible work left — standing down."; break
  fi
  empties=0
  read -r _tag id tfile <<<"$res"; current="$id"
  echo "[$DROID] claimed $id — launching session…"
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  prompt="$(cat "$FLEET/JOIN-PROMPT.md")

=== YOUR ASSIGNED TICKET: $id ===
$spec"
  if claude -p --model "$MODEL" --dangerously-skip-permissions "$prompt"; then
    # The droid committed its work on its branch but does NOT push or open the PR: the
    # deny-list blocks `git push`/`gh pr create` inside the Claude session (even with
    # --dangerously-skip-permissions, which does NOT bypass deny rules). So the LAUNCHER
    # publishes here in plain operator-shell — NOT a Claude Bash tool call — so the
    # deny-list never applies. Read <branch> from the ticket via the same awk meta pattern.
    branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
    wt="/home/stack/code/charon-fleet-$id"
    # SAFETY NET (FR1 root cause): a droid can exit 0 with work left UNCOMMITTED — it made the
    # edits but never ran `git commit`. Pushing then publishes an EMPTY branch (gh pr create
    # fails → NEEDS-PUSH) and strands the work in the worktree, where a later re-claim's
    # `git worktree remove --force` (JOIN-PROMPT) DESTROYS it. So auto-commit any leftover first:
    # the work is always captured and still goes through the PR/CI/review gate. The commit message
    # flags it so the manager scrutinizes for half-done work.
    if [ -n "$(git -C "$wt" status --porcelain 2>/dev/null)" ]; then
      echo "[$DROID] WARNING: $id left UNCOMMITTED changes — launcher auto-committing (droid exited without committing)."
      git -C "$wt" add -A
      git -C "$wt" commit -q -m "chore($id): launcher auto-commit — droid exited without committing (review for completeness)" || true
    fi
    # If there are STILL no commits beyond base, the droid produced nothing — a genuine no-op.
    # Release for retry rather than pushing an empty branch.
    if [ -z "$(git -C "$wt" log --oneline "origin/master..$branch" 2>/dev/null)" ]; then
      echo "[$DROID] $id produced NO commits and NO changes — releasing for retry (nothing to publish)."
      bash "$FLEET/release.sh" "$id" || true; current=""; continue
    fi
    # Drop any stale remote branch from a prior/closed PR so the push fast-forwards, then
    # push + open the DRAFT PR. If either fails, fall through: submit.sh grounds on a real
    # open PR and flags state/needs-push when there isn't one. `|| true` keeps set -e happy.
    git -C "$wt" push origin --delete "$branch" 2>/dev/null || true
    git -C "$wt" push -u origin "$branch" \
      && gh pr create --repo SLOP-Platform/charon --base master --head "$branch" --draft --fill \
      || true
    if bash "$FLEET/submit.sh" "$id"; then
      current=""; echo "[$DROID] $id submitted (PR open). Next…"
    else
      # submit refused: work committed but no real PR (push or gh-pr-create failed). Keep the
      # claim + worktree (don't let another droid redo it); submit flagged state/needs-push
      # for the manager to land.
      current=""; echo "[$DROID] $id: work committed but NO PR opened — flagged needs-push; manager lands it. Next…"
    fi
  else
    bash "$FLEET/release.sh" "$id" || true; current=""
    echo "[$DROID] $id session exited non-zero — released for retry."
  fi
done
