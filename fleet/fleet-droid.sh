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
CHARON="/home/stack/code/charon"   # DEFAULT product repo (a ticket's `repo:` field overrides per-ticket)
# OFF-CLAUDE WORK CLIENT (SWAPPABLE). The droid's actual work runs THROUGH THE CHARON GATEWAY, not
# `claude -p` (which speaks to Anthropic directly and burns Claude tokens). Default client =
# charon-run.sh (opencode CLI -> `charon/<model>` -> gateway, cross-model failover, "zero Claude
# limit"). The opencode CLI is only the DEFAULT client — it is NOT hardwired: swap the client next
# week by setting CHARON_AGENT_CMD to any executable with the SAME positional contract
#   <cwd> <outlog> <brief-file> <model1> [model2 ...]      (exit 0 = success)
# — one env var, zero other edits. The MANAGER stays on Claude; only this droid work step is off-Claude.
CHARON_AGENT_CMD="${CHARON_AGENT_CMD:-$FLEET/charon-run.sh}"
# WORKTREE-LEAK GUARD (#1): launcher pre-creates the worktree + post-session leak detector.
source "$FLEET/leak-guard.sh"
# MULTI-REPO: maps a ticket's `repo:` field -> repo path / worktree / base branch / gate.
# Absent field -> key `charon` (product) => IDENTICAL behavior to the old hardwired path.
source "$FLEET/repo-registry.sh"
usage(){ echo "usage: fleet-droid.sh <frontier|strong|economy|low|med|high|opus|sonnet|haiku> [--wait <min>] [--retries <n>] [--patience <cycles>] [--serial-justified=<reason>]"; exit 2; }

# ---- DETENTION-REDLINE: shared tier/chain helpers ------------------------------------------------
# Defined ONCE and used by BOTH the main claim loop and the `resolve` hook below, so the chain a
# test observes is produced by the EXACT code that runs in production (production path == test path).
# normalize legacy/alias tier args (high/opus, med/sonnet, low/haiku) -> canonical frontier/strong/economy
canon_tier(){ case "$1" in
  high|opus)   echo frontier;;
  med|sonnet)  echo strong;;
  low|haiku)   echo economy;;
  *)           echo "$1";;
esac; }
# canonical tier -> comma failover chain from the tier-models data file. $NF (last field) not $2 —
# tolerant of accidental extra tabs / column alignment.
tier_chain(){ local canon="$1" tmf="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
  awk -F'\t' -v t="$canon" '$1!~/^#/ && $1==t {print $NF; exit}' "$tmf" 2>/dev/null || true; }
# Given a work_class and a tier's model chain, print the SURVIVING chain (comma-separated) after
# dropping HARD-detained models for that work_class; advisory-flagged models STAY (with a loud
# warning). Returns 7 if the WHOLE chain is HARD-detained (caller must FAIL LOUD — never run a
# detained model). model-detention.sh reads the grader-owned scorecard READ-ONLY.
detention_filter_chain(){
  local wc="$1"; shift
  local kept=() m drc
  for m in "$@"; do
    set +e; bash "$FLEET/model-detention.sh" check "$m" "$wc"; drc=$?; set -e
    case "$drc" in
      3) echo "[detention] HARD-detained: $m for work_class '$wc' — EXCLUDED from chain (scorecard redline: fabrication)." >&2 ;;
      1) echo "[detention] ADVISORY: $m flagged (>=50% block rate) for work_class '$wc' — KEPT in chain, watch closely." >&2; kept+=("$m") ;;
      *) kept+=("$m") ;;
    esac
  done
  [ "${#kept[@]}" -gt 0 ] || return 7
  ( IFS=','; echo "${kept[*]}" )
}

# ---- DETENTION-REDLINE: `resolve` dev/test hook --------------------------------------------------
# `fleet-droid.sh resolve <tier> <ticketfile>` resolves a tier + a claimed ticket to its
# POST-DETENTION-FILTER gateway chain using the SAME helpers the claim loop uses (production path ==
# test path). Prints the surviving comma chain on stdout; exits 7 with a loud message when the whole
# chain is HARD-detained for the ticket's work_class — the identical skip decision the loop makes.
if [ "${1:-}" = "resolve" ]; then
  rtier="${2:?resolve needs: <tier> <ticketfile>}"; rtfile="${3:?resolve needs: <tier> <ticketfile>}"
  [ -f "$rtfile" ] || { echo "[fleet-droid] resolve: no such ticket file: $rtfile" >&2; exit 2; }
  rcanon="$(canon_tier "$rtier")"
  rline="$(tier_chain "$rcanon")"
  [ -n "$rline" ] || { echo "[fleet-droid] resolve: no gateway model chain for tier '$rtier' (canonical '$rcanon')." >&2; exit 3; }
  IFS=',' read -r -a RMODELS <<<"$rline" || true
  rwc="$(awk -F': ' '$1=="work_class"{sub(/^[^:]*: ?/,"");print;exit}' "$rtfile")"
  if [ -z "$rwc" ]; then
    echo "[fleet-droid] resolve: ticket $rtfile has no work_class — detention filter cannot scope; emitting FULL chain." >&2
    ( IFS=','; echo "${RMODELS[*]}" ); exit 0
  fi
  if rkept="$(detention_filter_chain "$rwc" "${RMODELS[@]}")"; then
    echo "$rkept"; exit 0
  else
    echo "[fleet-droid] resolve: ALL eligible models detained for work_class '$rwc' — needs escalation or a heavily-tested run/override." >&2
    exit 7
  fi
fi

TIER=""; WAIT_MIN=3; RETRIES=6; PATIENCE=1; SERIAL_JUSTIFIED=""
while [ $# -gt 0 ]; do case "$1" in
  --wait)     WAIT_MIN="${2:?--wait needs minutes}"; shift 2;;
  --retries)  RETRIES="${2:?--retries needs a count}"; shift 2;;
  --patience) PATIENCE="${2:?--patience needs a cycle count}"; shift 2;;
  # F46 PARALLELIZABILITY-GATE escape hatch: justifies a SERIAL launch of a claimed ticket
  # that the gate would otherwise refuse (splittable: difficulty>=M AND >1 owned surface,
  # not yet decomposed). Applies to whatever this tab claims next — a per-run override, not
  # a per-ticket record; prefer 'serial_justified: <reason>' on the ticket for a durable one.
  --serial-justified=*) SERIAL_JUSTIFIED="${1#*=}"; shift;;
  frontier|strong|economy|opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;       # arg allowlist: canonical (frontier/strong/economy) + legacy
  *) usage;;
esac; done
[ -n "$TIER" ] || usage
# OFF-CLAUDE tier resolution: turn the tier arg into a GATEWAY model FAILOVER CHAIN (charon/<id>),
# NOT an Anthropic model. `charon tier resolve` only exposes an ANTHROPIC executor (its tier members
# are haiku/sonnet/opus) and config has NO tier->gateway-model map, so the per-tier chain lives in a
# small DATA FILE: fleet/tier-models.tsv (tier <TAB> comma,separated,failover,chain). Swap models by
# editing that file — zero code edits. The chain feeds $CHARON_AGENT_CMD's cross-model failover.
# ⚠️ PROVISIONAL defaults only — NO workhorse-per-tier is finalized; the real per-tier model is a
# PENDING OPERATOR DECISION (see the file header + memory: charon-no-workhorse-finalized).
TIER_MODELS_FILE="${CHARON_TIER_MODELS:-$FLEET/tier-models.tsv}"
# normalize + resolve via the SAME helpers the per-ticket detention filter + `resolve` hook use.
CANON="$(canon_tier "$TIER")"
models_line="$(tier_chain "$CANON")"
if [ -z "$models_line" ]; then
  echo "[fleet-droid] FATAL: no gateway model chain for tier '$TIER' (canonical '$CANON') in $TIER_MODELS_FILE — add a '$CANON<TAB>model1,model2' row." >&2
  exit 3
fi
IFS=',' read -r -a MODELS <<<"$models_line" || true
[ "${#MODELS[@]}" -gt 0 ] || { echo "[fleet-droid] FATAL: empty gateway model chain for tier '$CANON'." >&2; exit 3; }
DROID="$TIER-$$"; current=""; empties=0
# Release the in-flight claim if the tab is Ctrl-C'd / killed (no stuck tickets).
cleanup(){ if [ -n "${current:-}" ] && [ ! -e "$FLEET/state/submitted/$current" ]; then
  bash "$FLEET/release.sh" "$current" >/dev/null 2>&1 || true; fi
  # Drop this run's loop-guard counters (per-run scratch); durable quarantine markers under
  # state/loop-guard/<id> PERSIST for the manager to inspect + clear.
  rm -rf "$FLEET/state/loop-guard/runs/$DROID" 2>/dev/null || true; }
trap 'cleanup; echo "[$DROID] stood down."; exit 130' INT TERM
trap cleanup EXIT
wmsg=""; [ "$WAIT_MIN" -gt 0 ] && wmsg=", wait=${WAIT_MIN}m retries=${RETRIES} patience=${PATIENCE}"
echo "[$DROID] charon-fleet droid up (off-Claude via ${CHARON_AGENT_CMD##*/}; gateway chain=${MODELS[*]}$wmsg). Ctrl-C to stand down."
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
  # F46 PARALLELIZABILITY-GATE: refuse to launch a SPLITTABLE ticket (difficulty>=M AND >1
  # independent owned surface — see fleet/checks/parallelizability-gate.sh) as a single
  # SERIAL job unless it has already been decomposed into sub-tickets or is justified
  # (--serial-justified for this run, or a durable 'serial_justified:' field on the ticket).
  # Mechanizes the wall-clock rule (MANAGER-OPERATING-RULES.md sec.4) at the ONE place a
  # serial launch actually happens, so a splittable god-ticket can never silently run serial.
  pg_args=(check "$id"); [ -n "$SERIAL_JUSTIFIED" ] && pg_args+=(--serial-justified="$SERIAL_JUSTIFIED")
  if ! pg_out="$(bash "$FLEET/checks/parallelizability-gate.sh" "${pg_args[@]}" 2>&1)"; then
    echo "$pg_out" >&2
    echo "[$DROID] SKIP $id: PARALLELIZABILITY-GATE refused a serial launch — decompose it (fleet/decompose.sh $id) or pass --serial-justified=\"<reason>\"." >&2
    bash "$FLEET/release.sh" "$id" >/dev/null 2>&1 || true; current=""
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" >/dev/null 2>&1 \
      || echo "[$DROID] LOOP-GUARD: $id quarantined (parallelizability-gate refused repeatedly)." >&2
    continue
  fi
  # DETENTION-REDLINE: scope the tier chain to THIS ticket's work_class (read from its board file)
  # and drop HARD-detained models BEFORE the run. Advisory-flagged models stay (loud warning). If the
  # WHOLE chain is HARD-detained, FAIL LOUD + skip — a detained model can only run behind an explicit
  # override, never a silent fall-through. RUN_MODELS is what actually feeds the work client below.
  wclass="$(awk -F': ' '$1=="work_class"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  if [ -n "$wclass" ]; then
    if run_line="$(detention_filter_chain "$wclass" "${MODELS[@]}")"; then
      IFS=',' read -r -a RUN_MODELS <<<"$run_line" || true
    else
      echo "[$DROID] SKIP $id: ALL eligible models detained for work_class '$wclass' — needs escalation or a heavily-tested run/override. NOT running a detained model." >&2
      bash "$FLEET/release.sh" "$id" >/dev/null 2>&1 || true; current=""
      bash "$FLEET/loop-guard.sh" record "$id" "$DROID" >/dev/null 2>&1 \
        || echo "[$DROID] LOOP-GUARD: $id quarantined (all models detained for '$wclass')." >&2
      continue
    fi
  else
    echo "[$DROID] WARNING: $id has no work_class field — detention filter cannot scope; running the FULL chain unfiltered." >&2
    RUN_MODELS=("${MODELS[@]}")
  fi
  pfile="$(awk -F': ' '$1=="prompt"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  spec="$(cat "$tfile"; echo; echo '--- WORK SPEC ---'; cat "$pfile" 2>/dev/null || echo '(no prompt file)')"
  branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  # MULTI-REPO: resolve the ticket's target repo (`repo:` field; absent -> charon product).
  # RR_PATH/RR_WT/RR_BASE/RR_GATE come from repo-registry.sh; owner/repo is derived (not hardwired).
  repokey="$(awk -F': ' '$1=="repo"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
  if ! repo_resolve "$repokey" "$id"; then
    echo "[$DROID] $id names UNKNOWN repo '$repokey' (known: $(repo_known_keys)) — releasing; fix the ticket's repo: field." >&2
    bash "$FLEET/release.sh" "$id" || true; current=""; continue
  fi
  REPO="$RR_PATH"; wt="$RR_WT"; base_ref="origin/$RR_BASE"
  echo "[$DROID] $id -> repo=$RR_KEY ($REPO) base=$RR_BASE worktree=$wt"
  # #1 WORKTREE-LEAK GUARD (a): the LAUNCHER creates the worktree off the repo's base branch
  # BEFORE the model runs, so the create/cd step is out of the model's hands — a model that
  # ignores it can no longer land in the main checkout undetected. On failure we FAIL LOUDLY and
  # never launch into the main checkout. A live needs-push marker means committed-but-unlanded
  # work is sitting in that worktree — REFUSE to re-run (would risk destroying it); manager lands.
  npmark="$FLEET/state/needs-push/$id"
  mkdir -p "$(dirname "$wt")"
  set +e; leak_worktree_setup "$REPO" "$wt" "$branch" "$npmark" "$base_ref"; lg_rc=$?; set -e
  if [ "$lg_rc" -eq 2 ]; then
    echo "[$DROID] $id has committed-but-unlanded work (state/needs-push/$id) — NOT re-running (would risk its worktree). Land it: fleet/land-needs-push.sh $id. Keeping claim; next…" >&2
    current=""   # keep the claim marker so it isn't re-offered; manager lands it
    continue
  elif [ "$lg_rc" -ne 0 ]; then
    echo "[$DROID] FATAL: could not create worktree $wt off $base_ref — REFUSING to launch into the main checkout $REPO. Releasing $id for retry." >&2
    bash "$FLEET/release.sh" "$id" || true; current=""
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
      || echo "[$DROID] LOOP-GUARD: $id quarantined (repeated worktree-create failures)."
    continue
  fi
  # Snapshot the main checkout so the post-session leak detector can spot NEW stray work in it.
  main_before="$(git -C "$REPO" status --porcelain 2>/dev/null)"
  # LAUNCHER NOTE wins over JOIN-PROMPT step 1: the worktree already exists and is the CWD.
  launcher_note="=== LAUNCHER NOTE (overrides step 1 of the join prompt) ===
Your isolated worktree ALREADY EXISTS and is your current working directory:
  $wt   (branch $branch, freshly created off $base_ref by the launcher)
Do NOT run 'git worktree add' or 'git worktree remove'. SKIP the worktree-creation step.
Verify you are in $wt (run: pwd), then begin at the implementation step. NEVER edit the main
checkout $REPO — only files under $wt.
"
  prompt="$launcher_note
$(cat "$FLEET/JOIN-PROMPT.md")

=== YOUR ASSIGNED TICKET: $id ===
$spec"
  # OFF-CLAUDE EXECUTION (the ONE step that changed): run the droid's work THROUGH THE GATEWAY via
  # the swappable client ($CHARON_AGENT_CMD), NOT `claude -p`. `claude -p` speaks the Anthropic
  # Messages API directly (no ANTHROPIC_BASE_URL) and burns Claude tokens; the gateway client routes
  # `charon/<model>` to 4-LOM (non-Claude models, cheapest-usage-first, roll-to-next-on-exhaust). The
  # prompt becomes the client's BRIEF FILE; the tier's gateway chain ($MODELS) drives cross-model
  # failover. The client cds into the worktree itself (its <cwd> arg). Success == exit 0 (charon-run.sh
  # returns 0 on a model success, non-zero when every model in the chain is exhausted).
  brief="$FLEET/state/agent-briefs/$DROID-$id.md"; mkdir -p "$(dirname "$brief")"
  printf '%s' "$prompt" > "$brief"
  outlog="$FLEET/state/agent-logs/$DROID-$id.txt"; mkdir -p "$(dirname "$outlog")"
  if "$CHARON_AGENT_CMD" "$wt" "$outlog" "$brief" "${RUN_MODELS[@]}"; then
    # #1 WORKTREE-LEAK GUARD (b): did the droid leak into the main checkout instead of its worktree?
    # (0 commits AND clean worktree AND the main checkout gained NEW porcelain entries.)
    if [ "$(leak_detect "$REPO" "$wt" "$branch" "$main_before" "$base_ref")" = LEAK ]; then
      lf="$(leak_capture "$REPO" "$id" "$FLEET/state/leaks")"
      {
        echo ""
        echo "[$DROID] !!! LEAK DETECTED for $id !!! The droid wrote into the MAIN checkout"
        echo "[$DROID]     $REPO instead of its worktree (0 commits, clean worktree, main newly dirty)."
        echo "[$DROID]     Stray work CAPTURED (quarantined) -> $lf"
        echo "[$DROID]     Main checkout LEFT UNTOUCHED for manager recovery. NOT releasing/publishing $id."
        echo "[$DROID]     MANAGER: recover from the capture, clean $REPO, then 'fleet/release.sh $id'."
      } >&2
      current=""   # keep the claim so the ticket isn't re-run over the un-recovered leak
      continue
    fi
    # The droid committed its work on its branch but does NOT push or open the PR: the
    # deny-list blocks `git push`/`gh pr create` inside the Claude session (even with
    # --dangerously-skip-permissions, which does NOT bypass deny rules). So the LAUNCHER
    # publishes here in plain operator-shell — NOT a Claude Bash tool call — so the
    # deny-list never applies. Read <branch> from the ticket via the same awk meta pattern.
    branch="$(awk -F': ' '$1=="branch"{sub(/^[^:]*: ?/,"");print;exit}' "$tfile")"
    # wt / REPO / base_ref already resolved above from the ticket's repo: field (multi-repo).
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
    if [ -z "$(git -C "$wt" log --oneline "$base_ref..$branch" 2>/dev/null)" ]; then
      echo "[$DROID] $id produced NO commits and NO changes — releasing for retry (nothing to publish)."
      bash "$FLEET/release.sh" "$id" || true; current=""
      # LOOP-GUARD: count this zero-commit release. After N (default 2) of the SAME id in this
      # run, loop-guard.sh quarantines it (claim.sh then skips it) so we can't spin forever on
      # a parked/blocked/bad-prompt ticket and starve the next ready one. It prints the
      # escalation itself and exits 2 on quarantine.
      bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
        || echo "[$DROID] LOOP-GUARD: $id quarantined for this board — skipping it from now on."
      continue
    fi
    # Drop any stale remote branch from a prior/closed PR so the push fast-forwards, then
    # push + open the DRAFT PR. If either fails, fall through: submit.sh grounds on a real
    # open PR and flags state/needs-push when there isn't one. `|| true` keeps set -e happy.
    git -C "$wt" push origin --delete "$branch" 2>/dev/null || true
    # Title from the commit subject, NOT `--fill`: the worktree has no local base
    # ref, so `--fill` (which computes `base...branch`) fails and no PR opens. A
    # commit-subject title needs no base ref and is robust.
    pr_title="$(git -C "$wt" log -1 --pretty=%s 2>/dev/null || echo "$id")"
    # MULTI-REPO: PR target owner/repo is DERIVED from the ticket's repo (not hardwired to
    # SLOP-Platform/charon); base is the repo's base branch (master for charon, main for keystone).
    owner_repo="$(repo_owner_repo "$REPO")"
    git -C "$wt" push -u origin "$branch" \
      && gh pr create --repo "$owner_repo" --base "$RR_BASE" --head "$branch" --draft \
           --title "$pr_title" \
           --body "Automated draft PR for $id. See the commit and docs/review-log/$id.md." \
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
    # LOOP-GUARD: a non-zero exit is also a zero-commit release — count it so repeated
    # hard failures on the SAME id are quarantined rather than re-claimed forever.
    bash "$FLEET/loop-guard.sh" record "$id" "$DROID" \
      || echo "[$DROID] LOOP-GUARD: $id quarantined for this board (repeated non-zero exits) — skipping it from now on."
    echo "[$DROID] $id session exited non-zero — released for retry."
  fi
done
