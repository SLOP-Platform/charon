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

jget() {
  # jget <json-string> <key> - tiny helper so every field read below goes
  # through argv (not string-interpolated into python -c), avoiding quoting
  # bugs on model ids/paths.
  python3 -c 'import json,sys; print(json.loads(sys.argv[1])[sys.argv[2]])' "$1" "$2"
}

detect_model() {
  # bench-model-misdetect (P1, fleet/reds.tsv): auto-detect used to trust
  # the single most-recently-*touched* opencode session system-wide, which
  # silently misreports whenever some OTHER, unrelated concurrent tab was
  # touched more recently than the operator's own freshly-`/model`-picked
  # bench tab (very common in this rig's normal multi-tab operating mode -
  # session.time_updated bumps on ANY activity, not just /model). Confirmed
  # incident: announced hy3-preview-or instead of the operator's actual
  # glm-5.2 pick, saw hy3 already finalized, and silently SKIPPED the run.
  # lib/detect_model.py now REFUSES (exit 2) instead of guessing whenever
  # 2+ DIFFERENT models were set within its staleness window - see that
  # file's module docstring. `--model` remains the always-reliable explicit
  # path and is what RUN-BENCHMARK.md now recommends by default.
  local override="$1"
  if [ -n "$override" ]; then
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
  # bench-run-collision (P1): a bare file-existence check used to treat ANY
  # existing, non-finalized meta.json as "resume this" - including one that
  # was abandoned hours/days ago (its start_ts long past the section's own
  # timebox). grade_state.py's `is_active` instead only reports true while
  # the section is still within its CURRENT round's timebox - stale state
  # falls through to prepare_section's fresh-`init` path below instead of
  # being silently resumed with a poisoned clock. See lib/grade_state.py
  # module docstring for the full incident writeup.
  [ -f "$HERE/runs/$1/$2/meta.json" ] || return 1
  local active; active="$(python3 "$STATE_PY" is_active "$1" "$2")"
  [ "$active" = "true" ]
}

cost_mode_notice() {
  # SESSION-COST: one-time notice of which cost-attribution mode is active -
  # "session" (isolated from concurrent gateway traffic under any OTHER
  # session id) if the operator pre-wired CHARON_BENCH_SESSION_ID + a
  # matching opencode.json X-Charon-Session header BEFORE launching this
  # opencode tab, else "global" (the original method - a concurrent fleet
  # tab hitting the same gateway during this run WILL pollute cost_usd).
  # See lib/charon_cost.py `session_id()` for exactly why bench.sh cannot
  # mint this id itself (opencode's request headers are fixed at ITS OWN
  # process launch, which already happened before bench.sh ever runs).
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
  # bench-run-collision RESIDUAL (fleet/reds.tsv; harness-hardening
  # adversarial review must-fix #2) - FAIL-CLOSED half of the fix, called
  # ONLY from do_grade's/do_status's own no-`--model` branch, AFTER each has
  # already resolved $model from $MODEL_STATE in its own pre-existing style
  # (so do_status's original soft "no active run" message for a MISSING
  # pointer FILE is untouched by this - it only runs once there IS a model
  # name to check).
  #
  # $MODEL_STATE is a single pointer GLOBAL across every concurrent bench.sh
  # tab/process on this box - a DIFFERENT tab's `start` can silently
  # overwrite it between THIS caller's own `start` and this call, so an
  # LLM that forgets `--model` can resolve to the WRONG model entirely (the
  # exact mechanism that once misattributed a kimi-k2.6 grade to
  # deepseek-v4-pro). grade_state.py's `record` now independently refuses to
  # finalize a score against STALE state too (defense in depth - see its own
  # bench-run-collision-residual comment) - this is the earlier, cheaper
  # shell-level half of the same fix: fail fast with a clear message BEFORE
  # even running the grader, whenever the fallback resolves to a section
  # whose on-disk state isn't genuinely ACTIVE right now. A caller who
  # passes --model explicitly never calls this function at all - unaffected.
  local subcmd="$1" model="$2"
  local section; section="$(current_section "$model")"
  [ -z "$section" ] && return 0  # run already complete for this model - nothing to poison
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
    # bench-run-collision: was there stale/abandoned state here already (not
    # active per section_in_progress above, but on disk)? Surface that to
    # the operator/agent instead of silently discarding it.
    local had_stale_meta=false
    [ -f "$HERE/runs/$model/$section/meta.json" ] && had_stale_meta=true
    # BENCH_GUARD_ACTIVE_RUN=1: opt bench.sh into grade_state.py's
    # active-run guard (last-line TOCTOU defense - see its module docstring)
    # since bench.sh's own resume/fresh decision was JUST made above via
    # is_active; run.sh/run-many.sh deliberately don't set this, keeping
    # their existing always-reset PREPARE-mode contract unchanged.
    worktree="$(BENCH_GUARD_ACTIVE_RUN=1 python3 "$STATE_PY" init "$model" "$section" "$timebox")" \
      || die "could not initialize state for $model/$section - see error above (likely an active-run collision; another process may be using this model/section right now)"
    rm -rf "$worktree"
    mkdir -p "$worktree"
    # copy the fixture, never node_modules/dist/pycache - the model/grader
    # (re)installs/builds fresh so the worktree reflects only real edits.
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

do_grade() {
  # bench-run-collision (P1): resolving "which model am I" purely from the
  # single shared $MODEL_STATE file (last writer wins, GLOBAL across every
  # concurrent bench.sh tab/process on this box) is exactly how a kimi-k2.6
  # run's `grade` call once got silently misattributed to deepseek-v4-pro -
  # a DIFFERENT tab's `start` overwrote $MODEL_STATE in between. `--model`
  # (mirroring `start`'s own override) lets the agent pass back the EXACT
  # string it was told at start's ANNOUNCE banner (a self-report it already
  # has in its own conversation - no re-detection, no shared file, no
  # ambiguity), which is now what RUN-BENCHMARK.md instructs every run to
  # do. $MODEL_STATE remains the fallback for the legacy single-tab/manual
  # flow when no override is given - unchanged for that case, just no
  # longer the ONLY option.
  local override=""
  if [ "${1:-}" = "--model" ]; then override="${2:-}"; fi
  local model
  if [ -n "$override" ]; then
    model="$override"
  else
    [ -f "$MODEL_STATE" ] || die "no active run - start one with: $HERE/bench.sh start (or pass --model <id> explicitly - recommended whenever more than one bench.sh tab may be active concurrently)"
    model="$(cat "$MODEL_STATE")"
    refuse_if_stale_fallback grade "$model"
  fi
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

  # bench-premature-grade (P2): the model's own worktree file-write(s) can
  # still be flushing to disk in the instant right after it announces "done"
  # and invokes `grade` - grading that split second too early produced a
  # false-low score (observed: S5 scored 60, true settled state was 100).
  # Block until the worktree's newest file mtime has been stable (no writes)
  # for a few seconds - see lib/sections.sh `wait_for_worktree_stable`.
  wait_for_worktree_stable "$worktree"

  local grader_out
  grader_out="$($grader --worktree "$worktree" --baseline "$fixture")" || die "grader crashed: $grader_out"
  local score gate reason
  score="$(jget "$grader_out" score)"
  gate="$(jget "$grader_out" gate)"
  reason="$(jget "$grader_out" reason | tr '\t' ' ')"

  local record finalize corrections final_score time_s timed_out
  # bench-run-collision RESIDUAL, defense in depth: grade_state.py's `record`
  # can now itself refuse (prints {"error": ...}, exit 1) when this section's
  # state is STALE - surface that cleanly instead of letting `set -e` abort
  # the whole script with no message (the `if` form below is exempt from
  # errexit, unlike a bare `var="$(...)"` assignment).
  if ! record="$(python3 "$STATE_PY" record "$model" "$section" "$score" "$gate")"; then
    die "$(jget "$record" error 2>/dev/null || echo "$record")"
  fi
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
  # Gateway-attributed spend (SR-5b / SESSION-COST): grade_state.py `record`
  # diffs Charon's cumulative `cost_usd` between this section's `init` and
  # now (lib/charon_cost.py) - per-SESSION (isolated from concurrent traffic
  # under any other id) when CHARON_BENCH_SESSION_ID is wired, else the
  # original GLOBAL gateway counter (a concurrent fleet tab on the same
  # gateway during this section pollutes the delta - see cost_mode_notice
  # above, announced once at `start`). "-" only if the gateway wasn't
  # reachable/discoverable at either snapshot - never a guess.
  local cost_usd; cost_usd="$(jget "$record" cost_usd)"
  # TOKEN-CAPTURE: same delta the gateway reports alongside cost_usd (SEC 5a
  # weights tokens highest per BENCHMARK-V2-DESIGN.md) - grade_state.py
  # `record` now diffs tokens_in/tokens_out the same way it already diffs
  # cost_usd above. "-" only if the gateway didn't report them at either
  # snapshot (older gateway/provider) - never a guess. Passed to
  # model-scorecard.sh via env var (not a new positional arg - `append`'s
  # trailing `note` is variadic and already swallows the rest of argv; see
  # model-scorecard.sh's cmd_append comment for why).
  local tokens_in tokens_out
  tokens_in="$(jget "$record" tokens_in)"
  tokens_out="$(jget "$record" tokens_out)"

  CHARON_SCORECARD_TOKENS_IN="$tokens_in" CHARON_SCORECARD_TOKENS_OUT="$tokens_out" \
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
  local override=""
  if [ "${1:-}" = "--model" ]; then override="${2:-}"; fi
  local model
  if [ -n "$override" ]; then
    model="$override"
  else
    [ -f "$MODEL_STATE" ] || { echo "no active run"; return; }
    model="$(cat "$MODEL_STATE")"
    refuse_if_stale_fallback status "$model"
  fi
  local sec; sec="$(current_section "$model")"
  echo "model=$model  current_section=${sec:-<none - run complete>}"
}

do_chart() {
  local model="${1:-}"
  if [ -z "$model" ] && [ -f "$MODEL_STATE" ]; then model="$(cat "$MODEL_STATE")"; fi
  [ -n "$model" ] || die "usage: bench.sh chart <model>  (or run 'bench.sh start' first)"
  python3 "$CHART_PY" "$model"
}

do_reset() {
  # bench-model-misdetect (P1, fleet/reds.tsv) STEP 3: the harness had no
  # clean way to re-run a model whose 7 sections were ALREADY finalized
  # (e.g. moving a model to v2 scoring) short of hand-editing
  # runs/<model>/ and model-scorecard.tsv - this is that path. BACKS UP
  # first (never a bare delete), touches ONLY the one named model's state
  # (runs/<model>/ + its rows in model-scorecard.tsv, matched by the exact
  # `model` column value - col 6), and refuses on an ACTIVELY in-flight
  # section for that model unless --force is given, so it can't stomp a
  # bench that's genuinely mid-run right now.
  local model="" force=false
  while [ $# -gt 0 ]; do
    case "$1" in
      --model) model="${2:-}"; shift 2 ;;
      --force) force=true; shift ;;
      *) die "usage: bench.sh reset --model <id> [--force]" ;;
    esac
  done
  [ -n "$model" ] || die "usage: bench.sh reset --model <id> [--force]
Backs up then clears ONLY <id>'s runs/<id>/ state and its rows in
model-scorecard.tsv, so the next 'bench.sh start --model <id>' begins a
clean S0..S6 run (e.g. to move a model to v2 scoring). Never touches any
other model's data."
  # model becomes a path component below (runs/$model/...) - keep it to a
  # safe charset so this can never be tricked into a path-traversal rm -rf.
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
    # Only strip this model's BENCH-sourced rows (source=bench|bench2) - a
    # `live` row is real production usage signal, not re-runnable harness
    # output, and must survive a bench reset untouched.
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
