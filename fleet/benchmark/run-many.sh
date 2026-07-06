#!/usr/bin/env bash
# run-many.sh <model1> <model2> ... [-- --sections S0,S2,S6]
#
# STILL USEFUL, kept (not superseded): this is the one thing bench.sh does
# NOT do - bulk-provisioning fixture worktrees for a whole ROSTER of models
# in one invocation, e.g. so several opencode tabs can each be pointed at
# their own model's pre-copied worktrees before anyone starts driving them.
# For the single-model interactive flow (announce -> all 7 sections ->
# auto-record -> tier chart, one paste, no per-section shuttling), use
# bench.sh instead - see its header and README.md. Once worktrees are
# prepared here, either bench.sh or run.sh can grade/advance them (shared
# state via lib/grade_state.py + lib/sections.sh).
#
# Thin wrapper: loops run.sh's PREPARE mode over a list of models so an
# operator can kick off a whole roster in one invocation instead of one
# session per model. Each model still goes through the same manual
# model-driving + `run.sh --grade <section> <model>` seam per section - this
# script does not itself drive models, it just avoids re-invoking run.sh by
# hand for every model in the roster and prints one combined summary read
# from model-scorecard.tsv at the end.
#
# Usage:
#   run-many.sh glm-5.2 deepseek-v4-pro
#   run-many.sh glm-5.2 deepseek-v4-pro -- --sections S0,S2,S6
#   run-many.sh --models-file models.txt
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
SCORECARD="$FLEET_DIR/model-scorecard.sh"

die() { echo "error: $*" >&2; exit 1; }

MODELS=()
EXTRA_ARGS=()

if [ "${1:-}" = "--models-file" ]; then
  [ -n "${2:-}" ] || die "usage: run-many.sh --models-file <path>"
  while IFS= read -r line; do
    [ -n "$line" ] && MODELS+=("$line")
  done < "$2"
  shift 2
else
  while [ $# -gt 0 ] && [ "$1" != "--" ]; do
    MODELS+=("$1")
    shift
  done
  if [ "${1:-}" = "--" ]; then
    shift
    EXTRA_ARGS=("$@")
  fi
fi

[ "${#MODELS[@]}" -gt 0 ] || die "usage: run-many.sh <model1> <model2> ... [-- --sections S0,S2,S6]  |  run-many.sh --models-file <path>"

echo "run-many: preparing ${#MODELS[@]} model(s): ${MODELS[*]}"
for model in "${MODELS[@]}"; do
  echo
  echo "############################################################"
  echo "# MODEL: $model"
  echo "############################################################"
  "$HERE/run.sh" "$model" "${EXTRA_ARGS[@]}"
done

echo
echo "############################################################"
echo "# All models prepared. Drive each worktree, then grade with:"
echo "#   run.sh --grade <section> <model>"
echo "# per (model, section) as usual - each grade auto-appends its row."
echo "# Once every model/section pair for this roster has been graded,"
echo "# the combined summary below (read live from model-scorecard.tsv)"
echo "# will include every row appended so far for this roster."
echo "############################################################"
echo

python3 - "$SCORECARD" "${MODELS[@]}" <<'PYEOF'
import subprocess
import sys
from pathlib import Path

scorecard_sh = sys.argv[1]
models = set(sys.argv[2:])
tsv = Path(scorecard_sh).parent / "model-scorecard.tsv"

rows = []
if tsv.exists():
    for line in tsv.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if len(cols) < 13:
            continue
        if cols[1] == "bench" and cols[5] in models:
            rows.append(cols)

if not rows:
    print("(no bench rows appended yet for this roster - grade at least one section first)")
    sys.exit(0)

print(f"{'model':18} {'ref':4} {'work_class':16} {'tier':4} {'score':5} {'verdict':7} {'time_s':7} {'corr':4}  note")
for cols in sorted(rows, key=lambda c: (c[5], c[2])):
    _date, _src, ref, wclass, tier, model, verdict, _gate, score, time_s, _cost, corr, note = cols[:13]
    print(f"{model:18} {ref:4} {wclass:16} {tier:4} {score:5} {verdict:7} {time_s:7} {corr:4}  {note}")
PYEOF
