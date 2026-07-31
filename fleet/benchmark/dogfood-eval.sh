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
#   too-slow                 — charon-run.sh's own timeout (rc=124) where the model DID
#                               stream real output before the budget killed it (leg was
#                               healthy) — latency-is-a-failure-class, model-attributable
#   leg-fault                — charon-run.sh's own timeout (rc=124) with NO output at all
#                               (a hung/dead leg) — infra symptom, NEVER model-attributable
#   provider-degraded->retry — charon-run.sh's own timeout WITH a pool-exhaustion signal
#   provider-throttled->try-another — a REAL limit-hit/all-exhausted signal (see
#                               lib/dogfood-attribution.sh — local/opaque errors are
#                               checked FIRST so this bucket isn't a catch-all)
#   local-error                — a local/opaque failure (sqlite db-lock, opaque gateway
#                               UnknownError) that is NOT a provider rate-limit; needs
#                               human triage, never silently folded into provider-*
# A model is NEVER disqualified for a provider symptom (degraded/throttled/local-error/
# leg-fault) — only for early-ditch/quality or too-slow (latency-is-a-failure-class: an
# intrinsic budget miss fails by itself, regardless of correctness). EVAL-LATENCY-GATE
# (F4) also adds a wall-clock DETAIN(latency-wallclock) independent of the attribution
# string: elapsed>=LATENCY_BUDGET_S catches a clean rc=0 run that simply ran over budget
# (e.g. glm-5.2 RFL-3: wall=499s > budget=480s) even when no rc=124 marker exists — see
# run_one's overall-verdict block. A trailing provider hiccup on a call made AFTER the
# real diff already graded clean (gate pass + ticket-test pass) is reclassified and
# still counts as REVIEW-READY — see reclassify_trailing_success in lib/dogfood-attribution.sh.
#
# NEVER auto-merges, NEVER pushes, NEVER lands. Output is a per-candidate REVIEW PACKET
# (result card + saved diff + gate/test logs) for a human to read — pass/fail is a
# strong signal, not an auto-merge trigger.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
# shellcheck source=lib/dogfood-attribution.sh
source "$HERE/lib/dogfood-attribution.sh"
# W0b FIX 3: run_one ends in `rm -rf "$wt"` on a path built from $WORKTREE_PARENT + a model-derived
# label with NO guard at all. Reuse the SHARED refusal from W0 (_lg_wt_catastrophic) rather than
# writing a second one. Both libraries are pure (no top-level side effects, neither sources the
# other, neither sources this file) so there is no circular-source risk.
# shellcheck source=/dev/null
# SOURCE ORDER IS NOT SIGNIFICANT. (Corrected 2026-07-19: the previous comment here claimed the
# registry had to be sourced BEFORE leak-guard to "widen _lg_protected_paths". That was FALSE —
# _lg_protected_paths tests `declare -F repo_resolve` at CALL time (leak-guard.sh:156), so both
# orders behave identically. The registry is sourced because repo_valid_id + repo_resolve are
# used below, not because of any ordering dependency. Do NOT introduce one.)
source "$FLEET_DIR/repo-registry.sh"
# shellcheck source=/dev/null
source "$FLEET_DIR/leak-guard.sh"

# ---- configuration (env-overridable; defaults match repo-registry.sh's `charon` repo) ----
CHARON_RUN="${DOGFOOD_CHARON_RUN:-$FLEET_DIR/charon-run.sh}"
PRODUCT_REPO="${DOGFOOD_PRODUCT_REPO:-/home/stack/code/charon}"
BASE_REF="${DOGFOOD_BASE_REF:-origin/master}"
WORKTREE_PARENT="${DOGFOOD_WORKTREE_PARENT:-/home/stack/code}"   # sibling worktrees: <parent>/charon-fleet-<label>
# MED-1: normalised once, up front — every removal target in run_one must resolve UNDER this.
# Same fail-closed ladder as run_one's own resolution (LOW-4): "" rather than an un-normalised path.
WORKTREE_PARENT_REAL="$(cd "$WORKTREE_PARENT" 2>/dev/null && pwd -P)" \
  || WORKTREE_PARENT_REAL="$(realpath -m "$WORKTREE_PARENT" 2>/dev/null)" \
  || WORKTREE_PARENT_REAL=""
RESULTS_DIR="${DOGFOOD_RESULTS_DIR:-$FLEET_DIR/state/dogfood-eval/results}"
GATE_CMD="${DOGFOOD_GATE_CMD:-PYTHONPATH=src python3 -m charon.cli gate}"
LATENCY_BUDGET_S="${DOGFOOD_LATENCY_BUDGET_S:-900}"   # per-candidate wall-clock ceiling (15 min default for a D1 ticket)
TEST_CMD="${DOGFOOD_TEST_CMD:-}"                       # ticket-specific accept: check (optional but strongly recommended)
EXPECT_FILES="${DOGFOOD_EXPECT_FILES:-}"               # space-separated list of files the ticket's `owns:` allows touching (advisory scope-check)
KEEP_WORKTREE="${DOGFOOD_KEEP_WORKTREE:-1}"            # 1 = leave worktree in place for human audit (default; nothing auto-deletes)
# TEST SEAM ONLY. The needs-push marker dir the two safe_worktree_remove/leak_worktree_setup calls
# consult. Overridable so a fixture can plant a REAL marker: the live $FLEET_DIR/state/needs-push
# is empty, which made every needs-push refusal in this suite VACUOUS (the identical vacuity that
# orphaned 32254b3 — see leak-guard.sh:34-38). A guard no test can make fire is a guard no test
# covers. Production never sets this; the default is unchanged.
NEEDS_PUSH_DIR="${DOGFOOD_NEEDS_PUSH_DIR:-$FLEET_DIR/state/needs-push}"

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

# MED-1 (2026-07-19 adversarial review): $TICKET_LABEL is bare-interpolated into $wt below
# ("${WORKTREE_PARENT}/charon-fleet-dogfood-${TICKET_LABEL}-..."), and run_one ends in
# `rm -rf "$wt"`. A label carrying a separator + traversal (e.g. 'x/../../NEIGHBOUR') walked the
# removal target clean OUT of $WORKTREE_PARENT; _lg_wt_catastrophic only refuses PROTECTED trees,
# so an unprotected sibling was silently destroyed with no REFUSING line. Reuse the SSOT charset
# check (repo-registry.sh repo_valid_id) rather than writing a second validator — it is the same
# contract every worktree path in the rig is already held to. Verified against every label the
# sweep actually uses (SECRET-HOTROTATE, PROVIDER-URL-HELPER, RFL-3, ...): none is rejected.
if ! repo_valid_id "$TICKET_LABEL"; then
  echo "dogfood-eval: REFUSING: unsafe ticket label '$TICKET_LABEL' — it is interpolated into a" >&2
  echo "  worktree path that is later rm -rf'd. Allowed: A-Za-z0-9._- , no '/', no '..'." >&2
  exit 2
fi

[ -f "$BRIEF_FILE" ] || { echo "dogfood-eval: brief file not found: $BRIEF_FILE" >&2; exit 2; }
[ -x "$CHARON_RUN" ] || { echo "dogfood-eval: charon-run.sh not found/executable at $CHARON_RUN" >&2; exit 2; }
command -v git >/dev/null || { echo "dogfood-eval: git not found" >&2; exit 2; }

mkdir -p "$RESULTS_DIR"
# TEST HOOK (W0b): DOGFOOD_TS pins the run stamp so a test can know the exact worktree path
# ahead of time and drive the catastrophic-target guard in run_one against a REAL layout.
#
# LOW-5 (2026-07-19 adversarial review): DOGFOOD_TS used to be honoured unconditionally, so a
# stray EXPORTED value in the operator's environment silently pinned the stamp for REAL runs —
# every run would then collide on the same worktree path and overwrite the same SUMMARY file.
# The hook now requires an EXPLICIT test marker, so production cannot be affected by an
# inherited env var: a lone DOGFOOD_TS is ignored (and reported) unless DOGFOOD_TEST_MODE=1.
TS=""
if [ "${DOGFOOD_TEST_MODE:-}" = "1" ] && [ -n "${DOGFOOD_TS:-}" ]; then
  TS="$DOGFOOD_TS"
elif [ -n "${DOGFOOD_TS:-}" ]; then
  echo "[dogfood-eval] IGNORING DOGFOOD_TS='$DOGFOOD_TS' (test hook; needs DOGFOOD_TEST_MODE=1)" >&2
fi
[ -n "$TS" ] || TS="$(date -u +%Y%m%dT%H%M%SZ)"
SUMMARY_FILE="$RESULTS_DIR/${TICKET_LABEL}-${TS}-SUMMARY.md"
: > "$SUMMARY_FILE"
printf '# Path C dogfood-eval — %s (%s)\n\n' "$TICKET_LABEL" "$TS" >> "$SUMMARY_FILE"
printf '| model | verdict | attribution | wall_s | budget_s | gate | ticket-test | diff | scope | card |\n' >> "$SUMMARY_FILE"
printf '|---|---|---|---|---|---|---|---|---|---|\n' >> "$SUMMARY_FILE"

git -C "$PRODUCT_REPO" fetch origin --quiet 2>/dev/null || true

# finalize_live_capture <model> <overall> <ref> <gate_verdict> <test_verdict> <out_log> <card>
# Convert this run's OBJECTIVE grade (charon.cli gate + ticket accept-test — NEVER the
# model's own claimed SUCCESS) into a paired FINAL capture, so a clean run lands a
# source=live/stage=active scorecard row instead of evaporating as a lost provisional.
# The daemon (bench-grader) does the ledger write; we only enqueue to the maildrop spool.
#
# EVAL-PIPELINE-CONSOLIDATE (F12): the SOLE writer of source=live rows is the
# adaptive runner (fleet/benchmark/item-bank/pipeline.py). dogfood-eval no
# longer calls enqueue-capture.sh DIRECTLY — it goes through
# `pipeline.py enqueue-live`, which is the SAME single-capture-path the
# runner uses. This removes the dogfood/preflight/sweep fork: every
# source=live row is now emitted by exactly one Python function
# (`pipeline._enqueue_capture`), and dogfood-eval + the adaptive runner
# both call it. A grep proves no second writer (see pipeline.py's own
# FAIL-ON-REVERT (b) self-test).
#
# SAFETY INVARIANTS (money-path — see charon-run.sh's per-model loop):
#  * Fire ONLY when out_log has CHARON_RUN_RESULT=SUCCESS — the single state where
#    charon-run stored a PROVISIONAL + wrote state/model-used/<ref> and did NOT itself
#    self-finalize a row. This is the double-log guard: charon-run only ever writes a
#    FINAL row on its rc!=0 non-infra BLOCK path (which never emits this marker), and
#    SKIPS logging entirely on provider-limit / infra faults (also no marker). So a
#    SUCCESS marker == exactly one provisional awaiting our FINAL, never a double count.
#  * At SUCCESS (rc==0) `overall` is only ever REVIEW-READY / FIXES-NEEDED / DETAIN — a
#    RETRY verdict requires rc!=0 + a provider/local attribution, so an infra/provider
#    fault is structurally never mapped onto the model here (the Flaw-2 trap).
#  * Verdict is derived from the objective `overall`, not the model's claim; a
#    claimed-SUCCESS that grades FIXES/BLOCK is flagged as a discrepancy (--call-log-report).
finalize_live_capture() {
  local model="$1" overall="$2" ref="$3" gate_v="$4" test_v="$5" out_log="$6" card="$7"
  # Double-log guard: only the true charon-run SUCCESS path (provisional stored,
  # model-used written, no self-finalized row) is eligible.
  grep -q '^CHARON_RUN_RESULT=SUCCESS' "$out_log" 2>/dev/null || return 0
  local v g
  case "$overall" in
    REVIEW-READY*) v=MERGE; g=pass ;;
    FIXES-NEEDED*) v=FIXES; g="$gate_v" ;;
    DETAIN*)       v=BLOCK; g=fail ;;
    *)             return 0 ;;  # RETRY*/BLOCKED*/unknown -> not a model outcome; fail closed
  esac
  # Normalize gate to the daemon's enum (pass|fail); anything else (skipped/not-given)
  # is sent empty (the daemon accepts an empty actual_gate).
  case "$g" in pass|fail) : ;; *) g="" ;; esac
  local score=0; [ "$g" = pass ] && score=100
  # Single-capture-path: route through the runner's enqueue-live subcommand.
  # Pipeline owns the model-scorecard.tsv capture path; dogfood-eval is a
  # client of the pipeline, not a parallel writer. The runner
  # (pipeline.py enqueue-live) calls enqueue-capture.sh on the model's
  # behalf — exactly one place in the codebase calls enqueue-capture.sh
  # for source=live rows. EVAL-PIPELINE-CONSOLIDATE F12.
  local pipeline="$FLEET_DIR/benchmark/item-bank/pipeline.py"
  if [ ! -f "$pipeline" ]; then
    echo "[dogfood-eval] WARN: consolidated pipeline missing at $pipeline; live-lane capture skipped" >&2
    return 0
  fi
  CHARON_JOB_WORK_CLASS="${DOGFOOD_WORK_CLASS:-}" \
    python3 "$pipeline" enqueue-live \
      --model "$model" \
      --work-class "${DOGFOOD_WORK_CLASS:-ci-infra}" \
      --verdict "$v" --gate "$g" --score "$score" \
      --stage active \
      --ref "$ref" \
      --evidence "dogfood-eval OBJECTIVE grade: overall=$overall gate=$gate_v test=$test_v card=$(basename "$card")" \
      >/dev/null 2>&1 \
    && echo "[dogfood-eval] live-lane FINAL routed via pipeline: $model ref=$ref -> verdict=$v gate=${g:-<none>}" >&2 \
    || echo "[dogfood-eval] WARN: live-lane FINAL enqueue via pipeline failed for $model ref=$ref (non-fatal)" >&2
}

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

  # W0b FIX 3: CATASTROPHIC-TARGET GUARD, ahead of BOTH the removal below and the worktree add.
  # Fails CLOSED: an unresolvable/empty path is refused by _lg_wt_catastrophic, and a refusal
  # BLOCKS the candidate rather than falling through to `rm -rf`.
  local dg_real dg_repo dg_why
  # $wt normally does NOT exist yet (the worktree is created below), so `cd`+pwd -P fails and
  # `realpath -m` is the branch that actually runs: it normalises `..` and resolves symlinked
  # parents WITHOUT requiring the path to exist. That normalisation is what makes the CONTAINMENT
  # test below meaningful — an un-normalised path defeats a lexical ancestry comparison.
  #
  # LOW-4 (2026-07-19 adversarial review): the final fallback used to be `dg_real="$wt"`, which
  # FAILED OPEN — without GNU realpath an un-normalised path was handed to the guard and the
  # lexical tests missed it. It now fails CLOSED to "", which _lg_wt_catastrophic (leak-guard.sh:
  # "if [ -z "$real" ]; then echo 'empty path'; return 0") already refuses.
  dg_real="$(cd "$wt" 2>/dev/null && pwd -P)" || dg_real="$(realpath -m "$wt" 2>/dev/null)" || dg_real=""
  dg_repo="$(cd "$PRODUCT_REPO" 2>/dev/null && pwd -P)" || dg_repo=""
  # MED-1 CONTAINMENT (belt and braces alongside the repo_valid_id check on $TICKET_LABEL above):
  # repo_valid_id guards the INPUT; this guards the RESOLVED OUTPUT. Whatever the label, the
  # removal target must land UNDER $WORKTREE_PARENT. _lg_wt_catastrophic alone was not enough —
  # it refuses only PROTECTED trees, so an escape onto an unprotected sibling passed silently.
  # _lg_path_contains returns non-zero when either side is empty, so an unresolvable path refuses.
  if ! _lg_path_contains "$WORKTREE_PARENT_REAL" "$dg_real"; then
    echo "[dogfood-eval] REFUSING: worktree target '$wt' resolves to '${dg_real:-<unresolvable>}'," >&2
    echo "  which escapes the worktree parent '$WORKTREE_PARENT_REAL'" >&2
    write_card "$card" "$model" "BLOCKED" "worktree-target-escapes-parent" "-" "-" "-" "-" "-" "-"
    append_summary "$model" "BLOCKED" "worktree-target-escapes-parent" "-" "$LATENCY_BUDGET_S" "-" "-" "-" "-" "$card"
    return
  fi
  if dg_why="$(_lg_wt_catastrophic "$dg_real" "$dg_repo")"; then
    echo "[dogfood-eval] REFUSING: worktree target '$wt' is catastrophic — $dg_why" >&2
    write_card "$card" "$model" "BLOCKED" "catastrophic-worktree-target" "-" "-" "-" "-" "-" "-"
    append_summary "$model" "BLOCKED" "catastrophic-worktree-target" "-" "$LATENCY_BUDGET_S" "-" "-" "-" "-" "$card"
    return
  fi
  # DOGFOOD-EVAL-GUARD (2026-07-19 adversarial review): the two lines that used to sit here were
  # the last known UNGUARDED destruction path on the rig:
  #     git -C "$PRODUCT_REPO" worktree remove --force "$wt" 2>/dev/null || rm -rf "$wt"
  #     git -C "$PRODUCT_REPO" branch -D "$branch" 2>/dev/null || true
  # against the LIVE PRODUCT CHECKOUT. No dirty-tree check, no unpushed-commit check, and a
  # `|| rm -rf` fallback that turned every refusal of the safe path into the unsafe one. The
  # `branch -D` is the same shape that orphaned reviewed commit 32254b3 (leak-guard.sh:34-52) —
  # -D destroys unmerged commits AND erases .git/logs/refs/heads/<branch>, taking attribution
  # with it. `2>/dev/null || true` then hid both the act and the reason.
  #
  # REUSE, not a third variant: leak-guard.sh already owns this exact sequence.
  #   * safe_worktree_remove — needs-push marker check + _lg_wt_target_ok (catastrophic target,
  #     uncommitted changes, commits not on any remote), and an `rm -rf` fallback that only runs
  #     on a path git itself confirms is a non-primary worktree of THIS repo.
  #   * leak_worktree_setup — the unlanded-commit guard with the salvage-tag-then-REFUSE pattern
  #     (rc 3), the needs-push refusal (rc 2), reflog archival before deletion, and `branch -d`
  #     first with `-D` only as a fallback AFTER the guard has POSITIVELY proven 0 unlanded
  #     commits. It then creates the worktree. A second copy of this logic here would drift from
  #     that one, and the seam between two guards that must agree is where committed work dies.
  #
  # TERMINAL REFUSALS (fleet/retire-done.sh:74-77 shape): every refusal below BLOCKS the
  # candidate and leaves the target untouched. There is deliberately no `else`/`||` branch that
  # destroys anything — a guard whose refusal path triggers the destroy is a TRIGGER, not a
  # guard (the fleet-droid.sh bug reproduced today). Refusal reasons go to stderr UNSWALLOWED.
  local NPDIR="$NEEDS_PUSH_DIR"
  if [ -e "$wt" ]; then
    # $wt carries a run-unique $TS, so a pre-existing path here is anomalous, not a retry —
    # judge it on its real state rather than recycling it blind. Refusal is fail-closed: an
    # unreadable/unregistered/dirty/unpushed target keeps its contents and blocks the candidate.
    if ! safe_worktree_remove "$PRODUCT_REPO" "$wt" "$label" "$NPDIR"; then
      echo "[dogfood-eval] REFUSING: pre-existing worktree '$wt' was NOT removed (see leak-guard reason above)." >&2
      echo "  Candidate '$model' is BLOCKED; nothing was deleted. Resolve that tree by hand." >&2
      write_card "$card" "$model" "BLOCKED" "stale-worktree-removal-refused" "-" "-" "-" "-" "-" "-"
      append_summary "$model" "BLOCKED" "stale-worktree-removal-refused" "-" "$LATENCY_BUDGET_S" "-" "-" "-" "-" "$card"
      return
    fi
  fi
  git -C "$PRODUCT_REPO" worktree prune 2>/dev/null || true
  # Branch delete + worktree create, both under leak-guard's unlanded-work guard.
  local lws_rc=0
  leak_worktree_setup "$PRODUCT_REPO" "$wt" "$branch" "$NPDIR/$label" "$BASE_REF" || lws_rc=$?
  if [ "$lws_rc" -ne 0 ]; then
    local lws_why
    case "$lws_rc" in
      2) lws_why="branch-setup-refused-needs-push" ;;
      3) lws_why="branch-setup-refused-unlanded-commits(salvage-tagged)" ;;
      *) lws_why="worktree-create-failed" ;;
    esac
    echo "[dogfood-eval] FATAL: worktree/branch setup for $model did not complete — $lws_why (rc=$lws_rc)." >&2
    echo "  Branch '$branch' was NOT force-deleted. See the leak-guard lines above for the reason." >&2
    write_card "$card" "$model" "BLOCKED" "$lws_why" "-" "-" "-" "-" "-" "-"
    append_summary "$model" "BLOCKED" "$lws_why" "-" "$LATENCY_BUDGET_S" "-" "-" "-" "-" "$card"
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
  # CHARON_JOB_REF: pin the capture ref to this candidate's unique label so the
  # provisional charon-run stores (on success) and the FINAL finalize_live_capture
  # enqueues below pair on the SAME ref (and state/model-used/<ref> confirms it).
  # CHARON_JOB_WORK_CLASS: the daemon takes a paired FINAL's work_class from the
  # STORED PROVISIONAL (grader-daemon._handle_capture), so the class must ride on the
  # provisional charon-run enqueues here — a --work-class on the FINAL alone is ignored.
  # Unset -> daemon defaults to ci-infra.
  CHARON_JOB_REF="$label" CHARON_JOB_WORK_CLASS="${DOGFOOD_WORK_CLASS:-}" \
    CHARON_RUN_TIMEOUT_S="$LATENCY_BUDGET_S" "$CHARON_RUN" "$wt" "$out_log" "$wt/DOGFOOD-TICKET-BRIEF.md" "$model"
  rc=$?
  end_epoch="$(date -u +%s)"
  elapsed=$((end_epoch - start_epoch))

  # ---- failure attribution (lib/dogfood-attribution.sh; never re-derive inline —
  # see that file for the mislabel bug this classifier fixes) ----
  local attribution
  attribution="$(classify_attribution "$rc" "$out_log")"

  local latency_verdict="within-budget"
  [ "$elapsed" -ge "$LATENCY_BUDGET_S" ] && latency_verdict="BUDGET-EXCEEDED(too-slow-is-a-fail-by-itself)"

  # ---- real-work check: git-diff based (stronger than charon-run.sh's own mtime proxy —
  # our worktree IS a real git checkout) ----
  #
  # RFL-3-CAPTURE-FIX: git diff covers ONLY tracked changes. A candidate that creates a
  # genuinely NEW untracked file (created, never git-add'd) leaves output that is invisible
  # to git diff, invisible to the scorer, and permanently lost on worktree reap. Capture
  # untracked files too — they are first-class candidate output. Use `git ls-files --others
  # --exclude-standard` (read-only, no index mutation; unlike `git add -N`) and append each
  # as a proper diff via `git diff --no-index /dev/null <file>`.
  local diff_stat diff_files n_changed did_real_work
  diff_stat="$(git -C "$wt" diff --stat 2>/dev/null)"
  diff_files="$(git -C "$wt" diff --name-only 2>/dev/null)"

  local untracked_files n_untracked
  untracked_files="$(git -C "$wt" ls-files --others --exclude-standard 2>/dev/null)"
  n_untracked="$(printf '%s\n' "$untracked_files" | grep -c . || true)"

  git -C "$wt" diff > "$diff_file" 2>/dev/null || true

  if [ "${n_untracked:-0}" -gt 0 ]; then
    while IFS= read -r uf; do
      [ -z "$uf" ] && continue
      git -C "$wt" diff --no-index /dev/null "$uf" >> "$diff_file" 2>/dev/null || \
        { printf '%s\n' '--- /dev/null' "+++ $uf (unreadable)" >> "$diff_file"; }
    done <<< "$untracked_files"
  fi

  diff_files="$(printf '%s\n%s\n' "$diff_files" "$untracked_files" | grep . || true)"
  n_changed="$(printf '%s\n' "$diff_files" | grep -c . || true)"
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

  # ---- reclassify a trailing provider hiccup AFTER the real work already graded clean
  # (lib/dogfood-attribution.sh) — must run AFTER gate_verdict/test_verdict exist ----
  attribution="$(reclassify_trailing_success "$attribution" "$rc" "${n_changed:-0}" "$gate_verdict" "$test_verdict")"

  # ---- overall verdict (advisory for human review — never an auto-merge signal) ----
  # Order matters: an intrinsic quality/latency fail always wins (early-ditch/too-slow);
  # otherwise a real diff that graded clean on BOTH the objective gate and the ticket's
  # own accept-test is REVIEW-READY regardless of rc — this is what makes the trailing-
  # provider-hiccup-after-success case (deepseek-v4-flash/kimi-k2.6 on TOOL-REPAIR-
  # MUTATING) land correctly instead of as a false RETRY/provider-symptom. Only after
  # that do we fall back to a genuine provider symptom or a local/opaque error (neither
  # of which disqualifies the model — it's a RETRY, not a FIXES-NEEDED).
  local overall="FIXES-NEEDED"
  if [[ "$attribution" == too-slow* ]]; then
    overall="DETAIN(latency)"
  elif [[ "$attribution" == early-ditch* ]]; then
    overall="DETAIN(quality)"
  elif [[ "$attribution" == leg-fault* ]]; then
    # EVAL-LATENCY-GATE (F1/F4): rc=124 with NO output before the `timeout` wrapper
    # killed it -- a hung/dead leg, never the model's fault. Park the leg (RETRY),
    # NEVER a model BLOCK/DETAIN -- must be checked BEFORE the wall-clock elif below,
    # since a leg-fault also hits elapsed>=budget (the wrapper fires at the budget
    # regardless of whether the leg produced output) and would otherwise be
    # wrongly swept into DETAIN(latency-wallclock).
    overall="RETRY(leg-fault-not-model-fault; park-leg-not-model)"
  elif [ "$elapsed" -ge "$LATENCY_BUDGET_S" ]; then
    # EVAL-LATENCY-GATE (F4): wall-clock safety net, independent of the attribution
    # string -- a run that streamed past budget and STILL exited 0 (e.g. glm-5.2
    # RFL-3: wall=499s > budget=480s, attribution=ran-to-completion) must not slip
    # through as REVIEW-READY just because no rc=124/string-based attribution fired.
    # Never reached for the too-slow/early-ditch/leg-fault buckets above (already
    # returned by then).
    overall="DETAIN(latency-wallclock)"
  elif [ "${n_changed:-0}" -gt 0 ] && [ "$gate_verdict" = "pass" ] && { [ "$test_verdict" = "pass" ] || [ "$test_verdict" = "not-given" ]; }; then
    overall="REVIEW-READY(candidate-for-merge; human must still read the diff)"
  elif [[ "$attribution" == provider-*  && "$rc" -ne 0 ]]; then
    overall="RETRY(provider-symptom-not-model-fault)"
  elif [[ "$attribution" == local-error* ]]; then
    overall="RETRY(local-error-not-model-fault; needs human triage)"
  fi

  write_card "$card" "$model" "$overall" "$attribution" "$elapsed" "$latency_verdict" "$gate_verdict" "$test_verdict" "$did_real_work" "$scope_verdict" "$diff_stat" "$wt" "$branch" "$out_log" "$gate_log" "$test_log" "$diff_file"
  append_summary "$model" "$overall" "$attribution" "$elapsed" "$LATENCY_BUDGET_S" "$gate_verdict" "$test_verdict" "$did_real_work" "$scope_verdict" "$card"
  # Close the live-lane loop: objective grade -> paired FINAL capture -> daemon writes a
  # source=live/stage=active scorecard row (guarded; see finalize_live_capture header).
  finalize_live_capture "$model" "$overall" "$label" "$gate_verdict" "$test_verdict" "$out_log" "$card"

  echo "[dogfood-eval] candidate $model -> $overall (attribution=$attribution, wall_s=$elapsed, card=$card)" >&2

  # DOGFOOD-EVAL-GUARD: this was `worktree remove --force "$wt" 2>/dev/null || true`. --force
  # destroys uncommitted work exactly as thoroughly as `rm -rf`, and NOTHING in this script ever
  # commits the candidate's work — the model's entire output lives here as uncommitted changes.
  # $diff_file only captures `git diff` (TRACKED files), so a candidate that created NEW files
  # had them deleted with no copy anywhere. `2>/dev/null || true` made that silent.
  #
  # Routed through the same safe_worktree_remove as above: it removes a genuinely clean,
  # fully-pushed, provably-ours worktree (the early-ditch/no-diff case — so this is NOT a guard
  # that keeps everything), and REFUSES a tree still holding uncommitted or unremoted work,
  # leaving it on disk. No `|| rm -rf` fallback: DOGFOOD_KEEP_WORKTREE=1 (the default) is the
  # supported way to keep worktrees; there is no supported way to force-destroy live work.
  if [ "$KEEP_WORKTREE" != "1" ]; then
    # Drop the ONE file this script itself planted in the worktree, so its own scaffolding does
    # not read as candidate work and permanently over-block the clean/early-ditch case. This is
    # a named single file we created three steps up, NOT a `git clean` and NOT a guard bypass —
    # anything else in the tree still makes the removal below refuse.
    #
    # BY CONTENT, NOT BY NAME (adversarial review F4). `rm -f` on the path alone deleted whatever
    # was at that name — and a model handed a brief may write its plan, notes or answer INTO that
    # brief. The file is UNTRACKED, so $diff_file (`git diff`, tracked only) holds no copy and the
    # deletion is unrecoverable: precisely the failure class this whole commit exists to close.
    # So: remove it only while it is byte-identical to the pristine copy we planted three steps up
    # (the `touch` above changes mtime, not bytes, so cmp still matches). If it DIFFERS the
    # candidate wrote to it — keep it, and let the dirty check in _lg_wt_target_ok refuse the
    # removal below, exactly as it would for any other candidate output.
    if cmp -s "$wt/DOGFOOD-TICKET-BRIEF.md" "$BRIEF_FILE"; then
      rm -f "$wt/DOGFOOD-TICKET-BRIEF.md"
    fi
    if safe_worktree_remove "$PRODUCT_REPO" "$wt" "$label" "$NPDIR"; then
      echo "[dogfood-eval] worktree removed (clean): $wt" >&2
    else
      echo "[dogfood-eval] worktree KEPT: $wt — removal refused (reason above); it still holds work." >&2
    fi
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
