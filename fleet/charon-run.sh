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

# ── DROID-CLIENT-PREFLIGHT (2026-07-24): make the work client resolvable
# regardless of the CALLER'S SHELL TYPE, then prove it is there before burning
# the failover chain.
#
# Root cause it fixes: `$HOME/.local/bin` (where `opencode` lives) is put on
# PATH only by ~/.bashrc and ~/.profile — i.e. only for an INTERACTIVE or LOGIN
# shell. A fleet-droid.sh tab launched from a non-login, non-interactive shell
# (setsid/nohup/sh -c/tool-invoked wrapper) therefore ran `timeout … opencode`
# with no `opencode` on PATH -> `timeout` exits 127 -> every model in the chain
# "failed" in under a second -> bogus "ALL MODELS EXHAUSTED / POOL TOO THIN".
# See fleet/state/reviews/DROID-SESSION-FAILURE-agen-kolar.md.
#
# APPEND, never prepend: anything already resolvable on the caller's PATH must
# keep winning (hermetic tests stub `opencode` via PATH="$STUBDIR:$PATH", and a
# deliberate operator override must not be shadowed by ~/.local/bin). This adds
# a FALLBACK location only, and only when it is not already on PATH.
case ":${PATH}:" in
  *":$HOME/.local/bin:"*) : ;;
  *) [ -d "$HOME/.local/bin" ] && export PATH="$PATH:$HOME/.local/bin" ;;
esac
# The client is the DEFAULT, not a hardwire (same posture as fleet-droid.sh's
# swappable $CHARON_AGENT_CMD): an operator can point this at any CLI with the
# same `run --model <id> <prompt>` contract.
OPENCODE_BIN="${OPENCODE_BIN:-opencode}"

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
  # ── EXIT-CODE CLASS (DROID-CLIENT-PREFLIGHT, 2026-07-24) ────────────────
  # Written as a PREDICATE OVER A CLASS, deliberately not as a list of magic
  # numbers bolted on one incident at a time -- that accretion is exactly how
  # this predicate came to mis-book 42 of 46 lifetime BLOCK enqueues as model
  # failures (fleet/state/reviews/SCORECARD-FALSE-BLOCK-AUDIT-agen-kolar.md).
  # One of those is ALREADY MERGED into the live ledger routing ranks on:
  # model-scorecard.tsv:36, kimi-k2.6, rc=134 (SIGABRT).
  #
  # The question this answers is ALWAYS: "did the MODEL produce a bad result,
  # or did the LOCAL BOX fail to run it?" Only the former is a model verdict.
  case "$rc" in
    2)   # The client rejected our ARGUMENTS (argparse/usage). We built the
         # command line, not the model. A launcher bug is never a model fault.
         return 0 ;;
    125) # `timeout` itself failed (its own internal error, distinct from 124
         # = "child hit the budget", which is classified in the caller above).
         return 0 ;;
    126) # Found but NOT EXECUTABLE: bad perms, wrong ELF, noexec mount, bad
         # interpreter line. The client never started.
         return 0 ;;
    127) # COMMAND NOT FOUND. The purest possible infra fault, and the one that
         # produced three zero-commit sessions and 24 false BLOCKs when a
         # non-login shell left ~/.local/bin off PATH.
         return 0 ;;
  esac
  # SIGNAL DEATH: the shell reports a child killed by signal N as 128+N. A
  # signal is something the ENVIRONMENT did TO the process -- OOM killer (137
  # SIGKILL), operator Ctrl-C (130 SIGINT), supervisor stop (143 SIGTERM),
  # native crash in the client binary (134 SIGABRT, 139 SIGSEGV). None is the
  # model expressing a bad answer. Observed in the audit: 130 131 132 134 135
  # 137 139 141 143 -- enumerating those nine would leave the tenth to be
  # discovered by another poisoned ledger, so the RULE is the whole range.
  # Safe as a rule because a CLI chooses small exit codes; >=128 is the shell's
  # signal encoding, not a value the client picks to mean "the model failed".
  [ "$rc" -ge 128 ] && return 0
  # ── rc=1 IS DELIBERATELY *NOT* IN THE CLASS ─────────────────────────────
  # rc=1 is the genuinely ambiguous one: it is both the client's generic
  # "your run failed" (a REAL model verdict) and the exit code of an auth
  # rejection or a `cd` into a reaped worktree (infra). Blanket-classifying it
  # as infra would silently swallow every real model failure -- a false INFRA
  # is exactly as corrosive as a false BLOCK, just in the other direction.
  # So rc=1 stays TEXT-DISCRIMINATED: it is infra only when this attempt's own
  # output carries a recognised infra signature, and a bare rc=1 with nothing
  # infra in the tail is still charged to the model. The two rc=1 infra shapes
  # the audit newly identified -- auth rejection and the reaped-worktree `cd`
  # -- are added to the pattern below rather than to the code class.
  printf '%s' "$tail" | grep -qiE \
    '\b5(0[0-9]|[1-9][0-9])\b.*(gateway|server|error)|bad gateway|service unavailable|gateway timeout|connection (reset|refused)|econnreset|econnrefused|context deadline exceeded|database is locked|"name"[[:space:]]*:[[:space:]]*"?unknownerror|internal server error|\b(401|403)\b|unauthorized|forbidden|invalid api key|missing or invalid bearer|authentication (failed|error)|(cd|chdir):.*no such file or directory|can'"'"'t cd to' \
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
# ANNOUNCE (observability): the MODEL failover chain is driven HERE, so the first leg (primary) is
# known up front and the last leg on success (below) — announce both so a job's log shows
# "started on X -> finished on Y" and a failover is visible when they differ. CAVEAT: the actual
# UPSTREAM PROVIDER for each leg is picked by the gateway (SG) behind the charon/<model> alias and is
# NOT surfaced to this wrapper by opencode; announcing the real provider needs an SG-side
# X-Charon-Provider header + a session-tagged routing log (separate, not cheap). The model leg is
# truthful and free — that is what we announce here.
# ── CLIENT PREFLIGHT (DROID-CLIENT-PREFLIGHT) ────────────────────────────────
# Runs BEFORE the STARTED announce and BEFORE the model loop, so a missing local
# binary can NEVER be laundered into "ALL MODELS EXHAUSTED / POOL TOO THIN".
# That conflation is the entire defect: four rc=127 legs in under a second read
# as a thin provider pool and enqueued four scorecard BLOCKs against innocent
# models. One loud line with a DISTINCT exit code beats four silent lies.
#
# Exit-code contract (callers/tests depend on these being distinct):
#   0 = a model succeeded   3 = every model in the chain genuinely failed over
#   4 = MISSING LOCAL PREREQ — nothing was attempted, no model is implicated
#
# HARD prereqs are exactly the two binaries this script's one command needs:
# the work client and the `timeout` wrapper that execs it. `git`/`gh` are NOT
# checked here on purpose — this script never shells out to them; fleet-droid.sh
# owns those steps and preflights them itself (wrong layer to duplicate).
PREFLIGHT_MISSING=()
command -v "$OPENCODE_BIN" >/dev/null 2>&1 || PREFLIGHT_MISSING+=("$OPENCODE_BIN")
command -v timeout        >/dev/null 2>&1 || PREFLIGHT_MISSING+=("timeout")
if [ "${#PREFLIGHT_MISSING[@]}" -gt 0 ]; then
  {
    echo "[charon-run] FATAL: required binary not found: ${PREFLIGHT_MISSING[*]}"
    echo "[charon-run]   PATH searched: $PATH"
    echo "[charon-run]   This is a LOCAL ENVIRONMENT fault, NOT model/provider exhaustion."
    echo "[charon-run]   No model was attempted; no scorecard entry was enqueued."
    echo "[charon-run]   Likely cause: launched from a non-login, non-interactive shell that"
    echo "[charon-run]   sourced neither ~/.bashrc nor ~/.profile (so ~/.local/bin is absent)."
    echo "[charon-run]   Fix: install the binary, or set OPENCODE_BIN=/abs/path/to/client."
    echo "CHARON_RUN_RESULT=PREREQ-MISSING missing=${PREFLIGHT_MISSING[*]}"
  } | tee -a "$OUT" >&2
  led "${MODELS[*]}" "prereq-missing" "required binary not found: ${PREFLIGHT_MISSING[*]}; PATH=$PATH; local env fault, NOT model-attributable"
  exit 4
fi
# SOFT prereq: python3 backs the best-effort capture hook (capture/enqueue-capture.sh
# builds its JSON with it). Missing python3 does not stop the WORK, but it silently
# drops every scorecard capture — so say so loudly instead of degrading in silence.
if ! command -v python3 >/dev/null 2>&1; then
  echo "[charon-run] WARN: python3 not on PATH — the scorecard capture hook will silently no-op for this run (work still proceeds)." | tee -a "$OUT" >&2
fi

FIRST_MODEL="${MODELS[0]:-}"
echo "[charon-run] STARTED on charon/$FIRST_MODEL (failover chain: charon/$(IFS=,; echo "${MODELS[*]}"); upstream provider chosen by gateway)" >> "$OUT"
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
  ( cd "$CWD" && timeout "${CHARON_RUN_TIMEOUT_S:-1800}" "$OPENCODE_BIN" run --model "charon/$M" "$PROMPT" ) </dev/null >> "$OUT" 2>&1
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
  if [ "$M" != "$FIRST_MODEL" ]; then _fo=" (failed over from charon/$FIRST_MODEL)"; else _fo=" (primary; no failover)"; fi
  echo "[charon-run] FINISHED on charon/$M — started on charon/$FIRST_MODEL$_fo" >> "$OUT"
  echo "[charon-run] SUCCESS on model '$M' (rc=0)" >> "$OUT"
  echo "CHARON_RUN_RESULT=SUCCESS model=$M" >> "$OUT"
  echo "CHARON_RUN_RESULT_FIRST_MODEL=$FIRST_MODEL" >> "$OUT"
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
