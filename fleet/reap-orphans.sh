#!/usr/bin/env bash
# reap-orphans.sh — OUT-OF-BAND DEAD-PID CLAIM SWEEPER (DROID-LIFECYCLE-REAP).
#
# ROOT CAUSE (manager observation 2026-07-16): the in-process `cleanup` trap in
# fleet-droid.sh runs on bash EXIT/INT/TERM — but NOT on SIGKILL or terminal close. A
# Ctrl-C'd / OOM'd / power-cut droid leaves its claim marker (state/claims/<id>) AND its
# worktree alive FOREVER. Consequences:
#   1. STALE-CLAIM STARVATION: the ticket can never be re-claimed (claim.sh sees the
#      marker, skips). The manager has to hand-release the claim.
#   2. CLAIM-RELEASE CHURN: a later re-claim's `git worktree add -B <branch> <base>`
#      SILENTLY DISCARDS the orphaned branch's unmerged commits (reflog: "Created from
#      <base>") — a P0 data-loss path. The new P0 #4 guard in fleet-droid.sh
#      (`p0_worktree_setup`) fixes the silent-discard by REUSE-ing the surviving branch;
#      the cleanup of dead claims is still needed (this script).
#
# THIS SCRIPT: scans state/claims/*, reads the owner + liveness through the ONE canonical
# claim reader (_lib.sh: claim_owner / claim_liveness — it handles BOTH live claim shapes,
# claim.sh's legacy one-liner and work-lease.sh's `key: value` lease block), and for any
# claim whose owner is DEAD acts:
#
#   if branch has origin/master..HEAD unique commits:
#     PRESERVE — the work is valuable.
#       - flag state/orphans/<id> so the manager sees it on the next foreman run.
#       - release the claim (otherwise the ticket is stuck forever).
#       - remove the worktree ONLY if the branch survives the removal (it always does,
#         a worktree remove keeps the branch).
#   else (branch == base, no unique commits):
#     CLEAN — the droid died without doing anything useful.
#       - remove the worktree (safe: nothing committed).
#       - delete the empty branch (it equals base; recreating it == the same commit).
#       - release the claim so the ticket re-claimable.
#
# LIVE-PID claims are NEVER touched. `kill -0 <pid>` on a running process returns 0.
# The reaper is safe to run while live droids hold other claims.
#
# Usage:  fleet/reap-orphans.sh [--apply]
#   default = DRY-RUN (loud print of what would happen, no side effects).
#   --apply = perform the release / worktree-removal / branch-preserve.
#
# Env:
#   REAPER_FLEET_DIR    override the fleet dir (test isolation).
#   REAPER_PRESERVE_SUBMIT   when set, try `submit.sh` for dead-droid branches with
#                            unique commits (push + open DRAFT PR + mark submitted).
#                            Default off — manager lands orphans manually.
#   REAPER_REPO_PATH    override the resolved RR_PATH (test isolation: lets the test
#                        operate on a fixture repo without touching the real charon path).
#   REAPER_WT_PATH      override the resolved RR_WT (test isolation).
#   REAPER_BASE         override the resolved RR_BASE (test isolation; e.g. "master").
#   These are ONLY consumed when REAPER_FLEET_DIR is set — they exist for the test seam
#   and are a no-op in production (where repo-registry's hardcoded paths are correct).
set -uo pipefail
# Two distinct dirs:
#   FLEET  = the DATA dir (board, state). Override with REAPER_FLEET_DIR (test isolation).
#   SRC    = the SCRIPT dir (where this file + repo-registry.sh + leak-guard.sh live).
#            Always this script's own dir, NEVER overridable — we always want the real
#            repo-registry / leak-guard / etc. regardless of the data root.
FLEET="${REAPER_FLEET_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; STATE="$FLEET/state"; CLAIMS="$STATE/claims"
ORPHANS="$STATE/orphans"; SUBMITTED="$STATE/submitted"
APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; exit 0 ;;
    *) echo "reap-orphans: unknown arg '$arg' (expected --apply)" >&2; exit 2 ;;
  esac
done
# shellcheck source=repo-registry.sh
. "$SRC/repo-registry.sh"
# shellcheck source=leak-guard.sh
. "$SRC/leak-guard.sh"

# CANONICAL CLAIM READER (_lib.sh: claim_owner / claim_liveness / claim_unreadable_report).
# Sourced BEFORE this file's own canon(), so the archive-aware canon() below still wins — the
# only thing adopted from _lib.sh here is the claim-file grammar, which must have ONE home.
# shellcheck source=_lib.sh
. "$SRC/_lib.sh"

# canon: case-insensitive board lookup (matches the convention claim.sh / release.sh use)
canon(){ local w="$1" f b; for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
  [ -e "$f" ] || continue; b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  return 1; }
meta(){ awk -F': ' -v k="$1" '$1==k{sub(/^[^:]*: ?/,"");print;exit}' "$2" 2>/dev/null; }

# pid_from_droid / alive — RETIRED as local copies. Droid-id PID parsing is now
# _lib.sh:claim_owner_pid and liveness is _lib.sh:claim_liveness (which is PID-first and
# falls back to `heartbeat:` for lease owners that carry no PID). Two private copies of the
# claim grammar is exactly how this script drifted off the format in the first place.
REAP_STALE_S="${REAPER_STALE_S:-900}"

# safe_wt_remove <repo> <wt> <id> — thin wrapper honoring needs-push (the reaper's
# worktree-removal step). `safe_worktree_remove` is sourced from leak-guard.sh.

n_skipped_live=0; n_dead_clean=0; n_dead_preserve=0; n_errors=0
if [ "$APPLY" -eq 1 ]; then echo "reap-orphans: APPLY mode (releases + removals will occur)"
else echo "reap-orphans: DRY-RUN (pass --apply to actually reap)"; fi
echo "reap-orphans: fleet=$FLEET claims_dir=$CLAIMS"
echo

if [ ! -d "$CLAIMS" ]; then echo "reap-orphans: no claims dir ($CLAIMS) — nothing to do."; exit 0; fi
shopt -s nullglob
files=( "$CLAIMS"/* )
shopt -u nullglob
[ "${#files[@]}" -gt 0 ] || { echo "reap-orphans: no claims present — nothing to do."; exit 0; }

for cf in "${files[@]}"; do
  [ -f "$cf" ] || continue
  id_raw="$(basename "$cf")"
  # resolve to the canonical board id (case-insensitive). If the ticket was archived /
  # removed, the claim is a true orphan — release unconditionally.
  if ! id="$(canon "$id_raw" 2>/dev/null)"; then
    echo "ORPHAN  $id_raw  (no board ticket — releasing stale claim)"
    if [ "$APPLY" -eq 1 ]; then rm -f "$cf"; fi
    n_dead_clean=$((n_dead_clean+1))
    continue
  fi
  # OWNER + LIVENESS via the ONE canonical claim reader (_lib.sh). This script used to read
  # the owner with `awk '{print $1}'` against a comment asserting the legacy one-line shape.
  # work-lease.sh now also writes a `key: value` LEASE block into the SAME directory, and on
  # one of those the awk returned the literal `ticket:`, the PID parse failed, and the whole
  # thing degraded to a SILENT `SKIP` counted as live with exit 0 — so a genuinely dead droid
  # was never reaped and its ticket froze as `claimed` forever.
  live_reason="$(claim_liveness "$cf" "$REAP_STALE_S")"; live_rc=$?
  if [ "$live_rc" -eq 2 ]; then
    # UNKNOWN. LOUD (stderr + non-zero exit) and FAIL-CLOSED: the claim is KEPT. Releasing a
    # claim we cannot parse can hand a live droid's ticket to a second droid.
    claim_unreadable_report "$cf" reap-orphans "$live_reason"
    echo "UNREADABLE  $id  ($live_reason) — claim HELD, reported as an ERROR"
    n_errors=$((n_errors+1)); continue
  fi
  droid_id="$(claim_owner "$cf")" || droid_id="?"
  pid="$(claim_owner_pid "$droid_id" 2>/dev/null)" || pid="-"
  if [ "$live_rc" -eq 0 ]; then
    echo "LIVE    $id  droid=$droid_id pid=$pid ($live_reason — left untouched)"
    n_skipped_live=$((n_skipped_live+1)); continue
  fi
  # DEAD. Resolve the ticket's repo/worktree/branch.
  board_file="$BOARD/$id.md"
  [ -e "$board_file" ] || board_file="$BOARD/archive/$id.md"
  repo_key="$(meta repo "$board_file")"
  branch="$(meta branch "$board_file")"
  if [ -z "$branch" ]; then
    echo "DEAD    $id  droid=$droid_id pid=$pid — no branch on ticket; releasing (no work to preserve)"
    if [ "$APPLY" -eq 1 ]; then rm -f "$cf"; fi
    n_dead_clean=$((n_dead_clean+1)); continue
  fi
  if ! repo_resolve "$repo_key" "$id"; then
    echo "DEAD    $id  droid=$droid_id pid=$pid — UNKNOWN repo '$repo_key'; KEEPING claim (manager must release by hand)"
    n_skipped_live=$((n_skipped_live+1)); continue
  fi
  REPO="$RR_PATH"; WT="$RR_WT"; BASE="$RR_BASE"; BASE_REF="origin/$RR_BASE"
  # TEST-ISOLATION OVERRIDES: when REAPER_FLEET_DIR is set, the test supplies its own
  # paths (the fixture repo is a temp git repo, NOT the real /home/stack/charon). This
  # is a no-op in production (where REAPER_FLEET_DIR is unset and the hardcoded paths
  # from repo-registry are correct). It exists so test_droid_reap.sh can probe the
  # reaper end-to-end without touching the real fleet.
  if [ -n "${REAPER_FLEET_DIR:-}" ]; then
    [ -n "${REAPER_REPO_PATH:-}" ] && REPO="$REAPER_REPO_PATH"
    [ -n "${REAPER_WT_PATH:-}" ]   && WT="$REAPER_WT_PATH"
    [ -n "${REAPER_BASE:-}" ]       && { BASE="$REAPER_BASE"; BASE_REF="origin/$REAPER_BASE"; }
  fi
  # FETCH BEFORE COMPARING (fail-closed fix #2). The reaper never fetched, so on a repo whose
  # `origin/$BASE` had never been fetched (fresh clone, offline droid box, a repo whose base is
  # `main` not `master`) $BASE_REF simply DID NOT RESOLVE. This matches what fleet-droid.sh's
  # p0_worktree_setup already does. `|| true` because offline must not abort the sweep — it must
  # fall through to the fail-closed branch below, which PRESERVES.
  git -C "$REPO" fetch origin --quiet 2>/dev/null || true
  # Compute unique commits on branch vs. base — FAIL CLOSED (fix #1).
  #
  # THE BUG THIS REPLACES: `unique="$(git log … 2>/dev/null | wc -l)"` made `wc -l` the arbiter.
  # `wc -l` counts the lines of an EMPTY stream as 0 whether the branch genuinely has no unique
  # commits OR `git log` failed outright because $BASE_REF does not resolve. Both produced
  # `unique=0`, and 0 fell through to the DEAD+CLEAN arm below — `git branch -D "$branch"`, an
  # unconditional destroy of a branch that may have held every commit a dead droid ever made.
  # Piping through `wc -l` also swallowed git's exit status, so there was no way to tell the two
  # apart after the fact.
  #
  # `_lg_unlanded_count` (leak-guard.sh, reused — fix #5, NOT a second parallel guard) resolves
  # the base FIRST and returns `UNRESOLVABLE` + rc 1 when it cannot. Anything that is not a clean
  # numeric answer means WE DO NOT KNOW, and not knowing must PRESERVE, never clean.
  unique=""; unique_rc=0
  unique="$(_lg_unlanded_count "$REPO" "$branch" "$BASE_REF")" || unique_rc=$?
  case "$unique" in ''|*[!0-9]*) unique_rc=1 ;; esac
  if [ "$unique_rc" -ne 0 ]; then
    # UNKNOWN. Treat exactly as "has work": preserve the branch, preserve the worktree, flag it,
    # release the claim so the ticket is not starved. The manager resolves by hand.
    echo "DEAD+PRESERVE  $id  droid=$droid_id pid=$pid branch=$branch unique=UNKNOWN ('$BASE_REF' unresolvable in $REPO — FAILING CLOSED, keeping branch + worktree)"
    if [ "$APPLY" -eq 1 ]; then
      mkdir -p "$ORPHANS" "$STATE/needs-push"
      printf 'id=%s\ndroid=%s\npid=%s\nbranch=%s\nworktree=%s\nrepo=%s\nbase=%s\nunique_commits=UNKNOWN\nflagged=%s\nreason=dead-droid orphan — base ref %s UNRESOLVABLE, could not prove the branch is empty; preserved by fail-closed guard\n' \
        "$id" "$droid_id" "$pid" "$branch" "$WT" "$REPO" "$RR_BASE" "$(date -u +%FT%TZ)" "$BASE_REF" > "$ORPHANS/$id" || true
      printf 'branch=%s\nworktree=%s\nrepo=%s\nreason=dead-droid orphan, base ref unresolvable (reap-orphans failed closed and preserved branch)\nflagged=%s\n' \
        "$branch" "$WT" "$REPO" "$(date -u +%FT%TZ)" > "$STATE/needs-push/$id" || true
      rm -f "$cf"
    fi
    n_dead_preserve=$((n_dead_preserve+1))
    continue
  fi
  if [ "$unique" -gt 0 ]; then
    # PRESERVE the work. The branch has unmerged commits — the data is valuable. We:
    #   - flag state/orphans/<id> for the manager (diagnostic, foreman surfaces it).
    #   - also flag state/needs-push/<id> so the EXISTING land-needs-push.sh recovery
    #     path (`push + open DRAFT PR + submit.sh`) works on this id without any new
    #     manager tooling. The "needs-push" name is technically about "branch not
    #     pushed yet", but for an orphan the symptom is the same: there's committed
    #     work in the repo's branch that needs a manager-driven land.
    #   - release the claim (else the ticket is stuck forever).
    #   - DO NOT touch the worktree (the P0 #4 guard in fleet-droid.sh reuses it on
    #     re-claim, the manager can inspect it, and a re-claim keeps the branch safe).
    #   - DO NOT delete the branch.
    echo "DEAD+PRESERVE  $id  droid=$droid_id pid=$pid branch=$branch unique=${unique} (work valuable — keep branch + worktree, flag for manager)"
    if [ "$APPLY" -eq 1 ]; then
      mkdir -p "$ORPHANS" "$STATE/needs-push"
      printf 'id=%s\ndroid=%s\npid=%s\nbranch=%s\nworktree=%s\nrepo=%s\nbase=%s\nunique_commits=%s\nflagged=%s\nreason=dead-droid orphan — branch has unmerged commits, manager lands it\n' \
        "$id" "$droid_id" "$pid" "$branch" "$WT" "$REPO" "$RR_BASE" "$unique" "$(date -u +%FT%TZ)" > "$ORPHANS/$id" || true
      # The needs-push marker is the contract land-needs-push.sh reads. Write it in the
      # exact format submit.sh uses (branch / worktree / repo / reason / flagged) so the
      # existing recovery path Just Works.
      printf 'branch=%s\nworktree=%s\nrepo=%s\nreason=dead-droid orphan with unmerged commits (reap-orphans preserved branch)\nflagged=%s\n' \
        "$branch" "$WT" "$REPO" "$(date -u +%FT%TZ)" > "$STATE/needs-push/$id" || true
      # Optionally try submit.sh — pushes + opens PR if needed. Off by default (the
      # LAND contract is "manager pushes", and the reaper is not a lander). Manager
      # can `fleet/land-needs-push.sh $id` to push+open+submit.
      if [ -n "${REAPER_PRESERVE_SUBMIT:-}" ]; then
        bash "$FLEET/submit.sh" "$id" >/dev/null 2>&1 || true
      fi
      # Release the claim. The branch + orphan flag carry the preservation contract.
      rm -f "$cf"
    fi
    n_dead_preserve=$((n_dead_preserve+1))
  else
    # CLEAN — dead droid, no work. Release the claim + remove the worktree + delete the
    # empty branch.
    echo "DEAD+CLEAN  $id  droid=$droid_id pid=$pid branch=$branch unique=0 (no work — safe to clean)"
    if [ "$APPLY" -eq 1 ]; then
      # WORKTREE REMOVAL — go through the ONE sanctioned path and RESPECT ITS REFUSAL (fix #5).
      # This previously read `safe_worktree_remove … || git worktree remove --force … || rm -rf`,
      # which made the guard decorative: safe_worktree_remove returns 2 precisely when the target
      # must not be destroyed (live needs-push marker, uncommitted changes, unpushed commits, the
      # live checkout, $HOME, a worktree-family root) — and the `||` chain then destroyed it
      # anyway with the bluntest tool available. A refusal is now terminal for this id.
      if ! safe_worktree_remove "$REPO" "$WT" "$id" "$STATE/needs-push"; then
        echo "SKIP-CLEAN  $id  leak-guard REFUSED removal of $WT — keeping claim, branch and worktree for the manager"
        n_errors=$((n_errors+1))
        continue
      fi
      # `worktree remove` succeeded (or there was nothing there). Prune so a later
      # `git worktree list` doesn't show a ghost admin entry.
      git -C "$REPO" worktree prune 2>/dev/null || true
      # BRANCH DELETE — prefer `-d` (fix #3). We have positively proven unique==0 above, so `-d`
      # should always succeed here; it is a SECOND, INDEPENDENT check that costs nothing, since
      # git refuses `-d` on a branch holding unmerged commits. `-D` is deliberately NOT used as a
      # fallback: if `-d` refuses, git knows something our count did not, and that disagreement is
      # exactly the signal to stop. Leaving a stale empty branch is free; deleting a live one is not.
      #
      # BENIGN CASE FIRST (F2): the branch may simply NOT EXIST — `_lg_unlanded_count` returns a
      # legitimate 0 for a missing branch, and :154's comment calls this out as EXPECTED (a droid
      # created the worktree then crashed before `git worktree add -B` finalized the branch).
      # `git branch -d` on a missing branch exits 1, which used to be counted as an error and made
      # the WHOLE sweep exit 1 with a message ("git sees unmerged commits") that was simply wrong.
      # Nothing to delete is not a failure — only a REFUSAL to delete an existing branch is.
      if ! git -C "$REPO" rev-parse --verify --quiet "refs/heads/$branch" >/dev/null 2>&1; then
        echo "NO-BRANCH  $id  branch '$branch' does not exist in $REPO — nothing to delete (droid died before the branch was created); not an error"
      elif ! git -C "$REPO" branch -d "$branch" 2>/dev/null; then
        echo "SKIP-BRANCH-DELETE  $id  'git branch -d $branch' REFUSED (git sees unmerged commits though unique==0) — branch kept, investigate by hand"
        n_errors=$((n_errors+1))
      fi
      rm -f "$cf"
    fi
    n_dead_clean=$((n_dead_clean+1))
  fi
done
echo
echo "reap-orphans: done ($([ "$APPLY" = 1 ] && echo 'applied' || echo 'dry-run'))"
echo "  live (untouched): $n_skipped_live"
echo "  dead+preserve:    $n_dead_preserve"
echo "  dead+clean:       $n_dead_clean"
[ "$n_errors" -gt 0 ] && {
  echo "  errors:           $n_errors"
  echo "!!!!!! reap-orphans: $n_errors claim(s) could not be acted on — see the stderr findings above." >&2
  echo "       NOTHING was released for them. A silent skip here is how dead claims freeze tickets," >&2
  echo "       so this exits non-zero on purpose." >&2
  exit 1
}
exit 0
