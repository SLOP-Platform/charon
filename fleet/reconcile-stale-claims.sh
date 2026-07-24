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
# ADOPT-FIRST (no second merge-check, no second PID-check):
#   • DEAD/ALIVE — `<tier>-<pid>` parse + `kill -0` are the SAME semantics as reap-orphans.sh:82-90
#     (pid_from_droid / alive). They live in a run-on script (not a sourceable lib) and this ticket
#     owns only two files, so the 2-line helpers are inlined below with this citation — same rule,
#     not a second implementation.
#   • MERGE-PROOF — done.sh is THE sanctioned marker writer: its merge-proof (merged_pr_for_branch /
#     merged_pr_touching_owns, done.sh:35-68/132-148) writes the terminal marker AND removes the
#     claim ONLY when the merge is proven, and fail-closes (exit 3, NOTHING touched) otherwise.
#     We DRIVE `done.sh <id>` and read the OUTCOME off the claim file — the authoritative retire.
#   • PREVIEW — dry-run uses the canonical read-only proof `verify-merged.sh <id>` (a thin CLI over
#     _lib.sh:verify_merged, the ONE source of truth), so a preview never mutates anything.
#
# Usage:  fleet/reconcile-stale-claims.sh [--apply]
#   default = DRY-RUN (classify every claim, PREVIEW merged/held via verify-merged.sh; no writes).
#   --apply = for each DEAD claim: merged -> `done.sh <id>` (retire-with-proof); unmerged -> HOLD.
# LIVE-PID claims are NEVER touched (same invariant as reap-orphans.sh).
#
# Env (test seams, all honoured by the tools we drive — we add NO new seam):
#   RECONCILE_FLEET_DIR   override the fleet DATA dir (board/state) for test isolation.
#   VERIFY_MERGED_FIXTURE / DONE_MERGED_SRC / DONE_CHARON_REPO — the EXISTING verify-merged.sh /
#     done.sh offline hooks; set them and this reconciler is fully hermetic (see the .test.sh).
set -uo pipefail
FLEET="${RECONCILE_FLEET_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"   # scripts (done.sh/verify-merged.sh) — never overridden
BOARD="$FLEET/board"; STATE="$FLEET/state"; CLAIMS="$STATE/claims"

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//; /^set -uo/d'; exit 0 ;;
    *) echo "reconcile-stale-claims: unknown arg '$arg' (expected --apply)" >&2; exit 2 ;;
  esac
done

# pid_from_droid / alive — canonical form + semantics: reap-orphans.sh:82-90 (see header note).
pid_from_droid(){
  local pid="${1#*-}"
  [ "$pid" != "$1" ] || return 1
  case "$pid" in ''|*[!0-9]*) return 1;; esac
  echo "$pid"
}
alive(){ kill -0 "$1" 2>/dev/null; }

# canon: case-insensitive board+archive lookup (mirrors done.sh / reap-orphans.sh canon()).
canon(){ local w="$1" f b; for f in "$BOARD"/*.md "$BOARD"/archive/*.md; do
  [ -e "$f" ] || continue; b="$(basename "$f" .md)"
  [ "${b,,}" = "${w,,}" ] && { echo "$b"; return 0; }; done
  return 1; }

n_live=0; n_retired=0; n_held=0; n_skipped=0; n_would_retire=0; n_would_hold=0

if [ "$APPLY" -eq 1 ]; then echo "reconcile-stale-claims: APPLY mode (merged->retire via done.sh; unmerged->HOLD)"
else echo "reconcile-stale-claims: DRY-RUN (pass --apply to retire merged / flag held claims)"; fi
echo "reconcile-stale-claims: fleet=$FLEET claims_dir=$CLAIMS"
echo

if [ ! -d "$CLAIMS" ]; then echo "reconcile-stale-claims: no claims dir ($CLAIMS) — nothing to do."; exit 0; fi
shopt -s nullglob
files=( "$CLAIMS"/* )
shopt -u nullglob
[ "${#files[@]}" -gt 0 ] || { echo "reconcile-stale-claims: no claims present — nothing to do."; exit 0; }

for cf in "${files[@]}"; do
  [ -f "$cf" ] || continue
  id_raw="$(basename "$cf")"
  # Claim file is `<droid-id> <iso-ts>` (claim.sh printf). Read the first whitespace field.
  droid_id="$(awk '{print $1}' "$cf" 2>/dev/null)"
  pid="$(pid_from_droid "$droid_id" 2>/dev/null)" || {
    echo "SKIP    $id_raw  (claim owner '$droid_id' has no parseable PID — format drift, leaving as-is)"
    n_skipped=$((n_skipped+1)); continue
  }
  if alive "$pid"; then
    echo "LIVE    $id_raw  droid=$droid_id pid=$pid (ALIVE — left untouched)"
    n_live=$((n_live+1)); continue
  fi
  # DEAD PID. Resolve the canonical board id (case-insensitive). A claim for a ticket that no
  # longer has any board/archive file cannot be merge-proven -> HOLD it for the manager (never
  # a bare release: an unresolvable ticket is exactly when we know LEAST, so we touch nothing).
  if ! id="$(canon "$id_raw" 2>/dev/null)"; then
    echo "!! HOLD  $id_raw  droid=$droid_id pid=$pid (DEAD) — no board/archive ticket; cannot merge-prove -> HELD, NOT released" >&2
    n_held=$((n_held+1)); continue
  fi

  if [ "$APPLY" -eq 0 ]; then
    # DRY-RUN: read-only preview via the canonical proof. Never mutate.
    if bash "$SRC/verify-merged.sh" "$id" >/dev/null 2>&1; then
      echo "would RETIRE  $id  droid=$droid_id pid=$pid (DEAD, merge-proven) -> done.sh would write the terminal marker + drop the claim"
      n_would_retire=$((n_would_retire+1))
    else
      echo "would HOLD    $id  droid=$droid_id pid=$pid (DEAD, NOT merge-proven) -> claim KEPT (never released into a re-claimable void)"
      n_would_hold=$((n_would_hold+1))
    fi
    continue
  fi

  # APPLY. Drive the sanctioned writer. done.sh writes the marker + removes the claim IFF its own
  # merge-proof passes, and touches NOTHING on refusal. Read the outcome off the claim file itself
  # (robust to done.sh's best-effort scorecard/retire tail exit codes).
  proof_out="$(bash "$SRC/done.sh" "$id" 2>&1)"; drc=$?
  if [ ! -e "$cf" ]; then
    echo "RETIRED $id  droid=$droid_id pid=$pid — MERGED; terminal marker written, stale claim removed (done.sh)."
    n_retired=$((n_retired+1))
  else
    # HOLD — the red line. done.sh refused (work rejected / unpushed / unmerged). NEVER release.
    reason="$(printf '%s' "$proof_out" | grep -iE 'REFUSED|no MERGED PR|NOT an ancestor|cannot resolve' | head -1 | sed 's/^[[:space:]]*//')"
    [ -n "$reason" ] || reason="done.sh did not merge-prove $id (exit $drc)"
    echo "!!!!!! HOLD  $id  droid=$droid_id pid=$pid — UNMERGED work; claim HELD, NOT released." >&2
    echo "!!!!!! HOLD  $id  reason: $reason" >&2
    echo "!!!!!! HOLD  $id  rebuild+merge the ticket, or close it explicitly (done.sh $id --override \"<reason>\") before the pool re-offers it." >&2
    n_held=$((n_held+1))
  fi
done

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
[ "$n_skipped" -gt 0 ] && echo "  skipped (no PID): $n_skipped"
exit 0
