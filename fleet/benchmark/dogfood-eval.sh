#!/usr/bin/env bash
# dogfood-eval.sh — Path C: the dogfood-as-eval loop.
#
# Ranks candidate GATEWAY MODELS by REAL small-ticket outcome under a cheap monitored
# audit. A synthetic benchmark battery (fleet/benchmark/run.sh S0-S6, fleet/benchmark/
# preflight.sh T1-T12) is at best a pre-screen; THIS is the real trust signal — did the
# candidate actually do a real product ticket, end to end, under a latency budget, with
# its diff objectively gradeable.
#
# COMPOSES existing pieces — nothing below reimplements them:
#   - fleet/charon-run.sh          drives the model through the OpenAI-compatible gateway
#                                   (`opencode run --model charon/<M>`), already does
#                                   cross-provider failover + timeout/limit attribution +
#                                   per-attempt wall-time + a diff-state heuristic. This
#                                   script reuses it UNMODIFIED and reads its own log.
#   - git worktree                 isolation: one FRESH worktree per candidate off
#                                   origin/master (repo-registry.sh convention:
#                                   /home/stack/code/charon-fleet-<label>). Never touches
#                                   the primary checkout or master. Never merges.
#   - `charon.cli gate`            the product's own 11-check objective grader (ruff,
#                                   mypy, boundary, version, gate-registry, public-clean,
#                                   no-rig-import, check-arch, security-scan,
#                                   test-patterns, workflow-policy) — repo-registry.sh's
#                                   RR_GATE, run FROM the candidate's own worktree.
#   - a ticket-specific test cmd    (DOGFOOD_TEST_CMD) — the ticket's own accept: check,
#                                   e.g. `PYTHONPATH=src python3 -m pytest tests/foo.py`.
#
# Monitoring discipline (memory: monitored-preflight-failure-attribution): every result
# card carries wall-time, which provider served (best-effort — see charon-run.sh's own
# caveat), and whether real work happened (git-diff-based, stronger than charon-run.sh's
# own mtime heuristic since our worktree IS a real git checkout). Every failure is
# attributed to exactly one of:
#   early-ditch/quality      — ran to completion, exit 0, but the diff is empty/trivial
#                               (the model bailed without doing the work)
#   too-slow                 — charon-run.sh's own timeout (rc=124) with NO pool-exhaustion
#                               signal in opencode's log (latency-is-a-failure-class)
#   provider-degraded->retry — charon-run.sh's own timeout WITH a pool-exhaustion signal
#   provider-throttled->try-another — charon-run.sh's own limit-failover / ALL-EXHAUSTED
# A model is NEVER disqualified for a provider symptom (degraded/throttled) — only for
# early-ditch/quality or too-slow (latency-is-a-failure-class: an intrinsic budget miss
# fails by itself, regardless of correctness).
#
# NEVER auto-merges, NEVER pushes, NEVER lands. Output is a per-candidate REVIEW PACKET
# (result card + saved diff + gate/test logs) for a human to read — pass/fail is a
# strong signal, not an auto-merge trigger.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$(cd "$HERE/.." && pwd)"

# ---- configuration (env-overridable; defaults match repo-registry.sh's `charon` repo) ----
CHARON_RUN="${DOGFOOD_CHARON_RUN:-$FLEET_DIR/charon-run.sh}"
PRODUCT_REPO="${DOGFOOD_PRODUCT_REPO:-/home/stack/code/charon}"
BASE_REF="${DOGFOOD_BASE_REF:-origin/master}"
WORKTREE_PARENT="${DOGFOOD_WORKTREE_PARENT:-/home/stack/code}"   # sibling worktrees: <parent>/charon-fleet-<label>
RESULTS_DIR="${DOGFOOD_RESULTS_DIR:-$FLEET_DIR/state/dogfood-eval/results}"
GATE_CMD="${DOGFOOD_GATE_CMD:-PYTHONPATH=src python3 -m charon.cli gate}"
LATENCY_BUDGET_S="${DOGFOOD_LATENCY_BUDGET_S:-900}"   # per-candidate wall-clock ceiling (15 min default for a D1 ticket)
TEST_CMD="${DOGFOOD_TEST_CMD:-}"                       # ticket-specific accept: check (optional but strongly recommended)
EXPECT_FILES="${DOGFOOD_EXPECT_FILES:-}"               # space-separated list of files the ticket's `owns:` allows touching (advisory scope-check)
KEEP_WORKTREE="${DOGFOOD_KEEP_WORKTREE:-1}"            # 1 = leave worktree in place for human audit (default; nothing auto-deletes)

usage() {
  cat >&2 <<'EOF'
usage: dogfood-eval.sh <ticket-label> <ticket-brief-file> <model1> [model2 ...]

For EACH model given: fresh git worktree off origin/master (product repo) -> run the
model on the ticket brief via charon-run.sh (single-model invocation, so cross-MODEL
failover never masks a candidate's own result; the gateway's own cross-PROVIDER failover
for that one model still applies) -> objectively grade (charon.cli gate + DOGFOOD_TEST_CMD
if given) -> emit a per-candidate result card + saved diff under
fleet/state/dogfood-eval/results/. NEVER commits/merges/pushes the candidate's worktree.
A combined summary table is printed (and saved) after all candidates run.

Env overrides:
  DOGFOOD_TEST_CMD          ticket-specific test command, run inside the worktree
                            (e.g. 'PYTHONPATH=src python3 -m pytest tests/test_x.py -q')
  DOGFOOD_EXPECT_FILES      space-separated glob list the ticket's owns: allows touching
                            (advisory scope-check only; never blocks the run)
  DOGFOOD_LATENCY_BUDGET_S  per-candidate wall-clock ceiling in seconds (default 900)
  DOGFOOD_BASE_REF          worktree base ref (default origin/master)
  DOGFOOD_GATE_CMD          objective grader command, run from the worktree root
                            (default: repo-registry.sh's RR_GATE for the charon repo)
  DOGFOOD_PRODUCT_REPO      repo to worktree off of (default /home/stack/code/charon)
  DOGFOOD_CHARON_RUN        path to charon-run.sh (default: sibling to this script)
EOF
  exit 2
}

[ "$#" -ge 3 ] || usage
TICKET_LABEL="$1"; BRIEF_FILE="$2"; shift 2
MODELS=("$@")

[ -f "$BRIEF_FILE" ] || { echo "dogfood-eval: brief file not found: $BRIEF_FILE" >&2; exit 2; }
[ -x "$CHARON_RUN" ] || { echo "dogfood-eval: charon-run.sh not found/executable at $CHARON_RUN" >&2; exit 2; }
command -v git >/dev/null || { echo "dogfood-eval: git not found" >&2; exit 2; }

mkdir -p "$RESULTS_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SUMMARY_FILE="$RESULTS_DIR/${TICKET_LABEL}-${TS}-SUMMARY.md"
: > "$SUMMARY_FILE"
printf '# Path C dogfood-eval — %s (%s)\n\n' "$TICKET_LABEL" "$TS" >> "$SUMMARY_FILE"
printf '| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |\n' >> "$SUMMARY_FILE"
printf '|---|---|---|---|---|---|---|---|---|---|\n' >> "$SUMMARY_FILE"

git -C "$PRODUCT_REPO" fetch origin --quiet 2>/dev/null || true

# run_one <model>
# Everything about ONE candidate lives here: worktree, run, grade, card. Never merges.
run_one() {
  local model="$1"
  local safe_model
  safe_model="$(printf '%s' "$model" | tr -c 'A-Za-z0-9._-' '-')"
  local label="dogfood-${TICKET_LABEL}-${safe_model}-${TS}"
  local branch="dogfood-eval/${TICKET_LABEL}/${safe_model}-${TS}"
  local wt="${WORKTREE_PARENT}/charon-fleet-${label}"
  local card="$RESULTS_DIR/${label}.card.md"
  local out_log="$RESULTS_DIR/${label}.charon-run.log"
  local gate_log="$RESULTS_DIR/${label}.gate.log"
  local test_log="$RESULTS_DIR/${label}.test.log"
  local diff_file="$RESULTS_DIR/${label}.diff"

  echo "[dogfood-eval] === candidate: $model (ticket=$TICKET_LABEL) ===" >&2
  echo "[dogfood-eval] worktree: $wt  branch: $branch" >&2

  if [ -e "$wt" ]; then
    git -C "$PRODUCT_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  fi
  git -C "$PRODUCT_REPO" worktree prune 2>/dev/null || true
  git -C "$PRODUCT_REPO" branch -D "$branch" 2>/dev/null || true
  if ! git -C "$PRODUCT_REPO" worktree add "$wt" -b "$branch" "$BASE_REF" >/dev/null 2>"$RESULTS_DIR/${label}.worktree-add.err"; then
    echo "[dogfood-eval] FATAL: could not create worktree for $model — see ${label}.worktree-add.err" >&2
    write_card "$card" "$model" "BLOCKED" "worktree-create-failed" "-" "-" "-" "-" "-" "-"
    append_summary "$model" "BLOCKED" "worktree-create-failed" "-" "$LATENCY_BUDGET_S" "-" "-" "-" "-" "$card"
    return
  fi

  # Copy the brief into the worktree so the model can read it (matches charon-run.sh's
  # own contract: <cwd> <outlog> <brief-file> <model...> — brief content is passed as the
  # prompt string; we ALSO drop a copy into the worktree for the model to reference/edit
  # around, consistent with how fleet-droid.sh hands a ticket to a droid).
  cp "$BRIEF_FILE" "$wt/DOGFOOD-TICKET-BRIEF.md"
  # charon-run.sh's real-diff-or-bail mtime heuristic anchors on the brief file's mtime —
  # touch it now so anything the model creates afterward reads as "changed".
  touch "$wt/DOGFOOD-TICKET-BRIEF.md"

  local start_epoch end_epoch elapsed rc
  start_epoch="$(date -u +%s)"
  CHARON_RUN_TIMEOUT_S="$LATENCY_BUDGET_S" "$CHARON_RUN" "$wt" "$out_log" "$wt/DOGFOOD-TICKET-BRIEF.md" "$model"
  rc=$?
  end_epoch="$(date -u +%s)"
  elapsed=$((end_epoch - start_epoch))

  # ---- failure attribution (reuse charon-run.sh's OWN classification lines; never
  # re-derive from scratch) ----
  local attribution="unknown"
  if [ "$rc" -eq 0 ]; then
    attribution="ran-to-completion"
  elif grep -q 'TIMEOUT (rc=124.*CAUSE: gateway pool exhausted' "$out_log" 2>/dev/null; then
    attribution="provider-degraded->retry(pool-exhausted-on-timeout)"
  elif grep -q 'TIMEOUT (rc=124.*too-slow FAIL' "$out_log" 2>/dev/null; then
    attribution="too-slow(latency-budget-exceeded)"
  elif grep -q "hit a provider/session LIMIT" "$out_log" 2>/dev/null; then
    attribution="provider-throttled->try-another(limit-hit)"
  elif grep -q "ALL MODELS EXHAUSTED" "$out_log" 2>/dev/null; then
    attribution="provider-throttled->try-another(all-exhausted)"
  elif grep -q "exited nonzero" "$out_log" 2>/dev/null; then
    attribution="error-nonlimit(rc=$rc; needs human triage, not auto-disqualified as model-quality)"
  fi

  local latency_verdict="within-budget"
  [ "$elapsed" -ge "$LATENCY_BUDGET_S" ] && latency_verdict="BUDGET-EXCEEDED(too-slow-is-a-fail-by-itself)"

  # ---- real-work check: git-diff based (stronger than charon-run.sh's own mtime proxy —
  # our worktree IS a real git checkout) ----
  local diff_stat diff_files n_changed did_real_work
  diff_stat="$(git -C "$wt" diff --stat 2>/dev/null)"
  diff_files="$(git -C "$wt" diff --name-only 2>/dev/null)"
  n_changed="$(printf '%s\n' "$diff_files" | grep -c . || true)"
  git -C "$wt" diff > "$diff_file" 2>/dev/null || true
  if [ "${n_changed:-0}" -gt 0 ]; then
    did_real_work="real-diff(files=$n_changed)"
  else
    did_real_work="early-ditch-no-diff(quality-fail)"
    [ "$rc" -eq 0 ] && attribution="early-ditch/quality(exit0-but-empty-diff)"
  fi

  # ---- scope check (advisory only — never blocks) ----
  local scope_verdict="not-checked(no DOGFOOD_EXPECT_FILES given)"
  if [ -n "$EXPECT_FILES" ]; then
    local unexpected=""
    local f
    while IFS= read -r f; do
      [ -z "$f" ] && continue
      case " $EXPECT_FILES " in
        *" $f "*) ;;
        *) unexpected="$unexpected $f" ;;
      esac
    done <<< "$diff_files"
    if [ -z "$unexpected" ]; then
      scope_verdict="in-scope(matches owns:)"
    else
      scope_verdict="ADVISORY-out-of-scope:$unexpected"
    fi
  fi

  # ---- objective grade: charon.cli gate, run FROM the candidate's own worktree ----
  local gate_verdict="skipped"
  if [ "${n_changed:-0}" -gt 0 ] || [ "$rc" -eq 0 ]; then
    ( cd "$wt" && eval "$GATE_CMD" ) > "$gate_log" 2>&1
    if [ $? -eq 0 ]; then gate_verdict="pass"; else gate_verdict="fail"; fi
  else
    echo "(gate skipped: no diff, nothing to grade)" > "$gate_log"
  fi

  # ---- ticket-specific accept: check ----
  local test_verdict="not-given"
  if [ -n "$TEST_CMD" ]; then
    ( cd "$wt" && eval "$TEST_CMD" ) > "$test_log" 2>&1
    if [ $? -eq 0 ]; then test_verdict="pass"; else test_verdict="fail"; fi
  else
    echo "(no DOGFOOD_TEST_CMD given — ticket-specific accept: check not run)" > "$test_log"
  fi

  # ---- overall verdict (advisory for human review — never an auto-merge signal) ----
  local overall="FIXES-NEEDED"
  if [[ "$attribution" == too-slow* ]]; then
    overall="DETAIN(latency)"
  elif [[ "$attribution" == early-ditch* ]]; then
    overall="DETAIN(quality)"
  elif [[ "$attribution" == provider-*  && "$rc" -ne 0 ]]; then
    overall="RETRY(provider-symptom-not-model-fault)"
  elif [ "$rc" -eq 0 ] && [ "${n_changed:-0}" -gt 0 ] && [ "$gate_verdict" = "pass" ] && { [ "$test_verdict" = "pass" ] || [ "$test_verdict" = "not-given" ]; }; then
    overall="REVIEW-READY(candidate-for-merge; human must still read the diff)"
  fi

  write_card "$card" "$model" "$overall" "$attribution" "$elapsed" "$latency_verdict" "$gate_verdict" "$test_verdict" "$did_real_work" "$scope_verdict" "$diff_stat" "$wt" "$branch" "$out_log" "$gate_log" "$test_log" "$diff_file"
  append_summary "$model" "$overall" "$attribution" "$elapsed" "$LATENCY_BUDGET_S" "$gate_verdict" "$test_verdict" "$did_real_work" "$scope_verdict" "$card"

  echo "[dogfood-eval] candidate $model -> $overall (attribution=$attribution, wall_s=$elapsed, card=$card)" >&2

  if [ "$KEEP_WORKTREE" != "1" ]; then
    git -C "$PRODUCT_REPO" worktree remove --force "$wt" 2>/dev/null || true
  fi
  # NEVER commit/push/merge this worktree's branch — it is left local, unpushed, for audit only.
}

write_card() {
  local card="$1" model="$2" overall="$3" attribution="$4" elapsed="${5:-}" latency_verdict="${6:-}" \
      gate_verdict="${7:-}" test_verdict="${8:-}" did_real_work="${9:-}" scope_verdict="${10:-}" \
      diff_stat="${11:-}" wt="${12:-}" branch="${13:-}" out_log="${14:-}" gate_log="${15:-}" \
      test_log="${16:-}" diff_file="${17:-}"
  {
    printf '# dogfood-eval result card\n\n'
    printf 'candidate: %s\n' "$model"
    printf 'ticket: %s\n' "$TICKET_LABEL"
    printf 'overall verdict: **%s**  (advisory — NEVER auto-merged; a human reads the diff)\n\n' "$overall"
    printf '## monitoring\n'
    printf -- '- wall_time_s: %s   latency_budget_s: %s   latency_verdict: %s\n' "$elapsed" "$LATENCY_BUDGET_S" "$latency_verdict"
    printf -- '- failure attribution: %s\n' "$attribution"
    printf -- '- provider: best-effort unknown-clientside (see charon-run.sh log; gateway alias only, needs gateway-log correlation for real per-provider attribution)\n'
    printf -- '- did-real-work: %s\n\n' "$did_real_work"
    printf '## objective grade\n'
    printf -- '- charon.cli gate: %s (log: %s)\n' "$gate_verdict" "$gate_log"
    printf -- '- ticket accept: check: %s (log: %s)\n\n' "$test_verdict" "$test_log"
    printf '## scope check (advisory only)\n- %s\n\n' "$scope_verdict"
    printf '## diff\n```\n%s\n```\nfull diff: %s\n\n' "$diff_stat" "$diff_file"
    printf '## audit trail\n'
    printf -- '- worktree: %s (left in place, NOT committed/pushed/merged)\n' "$wt"
    printf -- '- local branch: %s (local only)\n' "$branch"
    printf -- '- charon-run.sh log: %s\n' "$out_log"
  } > "$card"
}

append_summary() {
  local model="$1" overall="$2" attribution="$3" elapsed="$4" budget="$5" gate="$6" test_v="$7" diffw="$8" scope="$9" card="${10}"
  printf '| %s | %s | %s | %s | %s | %s | %s | %s | %s | %s |\n' \
    "$model" "$overall" "$attribution" "$elapsed" "$budget" "$gate" "$test_v" "$diffw" "$scope" "$(basename "$card")" >> "$SUMMARY_FILE"
}

for m in "${MODELS[@]}"; do
  run_one "$m"
done

echo >&2
echo "[dogfood-eval] combined summary: $SUMMARY_FILE" >&2
cat "$SUMMARY_FILE" >&2
