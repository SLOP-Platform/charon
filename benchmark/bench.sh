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
#       Enqueues a grading request into the out-of-band grader-daemon spool
#       (write-only from the agent's perspective) and polls for the result.
#       The daemon — not this agent — runs the grader, records the score,
#       and appends to the ledger. If the section is not yet finalized
#       (gate failed, a correction round was used), prints "fix + re-run
#       bench.sh grade" and stops there. If finalized and more sections
#       remain, AUTOMATICALLY prepares the next one (the queue advances
#       with zero operator action). If that was the last section (S6),
#       prints the FINAL TIER CHART instead and the run is complete.
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
#   bench.sh reset --model <id> [--force]
#       Operator-facing (not part of the agent's own S0..S6 loop): backs up
#       then clears ONLY <id>'s runs/<id>/ state and its rows in
#       model-scorecard.tsv, so a model whose 7 sections are already
#       finalized can be re-benchmarked cleanly (e.g. moving it to v2
#       scoring). Refuses if that model has a genuinely active in-flight
#       section unless --force is given. Never touches any other model's
#       data. See fleet/reds.tsv bench-model-misdetect.
#
# Legacy note: run.sh / run-many.sh (manual multi-step, explicit
# per-section/per-model shuttling) are SUPERSEDED by this file for the
# interactive one-model flow - see their own headers. They still share the
# exact same on-disk state (lib/grade_state.py, runs/<model>/<section>/, and
# now lib/sections.sh) so a worktree either script prepared can be graded
# by the other with no conversion step.
#
# Out-of-band grading (BENCH-OOB-GRADING #26): bench.sh LOSES its grading
# powers.  The agent signals "section done" by writing a grading request
# into the daemon's drop-spool; a SEPARATE grader-daemon process (running as
# the bench-grader unix user) snapshots the worktree, runs the grader from a
# mode-0700 answer-key tree, records the score, and appends the ledger row.
# The agent never reads grader sources or baseline fixtures, never appends
# to the ledger, and its pasted output is advisory/discarded — the daemon is
# the sole ledger writer.  See benchmark/grader-daemon.py and
# fleet/ADR-BENCH-OOB-GRADING.md.
set -euo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
BENCH_DIR="$HERE"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
SCORECARD="$FLEET_DIR/model-scorecard.sh"
SCORECARD_TSV="$FLEET_DIR/model-scorecard.tsv"
STATE_PY="$HERE/lib/grade_state.py"
DETECT_PY="$HERE/lib/detect_model.py"
CHART_PY="$HERE/lib/tier_chart.py"
TODAY="$(date +%F)"

# shellcheck source=lib/sections.sh
source "$HERE/lib/sections.sh"

MODEL_STATE="$HERE/runs/.current_model"
UNITS_TSV="$HERE/units.tsv"

# ── OOB grading spool config (#26) ─────────────────────────────────────────
# The daemon watches /var/lib/bench-grader/spool/req/ for incoming grading
# requests and writes results to spool/res/.  bench.sh writes the request
# then polls res/<run_id>.json.  The spool is mode 1733 (write-only + sticky
# for the agent), so the agent can enqueue but not read other requests.
SPOOL_REQ="${BENCH_SPOOL_REQ:-/var/lib/bench-grader/spool/req}"
SPOOL_RES="${BENCH_SPOOL_RES:-/var/lib/bench-grader/spool/res}"
SPOOL_POLL_TIMEOUT="${BENCH_SPOOL_POLL_TIMEOUT:-600}"

# poll_res <run_id> <timeout_s> — block until the daemon writes a result
# file for <run_id>, up to <timeout_s> seconds.  Prints the result's JSON
# content on stdout and returns 0.  If the timeout fires, returns 1.
poll_res() {
  local run_id="$1" timeout_s="${2:-600}"
  local result_file="$SPOOL_RES/${run_id}.json"
  local waited=0
  while [ "$waited" -lt "$timeout_s" ]; do
    if [ -f "$result_file" ]; then
      cat "$result_file"
      return 0
    fi
    sleep 1
    waited=$((waited + 1))
    if [ $((waited % 30)) -eq 0 ] && [ "$waited" -gt 0 ]; then
      echo "(waiting for daemon result — ${waited}s elapsed, timeout=${timeout_s}s)" >&2
    fi
  done
  return 1
}

unit_stage() {
  local uid="$1"
  [ -f "$UNITS_TSV" ] || { echo active; return; }
  awk -F'\t' -v u="$uid" '
    !/^#/ && $1!="unit_id" && $1==u { print $3; f=1; exit }
    END { if(!f) print "active" }' "$UNITS_TSV"
}

jget() {
  python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2"
}

normalize_model_id() {
  local id="${1:-}"
  [ -z "$id" ] && { echo ""; return; }
  python3 -c '
import os, sys
sys.path.insert(0, os.path.dirname(sys.argv[1]))
from detect_model import normalize_model_id as _norm
print(_norm(sys.argv[2]))
' "$DETECT_PY" "$id"
}

detect_model() {
  local override="$1"
  if [ -n "$override" ]; then
    override="$(normalize_model_id "$override")"
    echo "$override"
    echo "(model: explicit --model override)" >&2
    return
  fi
  local out rc=0
  out="$(python3 "$DETECT_PY" 2>/dev/null)" || rc=$?
  if [ "$rc" -eq 0 ] && [ -n "$out" ]; then
    local model age
    model="$(jget "$out" model)"
    age="$(jget "$out" age_s)"
    echo "$model"
    echo "(model: auto-detected from the opencode session DB - most-recently-updated session, ${age}s since its last /model switch; see lib/detect_model.py for why this method was chosen)" >&2
    return
  fi
  if [ "$rc" -eq 2 ] && [ -n "$out" ]; then
    local candidates; candidates="$(python3 -c 'import json,sys; print(", ".join(json.loads(sys.argv[1])["candidates"]))' "$out" 2>/dev/null || echo "$out")"
    die "refusing to auto-detect: AMBIGUOUS - more than one opencode tab set a DIFFERENT model
within the last 15 min ($candidates) - this is exactly the bench-model-misdetect incident
(fleet/reds.tsv): a concurrently-active OTHER tab can be touched more recently than YOUR
tab's own /model pick, so 'most recent' cannot be trusted here. Reply with your OWN model
name (self-report it - you already know it from your own /model selection), then run:
  $HERE/bench.sh start --model <your-model-id>"
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
  [ -f "$HERE/runs/$1/$2/meta.json" ] || return 1
  local active; active="$(python3 "$STATE_PY" is_active "$1" "$2")"
  [ "$active" = "true" ]
}

cost_mode_notice() {
  local mode
  mode="$(python3 "$HERE/lib/charon_cost.py" mode 2>/dev/null || echo global)"
  if [ "$mode" = "session" ]; then
    echo "(cost attribution: SESSION-isolated - immune to other tabs on this gateway)"
  else
    echo "(cost attribution: GLOBAL gateway counter - a concurrent fleet tab on the"
    echo " same gateway during this run will pollute cost_usd; set CHARON_BENCH_SESSION_ID"
    echo " + wire opencode.json's X-Charon-Session header BEFORE this opencode tab starts"
    echo " for isolated per-session cost instead)"
  fi
}

refuse_if_stale_fallback() {
  local subcmd="$1" model="$2"
  local section; section="$(current_section "$model")"
  [ -z "$section" ] && return 0
  local active
  active="$(python3 "$STATE_PY" is_active "$model" "$section" 2>/dev/null || echo false)"
  if [ "$active" != "true" ]; then
    die "refusing $subcmd without --model: the shared pointer ($MODEL_STATE) currently
resolves to model=$model section=$section, but that section's on-disk state is STALE
(not an actively in-flight run) - this is exactly how a kimi-k2.6 run once got
misattributed to deepseek-v4-pro (a DIFFERENT concurrent bench.sh tab's \`start\`
overwrote this shared pointer in between - see fleet/reds.tsv bench-run-collision).
Re-run with the EXACT model id from YOUR OWN start's ANNOUNCE line:
  $HERE/bench.sh $subcmd --model <your-id>"
  fi
}

current_section() {
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
    local had_stale_meta=false
    [ -f "$HERE/runs/$model/$section/meta.json" ] && had_stale_meta=true
    worktree="$(BENCH_GUARD_ACTIVE_RUN=1 python3 "$STATE_PY" init "$model" "$section" "$timebox")" \
      || die "could not initialize state for $model/$section - see error above (likely an active-run collision; another process may be using this model/section right now)"
    rm -rf "$worktree"
    mkdir -p "$worktree"
    ( cd "$fixture" && tar cf - --exclude node_modules --exclude dist --exclude __pycache__ --exclude .pytest_cache . ) \
      | ( cd "$worktree" && tar xf - )
    echo "=================================================================="
    echo "SECTION $section  (model=$model, work_class=$(section_work_class "$section"), time-box=${timebox}s)"
    if [ "$had_stale_meta" = true ]; then
      echo "NOTE: a prior state dir existed for $model/$section but was STALE"
      echo "(past its own timebox with no active run extending it) - discarded,"
      echo "starting FRESH with a new start_ts. If that prior run already"
      echo "produced a scorecard row, review it manually (see fleet/reds.tsv"
      echo "bench-run-collision)."
    fi
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
  echo "#"
  echo "# STOP - VERIFY before implementing anything: does '$model' match the"
  echo "# model YOU just picked with /model in THIS tab? If not (e.g. right"
  echo "# after an opencode restart, or with multiple tabs open), Ctrl-C and"
  echo "# re-run explicitly instead of trusting auto-detect:"
  echo "#   $HERE/bench.sh start --model <your-model-id>"
  echo "# See fleet/reds.tsv bench-model-misdetect for the incident this guards."
  echo "########################################################################"
  cost_mode_notice
  local sec; sec="$(current_section "$model")"
  if [ -z "$sec" ]; then
    echo "All 7 sections (S0-S6) already finalized for $model - printing the tier chart."
    python3 "$CHART_PY" "$model"
    return
  fi
  prepare_section "$sec" "$model"
}

# ── do_grade — OOB (out-of-band) grading via the grader-daemon spool ─────────
# bench.sh LOSES its direct grading powers (#26 / BENCH-OOB-GRADING).  Instead
# of calling the grader directly, it writes a grading request into the daemon's
# drop-spool and polls for the result.  The daemon (running as the bench-grader
# unix user) snapshots the worktree, runs the grader from a mode-0700 answer-key
# tree, records the score, and appends to the ledger.  bench.sh never reads
# grader sources, never appends to model-scorecard.tsv, and never computes a
# score or verdict itself — the daemon is the sole ledger writer.
do_grade() {
  local override=""
  if [ "${1:-}" = "--model" ]; then override="$(normalize_model_id "${2:-}")"; fi
  local model
  if [ -n "$override" ]; then
    model="$override"
  else
    [ -f "$MODEL_STATE" ] || die "no active run - start one with: $HERE/bench.sh start (or pass --model <id> explicitly - recommended whenever more than one bench.sh tab may be active concurrently)"
    model="$(normalize_model_id "$(cat "$MODEL_STATE")")"
    refuse_if_stale_fallback grade "$model"
  fi
  local section; section="$(current_section "$model")"
  if [ -z "$section" ]; then
    echo "run already complete for $model:"
    python3 "$CHART_PY" "$model"
    return
  fi

  local worktree fixture
  worktree="$(python3 "$STATE_PY" path "$model" "$section")" || die "no prepared worktree for $model/$section - run: $HERE/bench.sh start"
  fixture="$(section_fixture "$section")"

  # ── wait for worktree to settle ────────────────────────────────────────────
  wait_for_worktree_stable "$worktree"

  # ── enqueue grading request into the daemon spool ──────────────────────────
  local run_id; run_id="$(printf '%s-%s-%s' "$model" "$section" "$(date +%s)")"
  local req_file="$SPOOL_REQ/${run_id}.json"

  if [ ! -d "$SPOOL_REQ" ]; then
    die "daemon spool req/ dir not found: $SPOOL_REQ
The grader-daemon must be running (bench-grader user). Start it with:
  sudo -u bench-grader python3 /home/stack/code/charon-fleet-BENCH-OOB-GRADING/benchmark/grader-daemon.py
or (in its own systemd service):
  systemctl start bench-grader"
  fi

  local stage; stage="$(unit_stage "$section")"
  python3 -c '
import json, sys
req = {
    "run_id":   sys.argv[1],
    "model":    sys.argv[2],
    "unit_id":  sys.argv[3],
    "kind":     "section",
    "worktree": sys.argv[4],
    "stage":    sys.argv[5],
}
json.dump(req, open(sys.argv[6], "w"), indent=2)
' "$run_id" "$model" "$section" "$worktree" "$stage" "$req_file" \
    || die "failed to write grading request to spool: $req_file"

  echo "Enqueued grading request for $model/$section via daemon spool (run_id=$run_id)"

  # ── poll for the daemon's result ───────────────────────────────────────────
  local result_json
  if ! result_json="$(poll_res "$run_id" "$SPOOL_POLL_TIMEOUT")"; then
    die "grader-daemon did not respond for $model/$section within ${SPOOL_POLL_TIMEOUT}s (run_id=$run_id)
Check: is the grader-daemon running?
  sudo -u bench-grader python3 /home/stack/code/charon-fleet-BENCH-OOB-GRADING/benchmark/grader-daemon.py"
  fi

  # ── parse the daemon's result ──────────────────────────────────────────────
  local success score gate reason record finalize corrections final_score time_s timed_out
  success="$(jget "$result_json" success)"
  score="$(jget "$result_json" score)"
  gate="$(jget "$result_json" gate)"
  reason="$(jget "$result_json" reason | tr '\t' ' ')"

  if [ "$success" != "True" ]; then
    echo "SECTION $section / $model: daemon reported ERROR — $reason"
    return 1
  fi

  record="$(python3 -c 'import json,sys; print(json.dumps(json.loads(sys.argv[1])["record"]))' "$result_json")"
  finalize="$(jget "$record" finalize)"
  corrections="$(jget "$record" corrections)"
  final_score="$(jget "$record" final_score)"
  time_s="$(jget "$record" time_s)"
  timed_out="$(jget "$record" timed_out)"

  # ── handle correction round (not yet finalized) ────────────────────────────
  if [ "$finalize" != "True" ]; then
    echo "SECTION $section / $model: round $corrections/3 FAILED (score=$score, gate=$gate) - $reason"
    echo "Fix it IN THE SAME WORKTREE ($worktree) and re-run: $HERE/bench.sh grade"
    return 0
  fi

  # ── section finalized — display result and advance ─────────────────────────
  local note="$reason"
  if [ "$timed_out" = "True" ]; then note="timeout ($note)"; fi
  local verdict; verdict="$(verdict_from_score "$final_score")"
  local cost_usd; cost_usd="$(jget "$record" cost_usd)"

  echo "SECTION $section / $model: FINAL score=$final_score verdict=$verdict time_s=$time_s corrections=$corrections cost_usd=$cost_usd -> (daemon appended to model-scorecard.tsv)"

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
  local override=""
  if [ "${1:-}" = "--model" ]; then override="$(normalize_model_id "${2:-}")"; fi
  local model
  if [ -n "$override" ]; then
    model="$override"
  else
    [ -f "$MODEL_STATE" ] || { echo "no active run"; return; }
    model="$(normalize_model_id "$(cat "$MODEL_STATE")")"
    refuse_if_stale_fallback status "$model"
  fi
  local sec; sec="$(current_section "$model")"
  echo "model=$model  current_section=${sec:-<none - run complete>}"
}

do_chart() {
  local model="${1:-}"
  [ -n "$model" ] && model="$(normalize_model_id "$model")"
  if [ -z "$model" ] && [ -f "$MODEL_STATE" ]; then model="$(normalize_model_id "$(cat "$MODEL_STATE")")"; fi
  [ -n "$model" ] || die "usage: bench.sh chart <model>  (or run 'bench.sh start' first)"
  python3 "$CHART_PY" "$model"
}

do_reset() {
  local model="" force=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) model="$(normalize_model_id "${2:-}")"; shift 2 ;;
      --force) force=true; shift ;;
      *) die "usage: bench.sh reset --model <id> [--force]" ;;
    esac
  done
  [ -n "$model" ] || die "usage: bench.sh reset --model <id> [--force]
Backs up then clears ONLY <id>'s runs/<id>/ state and its rows in
model-scorecard.tsv, so the next 'bench.sh start --model <id>' begins a
clean S0..S6 run (e.g. to move a model to v2 scoring). Never touches any
other model's data."
  case "$model" in
    *[!A-Za-z0-9._-]*|""|.|..)
      die "refusing reset: model id '$model' has characters outside [A-Za-z0-9._-] - not safe to use as a path component" ;;
  esac

  if [ "$force" != true ]; then
    for s in "${ALL_SECTIONS[@]}"; do
      [ -f "$HERE/runs/$model/$s/meta.json" ] || continue
      local active; active="$(python3 "$STATE_PY" is_active "$model" "$s" 2>/dev/null || echo false)"
      if [ "$active" = "true" ]; then
        die "refusing reset: $model/$s has an ACTIVE in-flight run (within its own
timebox right now) - let it finish/fail out first, or pass --force to override
(NOT recommended while a bench may genuinely be running)."
      fi
    done
  fi

  local ts; ts="$(date +%Y%m%dT%H%M%S)"
  local backup_dir="$HERE/runs/.reset-backups/${model}-${ts}"
  mkdir -p "$backup_dir"

  if [ -d "$HERE/runs/$model" ]; then
    cp -a "$HERE/runs/$model" "$backup_dir/runs"
    rm -rf "$HERE/runs/$model"
    echo "backed up runs/$model/ -> $backup_dir/runs, then cleared it"
  else
    echo "no existing runs/$model/ to clear (nothing to back up there)"
  fi

  if [ -f "$SCORECARD_TSV" ]; then
    cp -a "$SCORECARD_TSV" "$backup_dir/model-scorecard.tsv.bak"
    local before after removed
    before="$(awk -F'\t' '!/^#/ && NF>0' "$SCORECARD_TSV" | wc -l)"
    awk -F'\t' -v m="$model" 'BEGIN{OFS="\t"}
      /^#/ || NF==0 {print; next}
      $6 == m && ($2 == "bench" || $2 == "bench2") {next}
      {print}' \
      "$SCORECARD_TSV" > "$backup_dir/model-scorecard.tsv.new"
    after="$(awk -F'\t' '!/^#/ && NF>0' "$backup_dir/model-scorecard.tsv.new" | wc -l)"
    removed=$((before - after))
    mv "$backup_dir/model-scorecard.tsv.new" "$SCORECARD_TSV"
    echo "backed up model-scorecard.tsv -> $backup_dir/model-scorecard.tsv.bak, removed $removed bench-sourced row(s) for model=$model (any 'live' rows for this model were kept)"
  else
    echo "no $SCORECARD_TSV found - nothing to strip there"
  fi

  if [ -f "$MODEL_STATE" ] && [ "$(cat "$MODEL_STATE")" = "$model" ]; then
    rm -f "$MODEL_STATE"
    echo "cleared shared runs/.current_model pointer (it pointed at $model)"
  fi

  echo "reset complete for model=$model."
  echo "backup: $backup_dir"
  echo "next: $HERE/bench.sh start --model $model    # begins a clean S0..S6 run"
}

main() {
  case "${1:-}" in
    start)  shift; do_start "$@" ;;
    grade)  shift; do_grade "$@" ;;
    status) shift; do_status "$@" ;;
    chart)  shift; do_chart "$@" ;;
    reset)  shift; do_reset "$@" ;;
    *) die "usage: bench.sh {start [--model <id>] | grade [--model <id>] | status [--model <id>] | chart [<model>] | reset --model <id> [--force]}" ;;
  esac
}

main "$@"
