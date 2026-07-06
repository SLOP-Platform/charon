#!/usr/bin/env bash
# run.sh — fleet model-benchmark runner (build-rig only; see MODEL-BENCHMARK-SPEC.md
# and TICKET-BENCHMARK-HARNESS.md).
#
# SUPERSEDED for the interactive one-model flow by bench.sh: `run.sh <model>`
# requires the operator to type the model name and then manually shuttle
# each `--grade <section> <model>` call themselves. bench.sh instead
# auto-detects the model (no typing it) and auto-advances through all 7
# sections with a single `bench.sh grade` invocation per section, ending in
# a tier chart with intra-tier rank - see bench.sh's header and README.md.
# This file is kept because (a) it still works standalone for scripted/
# unattended prepare+grade sequences, and (b) run-many.sh depends on its
# PREPARE mode to bulk-provision fixture worktrees for several models at
# once. It shares on-disk state with bench.sh (lib/grade_state.py,
# lib/sections.sh, runs/<model>/<section>/) - a worktree prepared by either
# script can be graded by the other. Two modes:
#
#   run.sh <model> [--sections S0,S2,S6]
#       PREPARE mode. For each section (default: all S0-S6): copies the
#       section's fixture into a fresh isolated worktree, starts this
#       section's clock (for auto time_s), prints the task PROMPT + the
#       worktree's absolute path + its time-box. Hand the prompt + worktree
#       path to the model (today: paste into an opencode tab pointed at that
#       worktree - the manual model-driving seam; a future headless driver
#       can slot in here without reworking the graders).
#
#   run.sh --grade <section> <model>
#       GRADE mode. Runs that section's deterministic grader against
#       whatever is currently in the prepared worktree, and auto-appends the
#       `bench` row to model-scorecard.tsv via model-scorecard.sh append -
#       grading and ledger-append are NEVER separate manual steps. If the
#       grade fails (gate=fail) and the correction cap (3, see
#       MODEL-BENCHMARK-SPEC.md §5a) hasn't been hit yet, nothing is
#       appended - fix the worktree and re-run `--grade` again; the runner
#       counts that as one correction round automatically. Once the model
#       passes, or the cap is hit, the row is appended (capped below the
#       top/MERGE band if the cap was hit while still failing).
#
# Time-boxing: each section's clock starts at `init` (prepare) time. A
# `--grade` call after the section's time-box has elapsed is scored 0 with
# note="timeout" - a hung/unresponsive model never hangs the run.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$HERE"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
SCORECARD="$FLEET_DIR/model-scorecard.sh"
STATE_PY="$HERE/lib/grade_state.py"
TODAY="$(date +%F)"

# shellcheck source=lib/sections.sh
source "$HERE/lib/sections.sh"   # ALL_SECTIONS, section_*(), verdict_from_score(), die() - shared with bench.sh

prepare_section() {
  local section="$1" model="$2"
  local timebox; timebox="$(section_timebox_sec "$section")"
  local worktree; worktree="$(python3 "$STATE_PY" init "$model" "$section" "$timebox")"
  local fixture; fixture="$(section_fixture "$section")"

  rm -rf "$worktree"
  mkdir -p "$worktree"
  # copy the fixture, never node_modules/dist/pycache - the model/grader
  # (re)installs/builds fresh so the worktree reflects only real edits.
  ( cd "$fixture" && tar cf - --exclude node_modules --exclude dist --exclude __pycache__ --exclude .pytest_cache . ) \
    | ( cd "$worktree" && tar xf - )

  echo "=================================================================="
  echo "SECTION $section  (model=$model, work_class=$(section_work_class "$section"), tier=$(section_tier "$section" 2>/dev/null || echo '-'), time-box=${timebox}s)"
  echo "------------------------------------------------------------------"
  cat "$HERE/prompts/$(echo "$section" | tr 'A-Z' 'a-z').txt"
  echo "------------------------------------------------------------------"
  echo "WORKTREE: $worktree"
  echo "Drive the model against this worktree now (e.g. paste the prompt"
  echo "above into an opencode tab pointed at that path). When the model's"
  echo "attempt is ready, grade it with:"
  echo ""
  echo "    $HERE/run.sh --grade $section $model"
  echo ""
  echo "(re-run the same command again after another attempt if it fails -"
  echo "up to ${timebox}s and 3 correction rounds are auto-tracked; a"
  echo "'run-many.sh' full run advances automatically once the row lands)"
  echo "=================================================================="
}

grade_section() {
  local section="$1" model="$2"
  # $STATE_PY always prints an absolute path (grade_state.py resolves RUNS via
  # Path(__file__).resolve()) - graders (S3's actionlint call in particular)
  # double-prefix a relative --worktree against their own cwd=<worktree>, so
  # this MUST stay absolute. common.parse_args() also .resolve()s defensively.
  local worktree; worktree="$(python3 "$STATE_PY" path "$model" "$section")" || die "no prepared worktree for $model/$section - run: $HERE/run.sh $model --sections $section"
  local fixture; fixture="$(section_fixture "$section")"
  local grader; grader="$(section_grader "$section")"

  local grader_out
  grader_out="$($grader --worktree "$worktree" --baseline "$fixture")" || die "grader crashed: $grader_out"
  local score gate reason
  score="$(echo "$grader_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["score"])')"
  gate="$(echo "$grader_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["gate"])')"
  reason="$(echo "$grader_out" | python3 -c 'import json,sys; print(json.load(sys.stdin)["reason"])' | tr '\t' ' ')"

  local record
  record="$(python3 "$STATE_PY" record "$model" "$section" "$score" "$gate")"
  local finalize corrections final_score time_s timed_out
  finalize="$(echo "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["finalize"])')"
  corrections="$(echo "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["corrections"])')"
  final_score="$(echo "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["final_score"])')"
  time_s="$(echo "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["time_s"])')"
  timed_out="$(echo "$record" | python3 -c 'import json,sys; print(json.load(sys.stdin)["timed_out"])')"

  if [ "$finalize" != "True" ]; then
    echo "SECTION $section / $model: round $corrections/3 FAILED (score=$score, gate=$gate) - $reason"
    echo "Fix in $worktree and re-run: $HERE/run.sh --grade $section $model"
    return 0
  fi

  local note="$reason"
  if [ "$timed_out" = "True" ]; then note="timeout ($note)"; fi
  local verdict; verdict="$(verdict_from_score "$final_score")"
  local wclass; wclass="$(section_work_class "$section")"
  local tier
  if [ "$section" = "S6" ]; then
    if [ "$final_score" -ge 90 ]; then tier=3; else tier=2; fi
  else
    tier="$(section_tier "$section")"
  fi
  local cost_usd="-"   # best-effort only; populated when a gateway-attributed driving flow can attach it (SR-5b) - never estimated

  bash "$SCORECARD" append "$TODAY" bench "$section" "$wclass" "$tier" "$model" "$verdict" "$gate" "$final_score" "$time_s" "$cost_usd" "$corrections" "$note"
  echo "SECTION $section / $model: FINAL score=$final_score verdict=$verdict time_s=$time_s corrections=$corrections -> appended to model-scorecard.tsv"
}

main() {
  if [ "${1:-}" = "--grade" ]; then
    local section="$2" model="$3"
    grade_section "$section" "$model"
    return 0
  fi

  local model="${1:-}"
  [ -n "$model" ] || die "usage: run.sh <model> [--sections S0,S2,S6]  |  run.sh --grade <section> <model>"
  shift || true

  local sections=("${ALL_SECTIONS[@]}")
  if [ "${1:-}" = "--sections" ]; then
    IFS=',' read -r -a sections <<< "$2"
  fi

  for s in "${sections[@]}"; do
    prepare_section "$s" "$model"
  done
}

main "$@"
