#!/usr/bin/env bash
# wci-contention.sh — WCI high-contention-file DETECTOR (build-rig only).
# Turns the collision metric into a REFACTOR TRIGGER: scans every board ticket's
# `owns:` field, counts how many tickets own each file, and flags any file owned by
# >= N tickets as a DECOMPOSE CANDIDATE (a god-file = refactoring debt — split it so
# tickets re-slice onto disjoint modules and parallelize by construction).
# See fleet/WCI-METHOD.md (Step 2/3).
#
# Two modes:
#   (default)  ADVISORY god-file detector. N defaults to 4. Scans live AND parked
#              tickets. Prints hits, never mutates anything, ALWAYS exits 0.
#   --strict   HARD PRE-CHECK (DEC-VALIDATE-STRICT). N defaults to 2. Scans only
#              LIVE tickets (parked are not schedulable, so they cannot collide).
#              Any file owned by >= N live tickets is a concurrency COLLISION: print
#              the collisions + exit NON-ZERO. Complements the engine's
#              intake.assert_disjoint_waves as a rig-side pre-flight.
#
# Usage: wci-contention.sh [--strict] [N]   # N = ownership threshold
# Exit:  default -> always 0 (advisory).  --strict -> non-zero if any collision.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BOARD="$HERE/board"

# --- arg parse: --strict flag (anywhere) + optional positional N -------------
STRICT=0
POS=()
for a in "$@"; do
  case "$a" in
    --strict) STRICT=1 ;;
    *) POS+=("$a") ;;
  esac
done
if [ "$STRICT" -eq 1 ]; then
  N="${POS[0]:-2}"
else
  N="${POS[0]:-4}"
fi

case "$N" in ''|*[!0-9]*) echo "wci-contention: N must be a positive integer (got '$N')" >&2; exit 0;; esac
[ "$N" -ge 1 ] || { echo "wci-contention: N must be >= 1" >&2; exit 0; }
[ -d "$BOARD" ] || { echo "wci-contention: no board dir at $BOARD"; exit 0; }

# owners.tsv: one "<file>\t<ticket>" row per (file, owning-ticket) pair.
# In --strict mode only LIVE tickets (*.md) are considered — parked tickets
# (*.md.parked) are not schedulable, so they cannot create a real collision.
owners="$(
  shopt -s nullglob
  globs=("$BOARD"/*.md)
  [ "$STRICT" -eq 1 ] || globs+=("$BOARD"/*.md.parked)
  for tk in "${globs[@]}"; do
    [ -f "$tk" ] || continue
    base="$(basename "$tk")"
    ticket="${base%.md}"; ticket="${ticket%.md.parked}"
    # Grab the value on the FIRST `owns:` line; robust to missing/empty/extra spaces.
    line="$(grep -m1 -E '^[[:space:]]*owns:' "$tk" 2>/dev/null || true)"
    val="${line#*:}"
    # split on commas
    IFS=',' read -ra parts <<< "$val"
    for p in "${parts[@]:-}"; do
      # trim leading/trailing whitespace
      f="$(printf '%s' "$p" | sed -E 's/^[[:space:]]+//; s/[[:space:]]+$//')"
      [ -n "$f" ] || continue
      printf '%s\t%s\n' "$f" "$ticket"
    done
  done
)"

if [ -z "$owners" ]; then
  echo "wci-contention: no owned files found across board tickets."
  exit 0
fi

# Aggregate: for each file, count distinct owning tickets + collect the list.
hits="$(
  printf '%s\n' "$owners" | sort -u | awk -F'\t' -v N="$N" '
    { cnt[$1]++; if (list[$1]=="") list[$1]=$2; else list[$1]=list[$1] ", " $2 }
    END {
      for (f in cnt) if (cnt[f] >= N) printf "%d\t%s\t%s\n", cnt[f], f, list[f]
    }
  ' | sort -rn -k1,1
)"

if [ -z "$hits" ]; then
  if [ "$STRICT" -eq 1 ]; then
    echo "wci-contention --strict: OK — no file owned by >= $N live ticket(s)."
  else
    echo "wci-contention: no DECOMPOSE CANDIDATE — no file owned by >= $N ticket(s)."
  fi
  exit 0
fi

if [ "$STRICT" -eq 1 ]; then
  echo "wci-contention --strict: COLLISION — files owned by >= $N LIVE ticket(s):"
  while IFS=$'\t' read -r count file list; do
    [ -n "$file" ] || continue
    echo "  COLLISION: $file — owned by $count live tickets"
    echo "      owners: $list"
  done <<< "$hits"
  echo "  -> two live tickets sharing a file will collide when run concurrently; make owns"
  echo "     DISJOINT (or add a real build-dep to sequence them) before launching the wave."
  exit 1
fi

echo "WCI CONTENTION — files owned by >= $N ticket(s) (DECOMPOSE CANDIDATES):"
while IFS=$'\t' read -r count file list; do
  [ -n "$file" ] || continue
  echo "  DECOMPOSE CANDIDATE: $file — owned by $count tickets"
  echo "      owners: $list"
done <<< "$hits"
echo "  -> a file owned by >= $N tickets is refactoring debt; split along seams so tickets re-slice"
echo "     onto DISJOINT modules and parallelize (fleet/WCI-METHOD.md Step 3)."
exit 0
