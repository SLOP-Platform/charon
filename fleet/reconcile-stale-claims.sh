#!/usr/bin/env bash
# reconcile-stale-claims.sh — IDEMPOTENT STALE-CLAIM RECONCILER (STALE-CLAIM-RECONCILE).
#
# ROOT (CLAIM-INTEGRITY-EVAL T2, operator RED LINE): a droid that dies (SIGKILL / OOM / terminal
# close) leaves its claim marker (state/claims/<id>) behind. reap-orphans.sh preserves/releases the
# BRANCH/worktree; this tool answers the ORTHOGONAL question the claim marker encodes — "is this
# ticket actually DONE?" — and either RETIRES it with merge-proof or HOLDS it LOUD. The red line
# (see [[claim-integrity-no-reclaim-red-line]]): a claim whose work is NOT merged must NEVER be
# released into a re-claimable void — that silent release is leak #3 (the pool re-offers a ticket
# whose rejected/unpushed work then gets silently discarded on the next `git worktree add -B`).
#
# FORMATS — both live claim shapes are read through the ONE canonical reader in _lib.sh
# (claim_owner / claim_worktree / claim_liveness / claim_unreadable_report):
#   • Legacy: `<droid-id> <iso-ts>` (claim.sh line-1 printf).
#   • Lease:  a `key: value` block (work-lease.sh:write_lease / session-bridge MCP); the owner
#             is the `session:` field, liveness falls back to `heartbeat:` when it has no PID.
# This file previously carried PRIVATE copies of that grammar and reap-orphans.sh carried a
# THIRD copy which had drifted off the on-disk format entirely. One grammar, one home.
#
# ADOPT-FIRST (no second merge-check, no second PID-check):
#   • DEAD/ALIVE — _lib.sh:claim_liveness, PID-first (`kill -0`, ground truth) with a
#     `heartbeat:` + threshold fallback for lease owners that carry no PID. This script
#     creates no second liveness signal, and an UNREADABLE claim is LOUD + fail-closed.
#   • MERGE-PROOF — done.sh is THE sanctioned marker writer: its merge-proof (merged_pr_for_branch /
#     merged_pr_touching_owns, done.sh:35-68/132-148) writes the terminal marker AND removes the
#     claim ONLY when the merge is proven, and fail-closes (exit 3, NOTHING touched) otherwise.
#     We DRIVE `done.sh <id>` and read the OUTCOME off the claim file — the authoritative retire.
#   • PREVIEW — dry-run uses the canonical read-only proof `verify-merged.sh <id>` (a thin CLI over
#     _lib.sh:verify_merged, the ONE source of truth), so a preview never mutates anything.
#
# WORKTREE GUARDS (CLAIM-RECONCILE-INERT accept-3):
#   A claim whose worktree has uncommitted changes or unpushed commits is NEVER released — the
# same invariants as branch-reaper.sh's _rp_keep_reason / _lg_wt_target_ok. A claim file that
# already has a terminal done-marker (state/done/<id>) AND whose branch is landed in master
# is released DIRECTLY (no done.sh re-invocation).
#
# Usage:  fleet/reconcile-stale-claims.sh [--apply] [--orphans]
#   default = DRY-RUN (classify every claim, PREVIEW merged/held via verify-merged.sh; no writes).
#   --apply = for each DEAD claim: merged -> retire; unmerged -> HOLD.
# LIVE claims are NEVER touched (same invariant as reap-orphans.sh).
#   --orphans = ORPHAN CLASSIFICATION MODE (ORPHAN-CLAIM-FORENSICS):
#     walks state/{claims,submitted,done}/<id> and classifies EVERY marker whose ticket ID
#     matches NO board ticket (orphan-marker REDs) into one of three buckets:
#       residue-safe-to-clear  — has merge-proof (sha/PR/override) OR a branch tip that's an
#                                ancestor of master; work is provably landed; SAFE under --apply.
#       work-at-risk           — has unlanded commits OR a dirty / unpushed worktree; NEVER cleared,
#                                surfaced to operator with the branch path so they can decide to
#                                land or retire.
#       unknown                — no branch, no proof, no worktree path; fail closed — NEVER cleared.
#     Default is DRY-RUN (print classification). With `--orphans --apply`, ONLY residue files are
#     removed (work-at-risk + unknown are NEVER auto-touched — same RED LINE as the rest of this
#     script). The legacy claim-walk loop is unchanged — `--orphans` is a SEPARATE operation that
#     runs in ADDITION to the stale-claim walk (still DRY-RUN by default; --apply operates BOTH).
#
# Env (test seams, all honoured by the tools we drive — we add NO new seam):
#   RECONCILE_FLEET_DIR   override the fleet DATA dir (board/state) for test isolation.
#   RECONCILE_STALE_S     staleness threshold for heartbeat-based liveness (default 900).
#   RECONCILE_CHAON_REPO  CHaon (charon / product) repo path for orphan ancestor-of-master checks
#                         (default /home/stack/code/charon, set CHARON_REPO to override globally).
#   RECONCILE_RIG_REPO    rig (charon-private) repo path for orphan ancestor-of-master checks
#                         (default /home/stack/charon-private, set this to override).
#   VERIFY_MERGED_FIXTURE / DONE_MERGED_SRC / DONE_CHARON_REPO — the EXISTING verify-merged.sh /
#     done.sh offline hooks; set them and this reconciler is fully hermetic (see the .test.sh).
set -uo pipefail
FLEET="${RECONCILE_FLEET_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; STATE="$FLEET/state"; CLAIMS="$STATE/claims"
STALE_S="${RECONCILE_STALE_S:-900}"
CHARON_REPO="${RECONCILE_CHARON_REPO:-${CHARON_REPO:-/home/stack/code/charon}}"
RIG_REPO="${RECONCILE_RIG_REPO:-/home/stack/charon-private}"

APPLY=0; ORPHANS=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    --orphans) ORPHANS=1 ;;
    -h|--help) sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//; /^set -uo/d'; exit 0 ;;
    *) echo "reconcile-stale-claims: unknown arg '$arg' (expected --apply/--orphans)" >&2; exit 2 ;;
  esac
done

# CANONICAL CLAIM READER — claim_owner / claim_worktree / claim_liveness /
# claim_unreadable_report all live in _lib.sh now. This file used to carry PRIVATE copies of
# claim_field / is_bridge_format / pid_from_droid, and reap-orphans.sh carried a THIRD,
# different copy that had already drifted off the on-disk format. One grammar, one home.
# Sourced BEFORE this file's own archive-aware canon(), which therefore still wins.
# shellcheck source=_lib.sh
. "$SRC/_lib.sh"

# claim_field keeps ONE legacy-shape convenience the shared reader deliberately omits: on a
# legacy one-liner the second field is the ISO claim timestamp, which this script displays.
claim_ts(){
  local cf="$1" v
  if claim_is_lease "$cf"; then v="$(claim_field claimed "$cf")"
  else v="$(awk 'NR==1{print $2; exit}' "$cf" 2>/dev/null)"; fi
  [ -n "$v" ] && printf '%s' "$v"
}

# canon: case-insensitive board+archive lookup (mirrors done.sh / reap-orphans.sh canon()).
canon(){ local w="$1" f b; for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
  [ -e "$f" ] || continue; b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  return 1; }

# _has_dirty <worktree> — true if the worktree has uncommitted changes (modified or untracked).
_has_dirty(){
  local wt="$1"
  [ -d "$wt/.git" ] || [ -f "$wt/.git" ] || return 1        # unreadable -> fail closed (dirty)
  command -v git >/dev/null 2>&1 || return 1                 # no git -> cannot check
  local out; out="$(git -C "$wt" status --porcelain 2>/dev/null)" || return 1  # status error -> dirty
  [ -z "$out" ]
}

# _has_unpushed <worktree> — true if HEAD has commits not on any remote ref.
_has_unpushed(){
  local wt="$1"
  [ -d "$wt/.git" ] || [ -f "$wt/.git" ] || return 1        # unreadable -> fail closed
  command -v git >/dev/null 2>&1 || return 1
  local ahead; ahead="$(git -C "$wt" rev-list --count HEAD --not --remotes 2>/dev/null)" || return 1
  [ "$ahead" -gt 0 ] 2>/dev/null
}

# ════════════════════════════════════════════════════════════════════════════
# ORPHAN CLASSIFIER (--orphans mode)
# Used by both the default loop (informational line at top of output) and
# the dedicated orphan walker when `--orphans` is passed. The taxonomy:
#   residue-safe-to-clear : merge-proof (done-marker) OR branch tip ancestor of master
#   work-at-risk          : worktree with uncommitted OR unpushed commits
#   unknown               : default for any case that cannot be determined
# ────────────────────────────────────────────────────────────────────────────

# _repo_search_branches <id> -> "<repo> <branch> <sha>" of the first matching branch,
# searching both CHARON_REPO and RIG_REPO.  Match is ref-name substring (case-insensitive)
# because orphan slugs are NOT reliably verbatim ticket ids (e.g. BOUNCE-1 →
# feat/bounce-1-egress-canary-realsut). Returns 1 if nothing found.
_repo_search_branches(){
  local id="$1" hit repo="" br="" sha=""
  for repo in "$CHARON_REPO" "$RIG_REPO"; do
    [ -d "$repo/.git" ] || continue
    hit="$(git -C "$repo" for-each-ref --format='%(refname:short) %(objectname:short)' refs/heads 2>/dev/null \
            | awk -v IGNORECASE=1 -v id="$id" 'tolower($1) ~ tolower(id) {print $1, $2; exit}')"
    [ -n "$hit" ] && { echo "$repo $hit"; return 0; }
  done
  return 1
}

# _sha_ancestor_of_master <repo> <sha> -> 0 if sha is an ancestor of the repo's master, 1 otherwise.
_sha_ancestor_of_master(){
  local repo="$1" sha="$2"
  [ -d "$repo/.git" ] || return 1
  command -v git >/dev/null 2>&1 || return 1
  git -C "$repo" merge-base --is-ancestor "$sha" master 2>/dev/null
}

# _worktree_repo <wt> -> echoes the worktree's git toplevel (the repo it lives in),
# empty if unknown.  This is the authoritative repo for ancestry checks on a per-worktree
# basis — orphan claims may point to a worktree in a repo OTHER than the configured
# CHARON_REPO / RIG_REPO (e.g. a worktree from a different fixture in tests, or an
# operator's ad-hoc checkout of a product commit).  The classifier MUST try this repo
# before falling back to the env-var roots.
_worktree_repo(){ git -C "$1" rev-parse --show-toplevel 2>/dev/null; }

# classify_marker <bucket> <id>
#   bucket: 'claims' | 'submitted' | 'done'
#   Prints one of: RESIDUE / WORK-AT-RISK / UNKNOWN and an evidence note on STDERR.
#   Returns 0 on RESIDUE, 10 on WORK-AT-RISK, 20 on UNKNOWN.
classify_marker(){
  local sub="$1" id="$2"
  case "$sub" in
    done)
      # merge-proof is decisive: 'merged:*' (sha or #PR) OR 'override:<reason>'.
      # The done-marker itself is the operator's INTENT for retirement — the
      # ticket file vanishing is the only RED this addresses.
      local marker="$STATE/done/$id" proof
      if [ ! -f "$marker" ]; then
        echo "UNKNOWN:done:$id:done-marker file vanished mid-classify — fail closed" >&2
        return 20
      fi
      proof="$(awk -F'\t' 'NR==1{print $2; exit}' "$marker" 2>/dev/null)"
      case "$proof" in
        merged:*|override:*)
          echo "RESIDUE:done:$id:merge-proof: $proof" >&2
          return 0 ;;
        *)
          echo "UNKNOWN:done:$id:no merge-proof in done-marker (got '${proof:-EMPTY}') — fail closed" >&2
          return 20 ;;
      esac
      ;;
    submitted)
      # A submitted marker = a PR was filed for the ticket. If the matching
      # branch tip is ancestor of master, the work landed (merge-drop erased
      # the ticket file). Otherwise it's work-in-flight and the ticket-loss
      # is OPERATOR-INVESTIGATION-REQUIRED: fail closed.
      local hit
      if hit="$(_repo_search_branches "$id" 2>/dev/null)"; then
        local repo br sha
        repo="${hit%% *}"; rest="${hit#* }"; br="${rest%% *}"; sha="${rest#* }"
        if _sha_ancestor_of_master "$repo" "$sha"; then
          echo "RESIDUE:submitted:$id:branch $br@$sha ancestor of master in $repo" >&2
          return 0
        fi
        echo "WORK-AT-RISK:submitted:$id:branch $br@$sha exists in $repo but NOT yet ancestor of master — in-flight" >&2
        return 10
      fi
      echo "UNKNOWN:submitted:$id:no matching branch across repos; bare submitted timestamp; operator must investigate" >&2
      return 20
      ;;
    claims)
      local cf="$STATE/claims/$id" wt=""
      [ -f "$cf" ] && wt="$(claim_field worktree "$cf" 2>/dev/null)"
      if [ -n "$wt" ] && [ -d "$wt" ]; then
        if ! _has_dirty "$wt"; then
          local dirty_ex; dirty_ex="$(git -C "$wt" status --porcelain 2>/dev/null | tr '\n' ',')"
          echo "WORK-AT-RISK:claims:$id:worktree $wt has uncommitted changes ($dirty_ex)" >&2
          return 10
        fi
        local wt_sha; wt_sha="$(git -C "$wt" rev-parse HEAD 2>/dev/null)"
        for repo in "$CHARON_REPO" "$RIG_REPO" "$(_worktree_repo "$wt")"; do
          [ -d "$repo/.git" ] || continue
          if _sha_ancestor_of_master "$repo" "$wt_sha"; then
            echo "RESIDUE:claims:$id:worktree clean; HEAD $wt_sha ancestor of master in $repo" >&2
            return 0
          fi
        done
        # Worktree clean and clean of unpushed (not flagging unpushed separately
        # would miss the contract — use the SAME --not --remotes semantic as the
        # legacy _has_unpushed so that a commit pushed to ANY remote counts).
        if _has_unpushed "$wt"; then
          echo "WORK-AT-RISK:claims:$id:worktree $wt has unpushed commits (HEAD $wt_sha)" >&2
          return 10
        fi
        # Worktree clean + fully-pushed + not on master anywhere = stranded.
        echo "WORK-AT-RISK:claims:$id:worktree $wt (HEAD $wt_sha) clean + pushed but NOT ancestor of master — stranded" >&2
        return 10
      fi
      # No worktree path. Fall back to the BRANCH search: maybe the worktree was
      # reaped but the branch still exists with all commits on master.
      local hit
      if hit="$(_repo_search_branches "$id" 2>/dev/null)"; then
        local repo br sha
        repo="${hit%% *}"; rest="${hit#* }"; br="${rest%% *}"; sha="${rest#* }"
        if _sha_ancestor_of_master "$repo" "$sha"; then
          echo "RESIDUE:claims:$id:no live worktree, but branch $br@$sha ancestor of master in $repo" >&2
          return 0
        fi
        echo "WORK-AT-RISK:claims:$id:no live worktree; branch $br@$sha exists in $repo but NOT yet ancestor of master" >&2
        return 10
      fi
      echo "UNKNOWN:claims:$id:no worktree + no matching branch — fail closed" >&2
      return 20
      ;;
  esac
  echo "UNKNOWN:$sub:$id:unclassified subdir — fail closed" >&2
  return 20
}

n_live=0; n_retired=0; n_held=0; n_skipped=0; n_would_retire=0; n_would_hold=0; n_unreadable=0
n_orphan_residue=0; n_orphan_held=0; n_orphan_walked=0
n_orphan_would_retire=0; n_orphan_would_hold=0

if [ "$APPLY" -eq 1 ]; then echo "reconcile-stale-claims: APPLY mode (merged->retire via done.sh; unmerged->HOLD; orphans->RESIDUE removed only)"
else echo "reconcile-stale-claims: DRY-RUN (pass --apply to retire merged / flag held claims / remove residue)"; fi
echo "reconcile-stale-claims: fleet=$FLEET claims_dir=$CLAIMS stale_threshold=${STALE_S}s orphan_mode=$ORPHANS"
echo

if [ ! -d "$CLAIMS" ]; then
  echo "reconcile-stale-claims: no claims dir ($CLAIMS) — nothing to do."
  # Still run the orphan walker if --orphans is set; it operates on submitted/done.
  if [ "$ORPHANS" -ne 1 ]; then exit 0; fi
  files=()
else
  shopt -s nullglob
  files=( "$CLAIMS"/* )
  shopt -u nullglob
  [ "${#files[@]}" -gt 0 ] || {
    echo "reconcile-stale-claims: no claims present — nothing to do."
    # Still run the orphan walker if --orphans is set; it operates on submitted/done.
    if [ "$ORPHANS" -ne 1 ]; then exit 0; fi
    files=()
  }
fi

for cf in "${files[@]}"; do
  [ -f "$cf" ] || continue
  id_raw="$(basename "$cf")"
  id_display="$id_raw"

  # ── liveness check — ONE canonical reader (_lib.sh:claim_liveness) ─────
  # This block used to branch on format itself and keep a private copy of the grammar; the
  # else-arm then read the owner with `awk '{print $1}'`, the same read that had already
  # silently broken reap-orphans.sh. claim_liveness is PID-first with a heartbeat fallback,
  # so a lease whose `session:` is `<tier>-<pid>` is now judged by `kill -0` (ground truth)
  # rather than by a heartbeat a dead process can no longer contradict.
  live_reason="$(claim_liveness "$cf" "$STALE_S")"; live_rc=$?
  if [ "$live_rc" -eq 2 ]; then
    # UNREADABLE. LOUD + FAIL-CLOSED: reported to stderr as a finding, claim KEPT. Never
    # release a claim we cannot parse — that can hand a live droid's ticket to a second one.
    claim_unreadable_report "$cf" reconcile-stale-claims "$live_reason"
    echo "UNREADABLE  $id_raw  ($live_reason) — claim HELD, NOT released; reported as an ERROR"
    n_skipped=$((n_skipped+1)); n_unreadable=$((n_unreadable+1)); continue
  fi
  droid_id="$(claim_owner "$cf")" || droid_id=""
  [ -n "$droid_id" ] || droid_id="bridge"
  wt="$(claim_worktree "$cf" 2>/dev/null)" || wt=""
  if [ "$live_rc" -eq 0 ]; then
    echo "LIVE    $id_raw  droid=$droid_id ($live_reason — left untouched)"
    n_live=$((n_live+1)); continue
  fi
  echo "STALE   $id_raw  droid=$droid_id ($live_reason)"

  # ── worktree guard: protect live work BEFORE canon ────────────────────
  # A claim whose worktree is dirty or has unpushed commits is NEVER released,
  # regardless of done-marker status. Live work is more important than board
  # hygiene. This check runs FIRST — its verdict is absolute.
  if [ -n "$wt" ] && [ -d "$wt" ]; then
    if ! _has_dirty "$wt"; then
      if [ "$APPLY" -eq 1 ]; then
        echo "!!!!!! HOLD  $id_raw  droid=$droid_id — worktree $wt has uncommitted changes; claim HELD, NOT released" >&2
        n_held=$((n_held+1))
      else
        echo "would HOLD    $id_raw  droid=$droid_id — worktree $wt has uncommitted changes"
        n_would_hold=$((n_would_hold+1))
      fi
      continue
    fi
    if _has_unpushed "$wt"; then
      if [ "$APPLY" -eq 1 ]; then
        echo "!!!!!! HOLD  $id_raw  droid=$droid_id — worktree $wt has unpushed commits; claim HELD, NOT released" >&2
        n_held=$((n_held+1))
      else
        echo "would HOLD    $id_raw  droid=$droid_id — worktree $wt has unpushed commits"
        n_would_hold=$((n_would_hold+1))
      fi
      continue
    fi
  fi

  # ── done-marker fast path: check by raw id (no canon needed) ───────────
  # Canonical lookup is for board-ticket resolution; a done-marker
  # exists independently. Check raw id first, then fall back to canonical.
  done_id=""
  if [ -e "$STATE/done/$id_raw" ]; then
    done_id="$id_raw"
  elif id_canon="$(canon "$id_raw" 2>/dev/null)" && [ -n "$id_canon" ] && [ -e "$STATE/done/$id_canon" ]; then
    done_id="$id_canon"
    id_display="$id_canon"
  fi

  if [ -n "$done_id" ]; then
    echo "HAS-DONE-MARKER  ${id_display:-$id_raw}  droid=$droid_id"
    if [ "$APPLY" -eq 1 ]; then
      rm -f "$cf"
      echo "RETIRED ${id_display:-$id_raw}  droid=$droid_id — done-marker present; stale claim removed"
      n_retired=$((n_retired+1))
    else
      echo "would RETIRE  ${id_display:-$id_raw}  droid=$droid_id — done-marker present; stale claim would be removed"
      n_would_retire=$((n_would_retire+1))
    fi
    continue
  fi

  # ── no done-marker, worktree state unknown -> fail closed ──────────────
  # A worktree path set but not a readable directory (deleted, broken,
  # nonexistent) means state cannot be determined -> HOLD. Only applies to
  # claims WITHOUT a done-marker (done-marker is authoritative proof).
  if [ -n "$wt" ] && [ ! -d "$wt" ]; then
    if [ "$APPLY" -eq 1 ]; then
      echo "!!!!!! HOLD  $id_raw  droid=$droid_id — worktree $wt is not a readable directory (deleted/broken); claim HELD, NOT released" >&2
      n_held=$((n_held+1))
    else
      echo "would HOLD    $id_raw  droid=$droid_id — worktree $wt is not a readable directory (deleted/broken)"
      n_would_hold=$((n_would_hold+1))
    fi
    continue
  fi

  # ── resolve canonical board id ─────────────────────────────────────────
  if ! id="$(canon "$id_raw" 2>/dev/null)"; then
    # ORPHAN-MARKER path — the board ticket is missing for THIS claim. This is the
    # case --orphans is designed to classify. Surface classification output if
    # the operator asked for it; otherwise the existing 'HOLD' behavior remains.
    if [ "$ORPHANS" -eq 1 ]; then
      if classify_marker "claims" "$id_raw" 2>/dev/null; then
        # RESIDUE — work landed; safe to clear under --apply (this is the only
        # bucket that may be auto-removed).
        if [ "$APPLY" -eq 1 ]; then
          rm -f "$cf"
          echo "ORPHAN-RETIRED claims:$id_raw droid=$droid_id — residue; cleared (merge-proof/branch-ancestor)"
          n_orphan_residue=$((n_orphan_residue+1))
        else
          echo "would ORPHAN-RETIRE claims:$id_raw droid=$droid_id — residue"
        fi
      else
        # WORK-AT-RISK OR UNKNOWN — never auto-cleared (RED LINE), held loud.
        classify_marker "claims" "$id_raw" >&2
        if [ "$APPLY" -eq 1 ]; then
          echo "!!!!!! ORPHAN-HOLD claims:$id_raw droid=$droid_id — work-at-risk/unknown; claim HELD, NOT released" >&2
          n_orphan_held=$((n_orphan_held+1))
        else
          echo "would ORPHAN-HOLD claims:$id_raw droid=$droid_id — work-at-risk/unknown"
        fi
      fi
      continue
    fi
    # Legacy path (--orphans not requested): hold loud, identical to before.
    echo "!! HOLD  $id_raw  droid=$droid_id (DEAD) — no board/archive ticket; cannot merge-prove -> HELD, NOT released" >&2
    n_held=$((n_held+1)); continue
  fi
  id_display="$id"

  # ── merge-proof path (no done-marker, no worktree blocks) ───────────────
  if [ "$APPLY" -eq 0 ]; then
    if bash "$SRC/verify-merged.sh" "$id" >/dev/null 2>&1; then
      echo "would RETIRE  $id_display  droid=$droid_id (DEAD, merge-proven) -> done.sh would write the terminal marker + drop the claim"
      n_would_retire=$((n_would_retire+1))
    else
      echo "would HOLD    $id_display  droid=$droid_id (DEAD, NOT merge-proven) -> claim KEPT (never released into a re-claimable void)"
      n_would_hold=$((n_would_hold+1))
    fi
    continue
  fi

  # APPLY: drive the sanctioned writer.
  proof_out="$(bash "$SRC/done.sh" "$id" 2>&1)"; drc=$?
  if [ ! -e "$cf" ]; then
    echo "RETIRED $id_display  droid=$droid_id — MERGED; terminal marker written, stale claim removed (done.sh)."
    n_retired=$((n_retired+1))
  else
    reason="$(printf '%s' "$proof_out" | grep -iE 'REFUSED|no MERGED PR|NOT an ancestor|cannot resolve' | head -1 | sed 's/^[[:space:]]*//')"
    [ -n "$reason" ] || reason="done.sh did not merge-prove $id (exit $drc)"
    echo "!!!!!! HOLD  $id_display  droid=$droid_id — UNMERGED work; claim HELD, NOT released." >&2
    echo "!!!!!! HOLD  $id_display  reason: $reason" >&2
    echo "!!!!!! HOLD  $id_display  rebuild+merge the ticket, or close it explicitly (done.sh $id --override \"<reason>\") before the pool re-offers it." >&2
    n_held=$((n_held+1))
  fi
done

# ════════════════════════════════════════════════════════════════════════════
# ORPHAN MARKER WALKER (--orphans mode)
# Walks state/{submitted,done}/<id> for orphan markers. The state/claims/<id>
# orphans are caught in the legacy loop above (the canon-failed branch). This
# block handles ONLY the non-claims subdirs: submitted and done.
# ────────────────────────────────────────────────────────────────────────────
if [ "$ORPHANS" -eq 1 ]; then
  for sub in submitted done; do
    [ -d "$STATE/$sub" ] || continue
    shopt -s nullglob
    orphans_in_sub=( "$STATE/$sub"/* )
    shopt -u nullglob
    [ "${#orphans_in_sub[@]}" -gt 0 ] || continue
    for f in "${orphans_in_sub[@]}"; do
      [ -f "$f" ] || continue
      id="$(basename "$f")"
      # Skip markers whose ticket is on the board — not actually an orphan.
      if canon "$id" >/dev/null 2>&1; then continue; fi
      n_orphan_walked=$((n_orphan_walked+1))
      if classify_marker "$sub" "$id" 2>/dev/null; then
        # RESIDUE — merge-proof / branch-ancestor; safe to clear under --apply.
        if [ "$APPLY" -eq 1 ]; then
          rm -f "$f"
          echo "ORPHAN-RETIRED $sub:$id — residue; cleared"
          n_orphan_residue=$((n_orphan_residue+1))
        else
          echo "would ORPHAN-RETIRE $sub:$id — residue"
          n_orphan_would_retire=$((n_orphan_would_retire+1))
        fi
      else
        # WORK-AT-RISK OR UNKNOWN — never auto-cleared; held loud.
        classify_marker "$sub" "$id" >&2
        if [ "$APPLY" -eq 1 ]; then
          echo "!!!!!! ORPHAN-HOLD $sub:$id — work-at-risk/unknown; marker HELD, NOT released" >&2
          n_orphan_held=$((n_orphan_held+1))
        else
          echo "would ORPHAN-HOLD $sub:$id — work-at-risk/unknown"
          n_orphan_would_hold=$((n_orphan_would_hold+1))
        fi
      fi
    done
  done
fi

echo
echo "reconcile-stale-claims: done ($([ "$APPLY" = 1 ] && echo 'applied' || echo 'dry-run'))"
echo "  live (untouched): $n_live"
if [ "$APPLY" -eq 1 ]; then
  echo "  retired (merged): $n_retired"
  echo "  HELD (unmerged):  $n_held"
else
  echo "  would-retire:     $n_would_retire"
  echo "  would-hold:       $n_would_hold"
  echo "  held (unresolved):$n_held"
fi
[ "$n_skipped" -gt 0 ] && echo "  skipped (unreadable): $n_skipped"
if [ "$ORPHANS" -eq 1 ]; then
  echo "  --orphans:"
  echo "    walked:    $n_orphan_walked"
  if [ "$APPLY" -eq 1 ]; then
    echo "    residue:   $n_orphan_residue   (cleared)"
    echo "    held:      $n_orphan_held   (work-at-risk + unknown NEVER auto-cleared)"
  else
    echo "    residue:   ${n_orphan_would_retire:-0}   (would-clear under --apply)"
    echo "    held:      ${n_orphan_would_hold:-0}   (would-HOLD)"
  fi
fi
# An UNREADABLE claim is a FINDING, never a silent skip. It is the failure that froze tickets
# as `claimed` forever with exit 0 and nothing on stderr, so it now exits non-zero.
if [ "$n_unreadable" -gt 0 ]; then
  echo "!!!!!! reconcile-stale-claims: $n_unreadable claim(s) UNREADABLE — see the stderr findings above." >&2
  echo "       NOTHING was released for them (fail-closed). Exiting non-zero on purpose." >&2
  exit 1
fi
exit 0
