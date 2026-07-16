#!/usr/bin/env bash
# charon-run.sh <cwd> <outlog> <brief-file> <model1> [model2 ...]
# Headless opencode against the Charon gateway with CROSS-MODEL failover.
# Charon already fails over across PROVIDERS for one model id; this adds failover
# across MODELS when one is exhausted across all its providers (session/rate limit).
# Zero Claude limit (all models are non-Claude on the 4-LOM gateway).
set -u
PFR_DEBUG="${PFR_DEBUG:-0}"
dbg() { [ "$PFR_DEBUG" = "1" ] && printf '[charon-run][DEBUG] %s\n' "$*" >&2; return 0; }
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
CWD="$1"; OUT="$2"; BRIEF="$3"; shift 3
MODELS=("$@")
PROMPT="$(cat "$BRIEF")"
dbg "invoked: cwd=$CWD out=$OUT brief=$BRIEF models=[${MODELS[*]}]"
: > "$OUT"
LABEL=$(basename "$OUT" .txt)
LEDGER="${CHARON_EXHAUST_LEDGER:-/home/stack/charon-private/fleet/provider-exhaustion-ledger.tsv}"
if [ ! -f "$LEDGER" ]; then
  printf 'ts\tjob\tmodel\tevent\tnote\n' > "$LEDGER" 2>/dev/null || true
fi
 led() { printf '%s\t%s\t%s\t%s\t%s\n' "$(date -u +%FT%TZ)" "$LABEL" "$1" "$2" "$3" >> "$LEDGER" 2>/dev/null || true; }
# SALVAGE-STASH-CHARON-RUN (rc=124 disambiguation): read-only peek at opencode's
# own structured log to tell "model genuinely too slow" apart from "gateway
# pool exhausted and opencode silently retried" when the `timeout` wrapper
# kills the subprocess. opencode's CLI stdout does NOT surface "all providers
# exhausted" (it hangs silently until `timeout` fires) — without this signal
# the two cases are indistinguishable from $OUT alone, and a pool-exhaustion
# masquerade was getting charged to the model as a too-slow fault. Callers can
# override the path (e.g. tests inject a hermetic fake).
OPENCODE_LOG="${OPENCODE_LOG:-$HOME/.local/share/opencode/log/opencode.log}"

# ── FLAW-2 fix (adversarial review 2026-07-13): provider/local/infra faults
# must NEVER be attributed to the model. Before this, ANY nonzero rc that
# wasn't a rate-limit signal fell into the generic `elif RC -ne 0` branch
# below and enqueued a model BLOCK -- so a gateway 5xx, a reset/refused
# connection, a context-deadline, a local sqlite "database is locked", the
# `timeout 1800` wrapper firing (rc=124), or an opaque server error (e.g.
# phi-4's rc=3 UnknownError) all wrongly detained the MODEL for a fault that
# was the PROVIDER's or the local session's, not the model's. This mirrors
# the SAME taxonomy benchmark/dogfood-to-scorecard.sh's classify() already
# uses (`provider-*|error-nonlimit*) -> SKIP`) and benchmark/lib/
# dogfood-attribution.sh's db-lock/opaque-error buckets -- same categories,
# reused here rather than forked, adapted to this script's per-attempt
# (mid-loop, single-attempt tail) shape rather than dogfood-eval.sh's
# post-hoc whole-log shape.
# is_infra_fault <rc> <tail_text> -> 0 (true) if this attempt's failure is a
# provider/local/infra symptom that must enqueue NOTHING (not model quality).
is_infra_fault() {
  local rc="$1" tail="$2"
  # rc=124 (the `timeout` wrapper firing) is handled EXPLICITLY in the per-model loop
  # below, BEFORE this function is ever called -- it distinguishes genuine too-slow
  # (model streamed output, model-attributable, latency-is-a-failure-class) from a
  # hung/no-output leg (infra symptom). is_infra_fault no longer blanket-treats
  # rc=124 as infra (EVAL-LATENCY-GATE fix for the F1 dead-code bug -- see the
  # rc=124 branch below and lib/dogfood-attribution.sh's classify_attribution).
  # opaque rc=3 (confirmed real-world signature: phi-4 via a funded DeepInfra
  # gateway path -- see benchmark/lib/dogfood-attribution.sh's UnknownError
  # note) -- a bare non-descriptive exit code with no model-attributable
  # content is an infra/opaque fault, not a model-quality signal.
  [ "$rc" -eq 3 ] && return 0
  printf '%s' "$tail" | grep -qiE \
    '\b5(0[0-9]|[1-9][0-9])\b.*(gateway|server|error)|bad gateway|service unavailable|gateway timeout|connection (reset|refused)|econnreset|econnrefused|context deadline exceeded|database is locked|"name"[[:space:]]*:[[:space:]]*"?unknownerror|internal server error' \
    && return 0
  return 1
}

# ── scorecard capture hook (grader-safe: enqueues to the bench-grader-owned
# spool; NEVER writes model-scorecard.tsv itself — see capture/enqueue-capture.sh
# + fleet/ADR-BENCH-OOB-GRADING.md). Best-effort: never fails the run.
# `ref` comes from CHARON_JOB_REF (set by fleet-droid.sh) falling back to LABEL
# so a standalone invocation still gets a usable ref.
CAPTURE_SCRIPT="$SCRIPT_DIR/capture/enqueue-capture.sh"
CAPTURE_MODEL_USED_DIR="$SCRIPT_DIR/state/model-used"
cap() {  # cap <model> <claimed-result> [<verdict> <gate> <evidence>]
  [ -x "$CAPTURE_SCRIPT" ] || return 0
  local m="$1" claimed="$2" verdict="${3:-}" gate="${4:-}" evid="${5:-}"
  local args=(--model "$m" --claimed-result "$claimed" --ref "${CHARON_JOB_REF:-$LABEL}")
  if [ -n "$verdict" ]; then
    local sc=0; [ "$gate" = "pass" ] && sc=100
    args+=(--stage active --actual-verdict "$verdict" --actual-gate "$gate" --score "$sc" --evidence "$evid" --call-log-report)
  else
    args+=(--stage provisional)
  fi
  "$CAPTURE_SCRIPT" "${args[@]}" >/dev/null 2>&1 || true
}
for M in "${MODELS[@]}"; do
  echo "===== [charon-run] attempt: charon/$M @ $(basename "$CWD") =====" >> "$OUT"
  MARK=$(wc -l < "$OUT")
  dbg "attempt model=charon/$M cwd=$CWD cmd: timeout 1800 opencode run --model charon/$M <PROMPT, ${#PROMPT} bytes>"
  # `</dev/null`: this subprocess must NEVER read stdin. When this script is
  # invoked from preflight.sh's per-task `while read` loop, an inherited,
  # unbounded stdin here is what silently truncates that loop to ONE task
  # (see preflight.sh's fd-3 fix + comment) — belt-and-suspenders even when
  # invoked standalone (headless run should never block on / consume tty
  # input either).
  # Honor the caller's latency budget (dogfood-eval/preflight pass CHARON_RUN_TIMEOUT_S);
  # only fall back to 1800 when unset. Hardcoding 1800 let a hung/edit-loop model burn 30min
  # instead of its budget (latency-is-a-failure-class).
  # SALVAGE-STASH-CHARON-RUN: capture start wall-clock (epoch + ISO) so the
  # OPENCODE_LOG peek can be scoped to events that fired DURING this attempt.
  # Using a local var (not the global `SECONDS` builtin) so a subshell launched
  # before the `(cd ...)` wouldn't reset the clock.
  ATTEMPT_START_EPOCH=$(date -u +%s)
  ATTEMPT_START_ISO=$(date -u -d "@$ATTEMPT_START_EPOCH" +%FT%TZ 2>/dev/null || date -u +%FT%TZ)
  ( cd "$CWD" && timeout "${CHARON_RUN_TIMEOUT_S:-1800}" opencode run --model "charon/$M" "$PROMPT" ) </dev/null >> "$OUT" 2>&1
  RC=$?
  dbg "attempt model=charon/$M exit_code=$RC"
  TAIL=$(tail -n +"$MARK" "$OUT")
  # Hard failure OR limit-signal in this attempt's tail -> fail over to next model.
  if printf '%s' "$TAIL" | grep -qiE '\b429\b|rate.?limit|quota exceeded|insufficient (funds|credit|balance)|session limit|no capacity|model (is )?(over|exhausted)|out of (credit|quota)'; then
    echo "[charon-run] model '$M' hit a provider/session LIMIT -> failing over" >> "$OUT"
    led "$M" "limit-failover" "rc=$RC; all providers for this model exhausted at gateway"
    # NOT a scorecard-worthy quality signal (provider/session exhaustion, not model
    # competence) -- matches dogfood-to-scorecard.sh's classify() SKIP for provider-*.
    continue
  elif [ "$RC" -eq 124 ]; then
    # EVAL-LATENCY-GATE fix (review F1): the `timeout` wrapper killed the subprocess
    # at its budget. Distinguish (a) genuine too-slow -- the model streamed real
    # output but didn't finish in time (model-attributable; latency-is-a-failure-
    # class) -- from (b) a hung/no-output leg -- literally nothing came back before
    # the budget (an infra/leg symptom, never the model's fault). TAIL's first line
    # is always this attempt's own "===== attempt: ... =====" banner (see MARK
    # above), so strip it before checking for real opencode output.
    #
    # The two marker strings below are grepped VERBATIM by lib/dogfood-attribution.sh's
    # classify_attribution. Change one side, change both, or the F1 dead-code bug
    # (strings that agree with nothing) returns.
    #
    # SALVAGE-STASH-CHARON-RUN: BEFORE classifying too-slow vs leg-fault, peek at
    # opencode's own log for "all providers exhausted" events that fired during this
    # attempt. If the gateway pool was being drained and opencode was silently
    # retrying in a loop, the rc=124 is a PROVIDER symptom (masquerading as a hang),
    # never a model-attributable timeout. This is the third sub-case of the rc=124
    # branch and the only one that does NOT scorecard-BLOCK the model.
    EXHAUST_HITS=0
    if [ -f "$OPENCODE_LOG" ]; then
      # opencode log lines look like:
      #   timestamp=2026-07-13T20:25:23.537Z level=ERROR ... modelID=$M ... "all providers exhausted"
      # Timestamps are ISO-8601 UTC -> lexical `>=` against ATTEMPT_START_ISO is
      # valid and avoids any date parsing. `modelID=$M` is the gateway alias (the
      # only providerID opencode surfaces client-side), not the upstream sub-provider.
      EXHAUST_HITS=$(awk -v m="modelID=$M" -v t0="$ATTEMPT_START_ISO" '
        /^timestamp=/ && $0 ~ m && /all providers exhausted/ {
          ts = substr($1, index($1, "=") + 1)
          if (ts >= t0) c++
        }
        END { print c+0 }
      ' "$OPENCODE_LOG" 2>/dev/null || echo 0)
    fi
    if [ "${EXHAUST_HITS:-0}" -gt 0 ]; then
      # SALVAGE-STASH-CHARON-RUN: the EXACT marker text "TIMEOUT (rc=124.*CAUSE:
      # gateway pool exhausted" is what lib/dogfood-attribution.sh's
      # classify_attribution greps for (see its line-41 marker check) — change
      # one side, change both. NOT a model-attributable timeout: the gateway
      # pool was empty and opencode was retrying silently. Park and move on.
      echo "[charon-run] model '$M' TIMEOUT (rc=124) budget=${CHARON_RUN_TIMEOUT_S:-1800}s — CAUSE: gateway pool exhausted (${EXHAUST_HITS}x 'all providers exhausted' in opencode log during this attempt) -> provider-side, not model-slow -> failing over" >> "$OUT"
      led "$M" "pool-exhausted-timeout" "rc=124; budget=${CHARON_RUN_TIMEOUT_S:-1800}s; ${EXHAUST_HITS}x all-providers-exhausted in opencode.log during this attempt; provider-side, not model-attributable"
      # NOT scorecard-BLOCK'd: pool exhaustion is never a model-quality signal.
      continue
    fi
    OPCODE_TAIL="$(printf '%s' "$TAIL" | tail -n +2)"
    if printf '%s' "$OPCODE_TAIL" | grep -q '[^[:space:]]'; then
      echo "[charon-run] model '$M' TIMEOUT (rc=124) budget=${CHARON_RUN_TIMEOUT_S:-1800}s too-slow FAIL (leg healthy: output observed before budget)" >> "$OUT"
      led "$M" "too-slow-failover" "rc=124; budget=${CHARON_RUN_TIMEOUT_S:-1800}s; model streamed output but did not finish -- latency-is-a-failure-class, model-attributable"
      cap "$M" "FAIL" "BLOCK" "fail" "charon-run TIMEOUT rc=124 budget=${CHARON_RUN_TIMEOUT_S:-1800}s: model streamed output but exceeded the latency budget"
    else
      echo "[charon-run] model '$M' TIMEOUT (rc=124) leg-fault: no output before budget=${CHARON_RUN_TIMEOUT_S:-1800}s (hang, not model-attributable)" >> "$OUT"
      led "$M" "leg-fault-failover" "rc=124; budget=${CHARON_RUN_TIMEOUT_S:-1800}s; no output observed before the timeout -- leg/infra hang, not a model verdict"
      # NOT a scorecard-worthy quality signal -- a dead/hung leg is never model-attributable.
    fi
    continue
  elif [ "$RC" -ne 0 ] && is_infra_fault "$RC" "$TAIL"; then
    echo "[charon-run] model '$M' hit a provider/local/infra FAULT (rc=$RC, not model quality) -> failing over" >> "$OUT"
    led "$M" "infra-fault-failover" "rc=$RC; provider/local/infra symptom (5xx/reset/refused/deadline/db-lock/timeout/opaque) -- not a model verdict"
    # NOT a scorecard-worthy quality signal -- matches dogfood-to-scorecard.sh's
    # classify() SKIP for provider-*/error-nonlimit* (see is_infra_fault above).
    continue
  elif [ "$RC" -ne 0 ]; then
    echo "[charon-run] model '$M' exited nonzero (rc=$RC, not a limit, not an infra fault) -> failing over" >> "$OUT"
    led "$M" "error-failover" "rc=$RC; non-limit, non-infra failure (genuine model-attributable result)"
    cap "$M" "FAIL" "BLOCK" "fail" "opencode exited rc=$RC (non-limit, non-infra failure, self-evident at run time)"
    continue
  fi
  echo "[charon-run] SUCCESS on model '$M' (rc=0)" >> "$OUT"
  echo "CHARON_RUN_RESULT=SUCCESS model=$M" >> "$OUT"
  # Claim only (PROVISIONAL) -- the run exiting 0 is not yet a verified MERGE;
  # done.sh supplies the FINAL actual_verdict/gate once the merge is proof-verified.
  cap "$M" "SUCCESS"
  mkdir -p "$CAPTURE_MODEL_USED_DIR" 2>/dev/null && printf '%s\n' "$M" > "$CAPTURE_MODEL_USED_DIR/${CHARON_JOB_REF:-$LABEL}" 2>/dev/null || true
  exit 0
done
echo "[charon-run] ALL MODELS EXHAUSTED: ${MODELS[*]}" >> "$OUT"
led "${MODELS[*]}" "ALL-EXHAUSTED" "every model failed over; POOL TOO THIN -> consider adding providers"
echo "CHARON_RUN_RESULT=EXHAUSTED" >> "$OUT"
exit 3
