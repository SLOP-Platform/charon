#!/usr/bin/env bash
# bench.sh — single in-session, one-paste model-benchmark driver.
#
# TARGET UX: the operator selects a model in opencode with `/model`, then
# pastes ONE prompt into that SAME session telling the agent (i.e. itself,
# running AS the selected model) to drive this script. From there everything
# is automatic: the model is auto-detected + announced, all 7 sections
# (S0-S6) run one after another with no per-section shuttling by the
# operator, each section auto-grades + auto-appends to model-scorecard.tsv,
# and the final turn prints a tier chart with intra-tier rank. See
# README.md for the exact one-liner the operator pastes.
#
# Subcommands (agent-facing - this is what the pasted prompt tells the agent
# to run in a loop; no section/model args needed for the common path):
#
#   bench.sh start [--model <id>]
#       Detect (or accept an explicit override for) the current model,
#       ANNOUNCE it, then prepare whichever section is next in the fixed
#       S0..S6 queue for that model (resuming a not-yet-finalized section
#       in place instead of re-copying its fixture if one is already
#       mid-correction-round). Prints the section's task prompt + worktree
#       path. If all 7 sections are already finalized for this model,
#       prints the tier chart instead (idempotent re-entry).
#
#   bench.sh grade
#       Grades the model's CURRENT in-flight section (whichever `start`/the
#       previous `grade` last prepared - derived from on-disk state, no
#       section arg needed). Auto-appends the row via model-scorecard.sh
#       once finalized. If the section is not yet finalized (gate failed,
#       a correction round was used), prints "fix + re-run bench.sh grade"
#       and stops there - the operator/agent does nothing else. If
#       finalized and more sections remain, AUTOMATICALLY prepares the
#       next one (the queue advances with zero operator action). If that
#       was the last section (S6), prints the FINAL TIER CHART instead and
#       the run is complete.
#
#   bench.sh status
#       Prints detected model + current section + progress. No side effects.
#
#   bench.sh chart [<model>]
#       (Re-)prints the tier chart for a model (defaults to the
#       last-detected model for this bench.sh instance) without touching
#       any run state - this is what `grade` calls at the natural end of a
#       run, and what the self-test uses to verify tiering/ranking.
#
# Legacy note: run.sh / run-many.sh (manual multi-step, explicit
# per-section/per-model shuttling) are SUPERSEDED by this file for the
# interactive one-model flow - see their own headers. They still share the
# exact same on-disk state (lib/grade_state.py, runs/<model>/<section>/, and
# now lib/sections.sh) so a worktree either script prepared can be graded
# by the other with no conversion step.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$HERE"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
SCORECARD="$FLEET_DIR/model-scorecard.sh"
STATE_PY="$HERE/lib/grade_state.py"
DETECT_PY="$HERE/lib/detect_model.py"
CHART_PY="$HERE/lib/tier_chart.py"
TODAY="$(date +%F)"

# shellcheck source=lib/sections.sh
source "$HERE/lib/sections.sh"

MODEL_STATE="$HERE/runs/.current_model"

jget() {
  # jget <json-string> <key> - tiny helper so every field read below goes
  # through argv (not string-interpolated into python -c), avoiding quoting
  # bugs on model ids/paths.
  python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2"
}

detect_model() {
  local override="$1"
  if [ -n "$override" ]; then
    echo "$override"
    echo "(model: explicit --model override)" >&2
    return
  fi
  local out
  if out="$(python3 "$DETECT_PY" 2>/dev/null)" && [ -n "$out" ]; then
    local model age
    model="$(jget "$out" model)"
    age="$(jget "$out" age_s)"
    echo "$model"
    echo "(model: auto-detected from the opencode session DB - most-recently-updated session, ${age}s since its last /model switch; see lib/detect_model.py for why this method was chosen)" >&2
    return
  fi
  die "could not auto-detect the current model (no opencode session in ~/.local/share/opencode/opencode.db updated in the last 15 min).
FALLBACK: reply with your OWN model name (self-report it), then run:
  $HERE/bench.sh start --model <your-model-id>"
}

section_finalized() {
  local meta="$HERE/runs/$1/$2/meta.json"
  [ -f "$meta" ] || return 1
  local v
  v="$(python3 -c 'import json,sys; print(json.load(open(sys.argv[1])).get("finalized", False))' "$meta")"
  [ "$v" = "True" ]
}

section_in_progress() {
  [ -f "$HERE/runs/$1/$2/meta.json" ]
}

current_section() {
  # first section in the fixed S0..S6 queue not yet finalized for $model;
  # prints "" if every section is finalized (run complete).
  local model="$1"
  for s in "${ALL_SECTIONS[@]}"; do
    if ! section_finalized "$model" "$s"; then
      echo "$s"
      return
    fi
  done
  echo ""
}

prepare_section() {
  local section="$1" model="$2"
  local timebox; timebox="$(section_timebox_sec "$section")"
  local worktree fixture
  fixture="$(section_fixture "$section")"

  if section_in_progress "$model" "$section"; then
    worktree="$(python3 "$STATE_PY" path "$model" "$section")"
    echo "=================================================================="
    echo "SECTION $section  (model=$model, RESUMING an in-progress correction round - worktree untouched)"
  else
    worktree="$(python3 "$STATE_PY" init "$model" "$section" "$timebox")"
    rm -rf "$worktree"
    mkdir -p "$worktree"
    # copy the fixture, never node_modules/dist/pycache - the model/grader
    # (re)installs/builds fresh so the worktree reflects only real edits.
    ( cd "$fixture" && tar cf - --exclude node_modules --exclude dist --exclude __pycache__ --exclude .pytest_cache . ) \
      | ( cd "$worktree" && tar xf - )
    echo "=================================================================="
    echo "SECTION $section  (model=$model, work_class=$(section_work_class "$section"), time-box=${timebox}s)"
  fi
  echo "------------------------------------------------------------------"
  cat "$HERE/prompts/$(echo "$section" | tr 'A-Z' 'a-z').txt"
  echo "------------------------------------------------------------------"
  echo "WORKTREE: $worktree"
  echo "Implement the task above IN THAT WORKTREE now, using your own tools."
  echo "When ready, run:  $HERE/bench.sh grade"
  echo "(no section/model args needed - it grades whatever is currently in"
  echo "flight for the detected model, auto-appends the row, then advances"
  echo "to the next section automatically, or prints the tier chart if this"
  echo "was the last one)"
  echo "=================================================================="
}

do_start() {
  local override=""
  if [ "${1:-}" = "--model" ]; then override="${2:-}"; fi
  local model; model="$(detect_model "$override")"
  mkdir -p "$HERE/runs"
  echo "$model" > "$MODEL_STATE"
  echo "########################################################################"
  echo "# ANNOUNCE: running this benchmark AS model = $model"
  echo "########################################################################"
  local sec; sec="$(current_section "$model")"
  if [ -z "$sec" ]; then
    echo "All 7 sections (S0-S6) already finalized for $model - printing the tier chart."
    python3 "$CHART_PY" "$model"
    return
  fi
  prepare_section "$sec" "$model"
}

do_grade() {
  [ -f "$MODEL_STATE" ] || die "no active run - start one with: $HERE/bench.sh start"
  local model; model="$(cat "$MODEL_STATE")"
  local section; section="$(current_section "$model")"
  if [ -z "$section" ]; then
    echo "run already complete for $model:"
    python3 "$CHART_PY" "$model"
    return
  fi

  local worktree fixture grader
  worktree="$(python3 "$STATE_PY" path "$model" "$section")" || die "no prepared worktree for $model/$section - run: $HERE/bench.sh start"
  fixture="$(section_fixture "$section")"
  grader="$(section_grader "$section")"

  local grader_out
  grader_out="$($grader --worktree "$worktree" --baseline "$fixture")" || die "grader crashed: $grader_out"
  local score gate reason
  score="$(jget "$grader_out" score)"
  gate="$(jget "$grader_out" gate)"
  reason="$(jget "$grader_out" reason | tr '\t' ' ')"

  local record finalize corrections final_score time_s timed_out
  record="$(python3 "$STATE_PY" record "$model" "$section" "$score" "$gate")"
  finalize="$(jget "$record" finalize)"
  corrections="$(jget "$record" corrections)"
  final_score="$(jget "$record" final_score)"
  time_s="$(jget "$record" time_s)"
  timed_out="$(jget "$record" timed_out)"

  if [ "$finalize" != "True" ]; then
    echo "SECTION $section / $model: round $corrections/3 FAILED (score=$score, gate=$gate) - $reason"
    echo "Fix it IN THE SAME WORKTREE ($worktree) and re-run: $HERE/bench.sh grade"
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
  # Gateway-attributed spend (SR-5b): grade_state.py `record` diffs Charon's
  # own cumulative `cost_usd` (GET /charon/status) between this section's
  # `init` and now (lib/charon_cost.py). "-" only if the gateway wasn't
  # reachable/discoverable at either snapshot - never a guess. NOTE: this is a
  # GLOBAL gateway counter, not per-session - a concurrent fleet tab hitting
  # the same gateway during this section would pollute the delta (no
  # per-session cost exists in Charon yet); correct for the intended
  # one-dedicated-tab bench.sh workflow.
  local cost_usd; cost_usd="$(jget "$record" cost_usd)"

  bash "$SCORECARD" append "$TODAY" bench "$section" "$wclass" "$tier" "$model" "$verdict" "$gate" "$final_score" "$time_s" "$cost_usd" "$corrections" "$note"
  echo "SECTION $section / $model: FINAL score=$final_score verdict=$verdict time_s=$time_s corrections=$corrections -> appended to model-scorecard.tsv"

  local next; next="$(current_section "$model")"
  if [ -z "$next" ]; then
    echo ""
    echo "########################################################################"
    echo "# BENCHMARK COMPLETE for $model - all 7 sections (S0-S6) graded."
    echo "########################################################################"
    python3 "$CHART_PY" "$model"
  else
    echo ""
    echo "Advancing automatically to the next section..."
    prepare_section "$next" "$model"
  fi
}

do_status() {
  [ -f "$MODEL_STATE" ] || { echo "no active run"; return; }
  local model; model="$(cat "$MODEL_STATE")"
  local sec; sec="$(current_section "$model")"
  echo "model=$model  current_section=${sec:-<none - run complete>}"
}

do_chart() {
  local model="${1:-}"
  if [ -z "$model" ] && [ -f "$MODEL_STATE" ]; then model="$(cat "$MODEL_STATE")"; fi
  [ -n "$model" ] || die "usage: bench.sh chart <model>  (or run 'bench.sh start' first)"
  python3 "$CHART_PY" "$model"
}

main() {
  case "${1:-}" in
    start)  shift; do_start "$@" ;;
    grade)  shift; do_grade "$@" ;;
    status) shift; do_status "$@" ;;
    chart)  shift; do_chart "$@" ;;
    *) die "usage: bench.sh {start [--model <id>] | grade | status | chart [<model>]}" ;;
  esac
}

main "$@"
