#!/usr/bin/env bash
# log-prune.sh — FLEET LOG ROTATION/PRUNE (build-rig hygiene, gap-register B3).
#
# Gap-register B3 / QUICKWINS-LEVERAGE #7: ~3.4M / ~59+ unrotated fleet logs accrete
# forever (state/overnight/*.log, state/dogfood-eval/results/*.log, state/wave1-logs,
# state/agent-logs, state/droid-logs, state/preflight-results, *.log under state/).
# Every board op / validate_board run re-reads that cruft. This script rotates and
# prunes them by age + size, idempotently, safe to run from preflight or a schedule.
#
# Two HARD-SCOPE guards (the delete blast radius mandates both):
#   1. SUFFIX-LOCKED: ONLY files matching `*.log` (or `*.log.<n>` rotations) are ever
#      touched. A non-log file in the same dir is NEVER deleted/gzipped — the self-test
#      asserts a sibling `keep.me` survives `--apply` (GREEN-IS-NOT-PROOF guard against
#      an over-broad `rm`).
#   2. PATH-LOCKED: candidate files MUST live under one of the explicit --dir roots
#      (default: the known fleet logdirs). board/, state/claims, state/needs-push,
#      state/done, state/submitted, and state/ markers are NEVER in the default root
#      set and the script REFUSES a root that resolves to board/ or state/ itself.
#      Only `*.log` files *under* a root are candidates — never the root dir wholesale.
#
# WHAT IT DOES (in order, each idempotent):
#   (1) AGE-PRUNE: delete `*.log` files older than --days (mtime +N). This is the
#       core guard — the self-test reverts the `-mtime +N` filter and asserts a FRESH
#       log is then wrongly pruned (RED), which a no-op or an over-broad `rm` would
#       also trigger / fail to catch respectively.
#   (2) SIZE-ROTATE: gzip `*.log` files larger than --size-bytes, bumping any prior
#       `*.log.1`/`.log.2` rotation up before rotating (drops the oldest). Caps the
#       total number of rotations per file at --rotations.
#   (3) For convenience, `*.log.<n>` (the rotated suffixes this script produces) are
#       also age-pruned under the same --days rule.
#
# Usage: fleet/log-prune.sh [options]
#   --apply            actually prune/rotate (default: DRY-RUN, print only)
#   --days N           age threshold in days for prune        (default 14)
#   --size-bytes B     rotate logs larger than B bytes         (default 10485760 = 10MiB)
#   --rotations N      keep at most N gzipped rotations/log    (default 3)
#   --dir DIR          add a target log dir (repeatable). Default roots:
#                        fleet/state/overnight
#                        fleet/state/dogfood-eval/results
#                        fleet/state/dogfood-eval/run-logs
#                        fleet/state/preflight-results
#                        fleet/state/wave1-logs
#                        fleet/state/droid-logs
#                        fleet/state/agent-logs
#   -h|--help          print this header
#
# Env:
#   LP_FLEET_DIR   fleet dir (default: this script's dir) — root for the default --dir set.
#   LP_DAYS, LP_SIZE_BYTES, LP_ROTATIONS  override the matching defaults (test hooks).
#
# TEST HOOK: set LP_FLEET_DIR (and --dir) to point at an isolated temp fixture.
# See fleet/tests/log-prune.test.sh (FAIL-ON-REVERT: stale gone, fresh KEPT; revert
# the -mtime filter -> the fresh log is wrongly pruned, test RED. GREEN-IS-NOT-PROOF:
# the self-test asserts the stale file was removed AND a fresh/non-log file survived).
set -uo pipefail
FLEET="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
LP_FLEET_DIR="${LP_FLEET_DIR:-$FLEET}"
DAYS="${LP_DAYS:-14}"
SIZE_BYTES="${LP_SIZE_BYTES:-10485760}"
ROTATIONS="${LP_ROTATIONS:-3}"
APPLY=0
DIRS=()

print_help() { sed -n '2,/^$/p' "$0" | sed 's/^# \?//'; }

add_default_dirs() {
  local d
  for d in \
    "$LP_FLEET_DIR/state/overnight" \
    "$LP_FLEET_DIR/state/dogfood-eval/results" \
    "$LP_FLEET_DIR/state/dogfood-eval/run-logs" \
    "$LP_FLEET_DIR/state/preflight-results" \
    "$LP_FLEET_DIR/state/wave1-logs" \
    "$LP_FLEET_DIR/state/droid-logs" \
    "$LP_FLEET_DIR/state/agent-logs"
  do
    [ -d "$d" ] && DIRS+=("$d")
  done
}

# Harden a --dir argument into an absolute, normalized, villain-proof path.
# Echoes the resolved dir on success; returns 1 if the path escapes the fleet root
# or resolves to board/ / state/ wholesale (the protected trees).
harden_dir() {
  local raw="$1" abs base
  case "$raw" in
    /*) abs="$raw" ;;
    *)  abs="$(pwd)/$raw" ;;
  esac
  # Collapse `.` / `..` lexically (does not follow symlinks; we only peer at the path text).
  abs="$(printf '%s' "$abs/" | sed -e 's#/\./#/#g' -e 's#/\{2,\}#/#g' -e ':l' -e 's#/[^/]*/\.\./#/#' -e 't l' -e 's#/$##')"
  # Resolve symlinks on the parent so a board/-pointing symlink can't sneak in.
  case "$abs" in
    "$LP_FLEET_DIR"/*) : ;;                # must live under the fleet root
    "$LP_FLEET_DIR")   : ;;                 # or be the fleet root itself (rejected below)
    *) echo "log-prune: refusing dir outside fleet root: $raw" >&2; return 1 ;;
  esac
  case "$abs" in
    "$LP_FLEET_DIR/board")
      echo "log-prune: refusing protected tree as target: board/" >&2; return 1 ;;
    "$LP_FLEET_DIR/state")
      echo "log-prune: refusing protected tree as target: state/" >&2; return 1 ;;
  esac
  # Reject any direct child of the fleet root that is state/ claims/ marks/ etc.:
  # the root set is leaf logdirs, not the state/ tree wholesale.
  base="${abs##*/}"
  if [ "$abs" = "$LP_FLEET_DIR/state" ] || [ "$abs" = "$LP_FLEET_DIR/board" ]; then
    echo "log-prune: refusing protected tree wholesale: $abs" >&2; return 1
  fi
  printf '%s' "$abs"
}

FORCE_DEFAULT=0
while [ $# -gt 0 ]; do
  case "$1" in
    --apply) APPLY=1 ;;
    --days) DAYS="${2:?--days needs a value}"; shift ;;
    --size-bytes) SIZE_BYTES="${2:?--size-bytes needs a value}"; shift ;;
    --rotations) ROTATIONS="${2:?--rotations needs a value}"; shift ;;
    --dir)  d="$(harden_dir "${2:?--dir needs a value}")" || exit 2; DIRS+=("$d"); FORCE_DEFAULT=1; shift ;;
    --help|-h) print_help; exit 0 ;;
    *) echo "log-prune: unknown argument '$1' (see --help)" >&2; exit 2 ;;
  esac
  shift
done

# Validate numeric args (a non-numeric DAYS/SIZE_BYTES silently breaks `find -mtime`).
case "$DAYS" in ''|*[!0-9]*) echo "log-prune: --days must be a non-negative integer (got '$DAYS')" >&2; exit 2 ;; esac
case "$SIZE_BYTES" in ''|*[!0-9]*) echo "log-prune: --size-bytes must be a non-negative integer (got '$SIZE_BYTES')" >&2; exit 2 ;; esac
case "$ROTATIONS" in ''|*[!0-9]*) echo "log-prune: --rotations must be a non-negative integer (got '$ROTATIONS')" >&2; exit 2 ;; esac

# If the caller gave no explicit --dir, use the default root set.
[ "$FORCE_DEFAULT" -eq 0 ] && add_default_dirs

if [ "${#DIRS[@]}" -eq 0 ]; then
  echo "log-prune: no target log dirs (set LP_FLEET_DIR or pass --dir)" >&2
  exit 1
fi

if [ "$APPLY" -eq 1 ]; then
  echo "log-prune: APPLY mode (prune + rotate will occur)"
else
  echo "log-prune: DRY-RUN (pass --apply to actually prune/rotate)"
fi
echo "log-prune: days=$DAYS size-bytes=$SIZE_BYTES rotations=$ROTATIONS"
echo "log-prune: dirs (${#DIRS[@]}):"
for d in "${DIRS[@]}"; do echo "  - $d"; done
echo

pruned_count=0
pruned_bytes=0
rotated_count=0
rotated_bytes=0

# (1) AGE-PRUNE — delete *.log and our own *.log.<n> rotations older than --days.
#     The `-mtime +N` filter IS the guard the self-test reverts. Only files whose
#     name ends in `.log` or `.log.<digits>` are candidates — never a non-log sibling.
age_prune_dir() {
  local dir="$1" f sz
  # shellcheck disable=SC2044
  for f in $(find "$dir" -maxdepth 1 -type f \( -name '*.log' -o -name '*.log.[0-9]' -o -name '*.log.[0-9][0-9]' \) -mtime +"$DAYS" -print 2>/dev/null); do
    [ -f "$f" ] || continue
    sz=$(stat -c '%s' "$f" 2>/dev/null || stat -f '%z' "$f" 2>/dev/null || echo 0)
    echo "  PRUNE  $f  (${sz}B, age>$DAYS day)"
    if [ "$APPLY" -eq 1 ]; then
      rm -f -- "$f"
    fi
    pruned_count=$((pruned_count+1))
    pruned_bytes=$((pruned_bytes+sz))
  done
}

# (2) SIZE-ROTATE — gzip large live *.log files, bumping prior rotations.
# Keeps at most $ROTATIONS gzipped copies per file; the oldest is dropped at bump.
rotate_dir() {
  local dir="$1" f sz base i prev
  # shellcheck disable=SC2044
  for f in $(find "$dir" -maxdepth 1 -type f -name '*.log' -size +"${SIZE_BYTES}c" -print 2>/dev/null); do
    [ -f "$f" ] || continue
    sz=$(stat -c '%s' "$f" 2>/dev/null || stat -f '%z' "$f" 2>/dev/null || echo 0)
    echo "  ROTATE $f  (${sz}B > ${SIZE_BYTES}B)"
    if [ "$APPLY" -eq 1 ]; then
      # Bump .log.<N-1> -> .log.<N> from high to low, dropping the slot above $ROTATIONS.
      base="${f%.log}"
      i=$ROTATIONS
      while [ "$i" -ge 1 ]; do
        prev=$((i-1))
        if [ "$i" -eq "$ROTATIONS" ]; then
          rm -f -- "${base}.log.$i" "${base}.log.$i.gz"
        fi
        if [ "$i" -eq 1 ]; then
          if [ -f "$f" ]; then mv -- "$f" "${base}.log.1"; fi
        else
          if [ -e "${base}.log.${prev}" ];  then mv -- "${base}.log.${prev}"  "${base}.log.$i"; fi
          if [ -e "${base}.log.${prev}.gz" ]; then mv -- "${base}.log.${prev}.gz" "${base}.log.$i.gz"; fi
        fi
        i=$((i-1))
      done
      gzip -f -- "${base}.log.1" 2>/dev/null || true
    fi
    rotated_count=$((rotated_count+1))
    rotated_bytes=$((rotated_bytes+sz))
  done
}

echo "== age-prune (*.log older than $DAYS day) =="
for d in "${DIRS[@]}"; do [ -d "$d" ] && age_prune_dir "$d"; done
echo "  pruned: $pruned_count file(s), $pruned_bytes byte(s)"
echo

echo "== size-rotate (*.log larger than $SIZE_BYTES byte, keep $ROTATIONS rotation(s)) =="
for d in "${DIRS[@]}"; do [ -d "$d" ] && rotate_dir "$d"; done
echo "  rotated: $rotated_count file(s), $rotated_bytes byte(s)"
echo

total_bytes=$((pruned_bytes + rotated_bytes))
echo "log-prune: done ($([ "$APPLY" = 1 ] && echo 'applied' || echo 'dry-run') — $pruned_count pruned ($pruned_bytes B), $rotated_count rotated ($rotated_bytes B); $total_bytes B total reclaimed)."
exit 0
