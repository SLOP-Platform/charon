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
# FORMATS — this script reads BOTH claim formats (CLAIM-RECONCILE-INERT accept-2):
#   • Old format: `<droid-id> <iso-ts>` (claim.sh line-1 printf). Liveness = PID.
#   • Bridge format: multi-line key=value (session-bridge MCP). Liveness = `heartbeat:` field.
#   The claim_field() helper transparently reads either, adopting the same dual-format strategy
#   as work-lease.sh:claim_epoch() (work-lease.sh:126-130).
#
# ADOPT-FIRST (no second merge-check, no second PID-check):
#   • DEAD/ALIVE — `<tier>-<pid>` parse + `kill -0` for old format (reap-orphans.sh:82-90
#     semantics); `heartbeat:` field + threshold for bridge format. Liveness notions are
#     adopted from their respective sources — this script creates no third liveness signal.
#   • MERGE-PROOF — done.sh is THE sanctioned marker writer: its merge-proof (merged_pr_for_branch /
#     merged_pr_touching_owns, done.sh:35-68/132-148) writes the terminal marker AND removes the
#     claim ONLY when the merge is proven, and fail-closes (exit 3, NOTHING touched) otherwise.
#     We DRIVE `done.sh <id>` and read the OUTCOME off the claim file — the authoritative retire.
#   • PREVIEW — dry-run uses the canonical read-only proof `verify-merged.sh <id>` (a thin CLI over
#     _lib.sh:verify_merged, the ONE source of truth), so a preview never mutates anything.
#
# WORKTREE GUARDS (CLAIM-RECONCILE-INERT accept-3):
#   A claim whose worktree has uncommitted changes or unpushed commits is NEVER released — the
#   same invariants as branch-reaper.sh's _rp_keep_reason / _lg_wt_target_ok. A claim file that
#   already has a terminal done-marker (state/done/<id>) AND whose branch is landed in master
#   is released DIRECTLY (no done.sh re-invocation).
#
# Usage:  fleet/reconcile-stale-claims.sh [--apply]
#   default = DRY-RUN (classify every claim, PREVIEW merged/held via verify-merged.sh; no writes).
#   --apply = for each DEAD claim: merged -> retire; unmerged -> HOLD.
# LIVE claims are NEVER touched (same invariant as reap-orphans.sh).
#
# Env (test seams, all honoured by the tools we drive — we add NO new seam):
#   RECONCILE_FLEET_DIR   override the fleet DATA dir (board/state) for test isolation.
#   RECONCILE_STALE_S     staleness threshold for heartbeat-based liveness (default 900).
#   VERIFY_MERGED_FIXTURE / DONE_MERGED_SRC / DONE_CHARON_REPO — the EXISTING verify-merged.sh /
#     done.sh offline hooks; set them and this reconciler is fully hermetic (see the .test.sh).
set -uo pipefail
FLEET="${RECONCILE_FLEET_DIR:-$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)}"
SRC="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$FLEET/board"; STATE="$FLEET/state"; CLAIMS="$STATE/claims"
STALE_S="${RECONCILE_STALE_S:-900}"

APPLY=0
for arg in "$@"; do
  case "$arg" in
    --apply) APPLY=1 ;;
    -h|--help) sed -n '2,/^set -uo/p' "$0" | sed 's/^# \?//; /^set -uo/d'; exit 0 ;;
    *) echo "reconcile-stale-claims: unknown arg '$arg' (expected --apply)" >&2; exit 2 ;;
  esac
done

# pid_from_droid / alive — old-format PID liveness (reap-orphans.sh:82-90).
pid_from_droid(){
  local pid="${1#*-}"
  [ "$pid" != "$1" ] || return 1
  case "$pid" in ''|*[!0-9]*) return 1;; esac
  echo "$pid"
}
alive(){ kill -0 "$1" 2>/dev/null; }

# claim_field <field> <file> -> value. Reads BOTH formats transparently.
# Bridge format: grep for "^field: *value". Old format: fallback for known fields.
claim_field(){
  local f="$1" cf="$2" val
  val="$(grep -m1 "^${f}:" "$cf" 2>/dev/null | sed "s/^${f}: *//")" && [ -n "$val" ] || val=""
  if [ -z "$val" ]; then
    case "$f" in
      heartbeat) val="$(awk 'NR==1{print $2; exit}' "$cf" 2>/dev/null)" || val="" ;;
      ticket)   val="$(basename "$cf")" ;;
    esac
  fi
  [ -n "$val" ] && printf '%s' "$val"
}

# is_bridge_format <file> — true if first line starts "ticket:".
is_bridge_format(){ head -1 "$1" 2>/dev/null | grep -q "^ticket:"; }

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

n_live=0; n_retired=0; n_held=0; n_skipped=0; n_would_retire=0; n_would_hold=0

if [ "$APPLY" -eq 1 ]; then echo "reconcile-stale-claims: APPLY mode (merged->retire via done.sh; unmerged->HOLD)"
else echo "reconcile-stale-claims: DRY-RUN (pass --apply to retire merged / flag held claims)"; fi
echo "reconcile-stale-claims: fleet=$FLEET claims_dir=$CLAIMS stale_threshold=${STALE_S}s"
echo

if [ ! -d "$CLAIMS" ]; then echo "reconcile-stale-claims: no claims dir ($CLAIMS) — nothing to do."; exit 0; fi
shopt -s nullglob
files=( "$CLAIMS"/* )
shopt -u nullglob
[ "${#files[@]}" -gt 0 ] || { echo "reconcile-stale-claims: no claims present — nothing to do."; exit 0; }

for cf in "${files[@]}"; do
  [ -f "$cf" ] || continue
  id_raw="$(basename "$cf")"
  id_display="$id_raw"

  # ── liveness check (format-aware) ──────────────────────────────────────
  if is_bridge_format "$cf"; then
    # Bridge format: liveness = heartbeat within threshold.
    hb="$(claim_field heartbeat "$cf")"
    if [ -n "$hb" ] && [ "$hb" -eq "$hb" ] 2>/dev/null; then
      now="$(date +%s)"
      age=$((now - hb))
      if [ "$age" -lt "$STALE_S" ]; then
        echo "LIVE    $id_raw  heartbeat=${age}s ago (within ${STALE_S}s threshold)"
        n_live=$((n_live+1)); continue
      fi
      echo "STALE   $id_raw  heartbeat=${age}s ago (exceeds ${STALE_S}s threshold)"
    fi
    droid_id="$(claim_field session "$cf")"
    [ -z "$droid_id" ] && droid_id="bridge"
    wt="$(claim_field worktree "$cf")"
  else
    # Old format: PID-based liveness.
    droid_id="$(awk '{print $1}' "$cf" 2>/dev/null)"
    pid="$(pid_from_droid "$droid_id" 2>/dev/null)" || {
      echo "SKIP    $id_raw  (claim owner '$droid_id' has no parseable PID — format drift, leaving as-is)"
      n_skipped=$((n_skipped+1)); continue
    }
    if alive "$pid"; then
      echo "LIVE    $id_raw  droid=$droid_id pid=$pid (ALIVE — left untouched)"
      n_live=$((n_live+1)); continue
    fi
    wt=""
  fi

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
