#!/usr/bin/env bash
# auto-park-scan.sh — after an honest-battery sweep, propose PARKED-MODELS.tsv
# entries for models whose runs were ALL provider/infra/local faults (a LEG
# problem), i.e. never once "ran-to-completion". A model that ran and graded
# BLOCK/FIXES is a QUALITY signal — kept in the scorecard, never parked here.
#
# Reads the newest per-ticket SUMMARY.md from the sweep (col3 = attribution).
# DRY-RUN by default (prints proposed rows); --apply appends to PARKED-MODELS.tsv.
set -u
cd "$(dirname "${BASH_SOURCE[0]}")/../.." || exit 3
RESULTS="fleet/state/dogfood-eval/results"
PARKED="fleet/state/PARKED-MODELS.tsv"
APPLY=0; [ "${1:-}" = "--apply" ] && APPLY=1
TODAY="$(date -u +%Y-%m-%d)"

# newest SUMMARY per honest-battery ticket
mapfile -t SUMMARIES < <(for t in SECRET-HOTROTATE PROVIDER-URL-HELPER RFL-3; do
  ls -t "$RESULTS/${t}"-*-SUMMARY.md 2>/dev/null | head -1
done)
[ ${#SUMMARIES[@]} -eq 0 ] && { echo "no SUMMARY files found under $RESULTS"; exit 0; }
echo "[auto-park] scanning: ${SUMMARIES[*]}"

# aggregate: per model, count total rows and ran-to-completion rows
declare -A TOTAL RANOK LASTATTR
for f in "${SUMMARIES[@]}"; do
  # table rows start with '| <model> |'; skip header/separator
  while IFS='|' read -r _ model _verdict attribution _rest; do
    model="$(echo "$model" | xargs)"; attribution="$(echo "$attribution" | xargs)"
    case "$model" in ""|model|:*|---*) continue ;; esac
    [ -z "$attribution" ] && continue
    TOTAL[$model]=$(( ${TOTAL[$model]:-0} + 1 ))
    LASTATTR[$model]="$attribution"
    case "$attribution" in ran-to-completion*) RANOK[$model]=$(( ${RANOK[$model]:-0} + 1 )) ;; esac
  done < "$f"
done

PROPOSED=0
{
  for model in "${!TOTAL[@]}"; do
    t=${TOTAL[$model]}; ok=${RANOK[$model]:-0}
    if [ "$ok" -eq 0 ] && [ "$t" -gt 0 ]; then
      reason="all $t honest-battery runs were leg/infra faults (never ran-to-completion; last=${LASTATTR[$model]}) — not model-quality, a provider-leg problem"
      cond="re-probe when the model's provider leg recovers (1-token probe returns 200+content), then re-run one honest-battery ticket clean"
      printf '%s\t%s\t%s\t%s\t%s\n' "$model" "leg-fault" "$TODAY" "$reason" "$cond"
      PROPOSED=$((PROPOSED+1))
    else
      echo "[auto-park] KEEP $model — $ok/$t ran-to-completion (healthy; quality signal retained)" >&2
    fi
  done
} > /tmp/auto-park-proposed.$$
echo "[auto-park] proposed park rows ($PROPOSED):"
cat /tmp/auto-park-proposed.$$
if [ "$PROPOSED" -gt 0 ] && [ "$APPLY" -eq 1 ]; then
  # skip any model already parked
  while IFS=$'\t' read -r m rest; do
    grep -qP "^${m}\t" "$PARKED" 2>/dev/null && { echo "[auto-park] already parked: $m"; continue; }
    printf '%s\t%s\n' "$m" "$rest" >> "$PARKED"
    echo "[auto-park] PARKED: $m"
  done < /tmp/auto-park-proposed.$$
fi
rm -f /tmp/auto-park-proposed.$$
