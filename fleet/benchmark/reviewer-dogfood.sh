#!/usr/bin/env bash
# reviewer-dogfood.sh — REVIEWER-DOGFOOD-REDS: the reds-replay eval for the REVIEWER
# job (today done by Claude Code — our single biggest Claude-cost lever). The reviewer
# is the LAST tier to hand off and the HIGHEST-stakes: a bad reviewer silently passes
# broken money-path code. Its quality CANNOT be graded by `charon.cli gate` (that grades
# WORKER output). You grade a reviewer by whether it CATCHES known real bugs —
# reds-replay, the same real-work-is-the-trust-test discipline as Path C
# (dogfood-eval.sh), NOT a synthetic battery. See ticket
# fleet/board/REVIEWER-DOGFOOD-REDS.md and ground truth fleet/state/REDS-CORPUS.md.
#
# PART 1 (corpus) lives in REDS-CORPUS.md — real caught-bug commits, ground truth held
# OUT of any prompt sent to a candidate (see that file's "OOB design note": a reviewer
# candidate here gets ONLY diff TEXT over the gateway, never filesystem/worktree access,
# which is a stronger isolation boundary than the preflight battery's 0700 keys).
#
# PART 2 (this harness): for each candidate model x each corpus case, compute the REAL
# defect-introducing diff live from git history (`git diff <good_ref> <bad_ref> --
# <paths>` — never a hand-copied blob, so a case can't silently drift from the commit it
# claims), feed it through the gateway (charon/<model>) via charon-run.sh (REUSED
# UNMODIFIED — same monitored dispatch Path C uses), capture the candidate's own review
# text, and OOB-grade recall (did it name the file + defect-concept keywords) and
# precision (did it invent a defect on the one clean/known-good diff). Reuses
# lib/dogfood-attribution.sh for provider/infra failure attribution (a gateway hiccup
# never counts against a candidate) and enforces latency-is-a-failure-class (a candidate
# too slow to review inside budget fails by that alone, independent of the text).
#
# PART 3 (verdict + promotion): PROMOTE-CANDIDATE only on recall >= threshold (default
# 100% of this small, all-real corpus) AND zero false positives on the clean set.
# NEVER auto-merges, edits fleet/tier-models.tsv, or writes model-scorecard.tsv directly
# (that ledger is bench-grader-owned) — generates a runnable scorecard-append script,
# same convention as fleet/benchmark/dogfood-to-scorecard.sh, for a human to run. Favor a
# multi-model voting PANEL over any single passer; keep Claude as the escalation for
# high-blast-radius / money-path review regardless of a pass here (a fixed replay proves
# recall on KNOWN cases, not safety on an unseen one).
#
# Usage:
#   reviewer-dogfood.sh <model1> [model2 ...]          # live run against the gateway
#   reviewer-dogfood.sh --corpus-selfcheck [corpus.md]  # offline: prove every case's
#                                                        # diff is real/non-empty (no
#                                                        # gateway call, no model)
#   reviewer-dogfood.sh --grade <case_id> <review_text_file> [corpus.md]
#                                                        # offline: OOB-grade one
#                                                        # candidate response against
#                                                        # one case's ground truth
#
# NEVER commits/pushes/merges. NEVER trusts a candidate's own self-report — grading is
# 100% deterministic keyword/file-anchored matching over its OWN emitted text, done by
# code no candidate's prompt ever sees.
set -uo pipefail

HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
FLEET_DIR="$(cd "$HERE/.." && pwd)"
RIG_REPO="$(cd "$FLEET_DIR/.." && pwd)"
# shellcheck source=lib/dogfood-attribution.sh
source "$HERE/lib/dogfood-attribution.sh"

CORPUS="${REVIEWER_CORPUS:-$FLEET_DIR/state/REDS-CORPUS.md}"
CHARON_RUN="${REVIEWER_CHARON_RUN:-$FLEET_DIR/charon-run.sh}"
PRODUCT_REPO="${REVIEWER_PRODUCT_REPO:-/home/stack/code/charon}"
RESULTS_DIR="${REVIEWER_RESULTS_DIR:-$FLEET_DIR/state/dogfood-eval/reviewer-results}"
LATENCY_BUDGET_S="${REVIEWER_LATENCY_BUDGET_S:-300}"
RECALL_THRESHOLD="${REVIEWER_RECALL_THRESHOLD:-1.0}"   # tiny all-real seed corpus: must catch EVERY case
ALLOW_FP="${REVIEWER_ALLOW_FP:-0}"                     # false positives tolerated on the clean set

die() { echo "reviewer-dogfood: ERROR: $*" >&2; exit 2; }

usage() {
  sed -n '2,/^set -uo pipefail/p' "${BASH_SOURCE[0]}" | sed 's/^# \{0,1\}//'
  exit 2
}

# ---- corpus parsing (fleet/state/REDS-CORPUS.md's embedded ```tsv block```) ----------
# parse_corpus <corpus_file> -> prints one TAB-separated row per case (comments/header
# stripped): id repo good_ref bad_ref paths defect_class keywords
parse_corpus() {
  local corpus="$1"
  awk '
    /^```tsv$/ { in_block=1; next }
    /^```$/    { if (in_block) { in_block=0 }; next }
    in_block && !/^#/ && NF>0 { print }
  ' "$corpus"
}

# clean_diff <corpus_file> -> prints the literal embedded CLEAN0 diff text
clean_diff() {
  local corpus="$1"
  awk '
    /^DIFF:CLEAN0-START$/ { in_block=1; next }
    /^DIFF:CLEAN0-END$/   { in_block=0; next }
    in_block { print }
  ' "$corpus"
}

# case_diff <case_row (one TSV line)> -> prints the real diff text for a RED case,
# computed LIVE from git history. Empty output (with a stderr note) means the corpus
# reference is broken — caller must treat that as a hard failure, never a silent skip
# (NON-VACUOUS: a case that produces nothing was never actually replayed).
case_diff() {
  local row="$1"
  local repo good_ref bad_ref paths
  IFS=$'\t' read -r _id repo good_ref bad_ref paths _defect _kw <<< "$row"
  local repo_path
  case "$repo" in
    product) repo_path="$PRODUCT_REPO" ;;
    rig)     repo_path="$RIG_REPO" ;;
    *) echo "reviewer-dogfood: unknown repo tag '$repo' in corpus row: $row" >&2; return 1 ;;
  esac
  # NOTE: a git WORKTREE's ".git" is a file (gitdir pointer), not a directory — use
  # rev-parse so this works from a worktree checkout, not just a primary clone.
  git -C "$repo_path" rev-parse --git-dir >/dev/null 2>&1 || { echo "reviewer-dogfood: repo not found: $repo_path (tag=$repo)" >&2; return 1; }
  # shellcheck disable=SC2086
  git -C "$repo_path" diff "$good_ref" "$bad_ref" -- $paths 2>/dev/null
}

# ---- OOB grading (deterministic, no LLM judge, ground truth never sent to a model) ---
# grade_recall <case_row> <review_text_file> -> prints CAUGHT|MISSED, rc 0 if CAUGHT
grade_recall() {
  local row="$1" review_file="$2"
  local paths keywords
  IFS=$'\t' read -r _id _repo _good _bad paths _defect keywords <<< "$row"
  [ -s "$review_file" ] || { echo "MISSED"; return 1; }
  local p file_hit=0
  for p in $paths; do
    local base; base="$(basename "$p")"
    if grep -qiF "$base" "$review_file"; then file_hit=1; break; fi
  done
  [ "$file_hit" -eq 1 ] || { echo "MISSED"; return 1; }
  if grep -qiE "$keywords" "$review_file"; then
    echo "CAUGHT"; return 0
  fi
  echo "MISSED"; return 1
}

# grade_precision <review_text_file> -> prints CLEAN|FALSE-POSITIVE, rc 0 if CLEAN
FP_LANGUAGE='bug|vulnerability|race condition|security issue|incorrect|broken|flaw|blocker|reject'
grade_precision() {
  local review_file="$1"
  [ -s "$review_file" ] || { echo "FALSE-POSITIVE"; return 1; }
  if grep -qiE "$FP_LANGUAGE" "$review_file"; then
    echo "FALSE-POSITIVE"; return 1
  fi
  echo "CLEAN"; return 0
}

# ---- adversarial-review prompt (standard, model-agnostic) ---------------------------
build_prompt() {
  local diff_file="$1" out_file="$2"
  {
    printf '%s\n' \
      'You are the REVIEWER on a code change about to merge, not its author.' \
      'Review the diff below adversarially: think about what edge cases fail, what' \
      'race conditions or concurrency bugs exist, what security/supply-chain properties' \
      'are violated, what invariants the change breaks, and whether a stated goal in the' \
      'commit message (e.g. "fix the gate", "make CI green") is actually a cover for a' \
      'regression elsewhere. A bad review here can silently pass broken money-path code.' \
      '' \
      'Reply with: (1) a clear verdict (APPROVE or REJECT/CONCERN), (2) if you REJECT or' \
      'have a CONCERN, name the exact file and the concrete defect — do not just say' \
      '"looks risky" in general terms. If you find no real issue, say so plainly.' \
      '' \
      '--- DIFF UNDER REVIEW ---'
    cat "$diff_file"
  } > "$out_file"
}

# ============================ offline entry points ====================================
if [ "${1:-}" = "--corpus-selfcheck" ]; then
  corpus="${2:-$CORPUS}"
  [ -f "$corpus" ] || die "corpus not found: $corpus"
  fail=0
  n=0
  while IFS= read -r row; do
    [ -z "$row" ] && continue
    n=$((n + 1))
    id="$(printf '%s' "$row" | cut -f1)"
    diff_text="$(case_diff "$row")"
    if [ -z "$diff_text" ]; then
      echo "FAIL: $id — git diff produced NOTHING (broken good_ref/bad_ref/paths, or repo missing)" >&2
      fail=1
    else
      lines="$(printf '%s\n' "$diff_text" | wc -l)"
      echo "OK: $id — real diff, $lines line(s)"
    fi
  done < <(parse_corpus "$corpus")
  clean_text="$(clean_diff "$corpus")"
  n=$((n + 1))
  if [ -z "$clean_text" ]; then
    echo "FAIL: CLEAN0 — embedded clean diff is empty" >&2
    fail=1
  else
    echo "OK: CLEAN0 — embedded clean diff present"
  fi
  # NON-VACUOUS: a corpus that parses to zero cases must FAIL, never pass "trivially".
  if [ "$n" -le 1 ]; then
    echo "FAIL: corpus parsed to $n case(s) — expected the seed red cases + CLEAN0 (empty/broken parse is not a pass)" >&2
    fail=1
  fi
  [ "$fail" -eq 0 ] && { echo "corpus-selfcheck: OK ($n case(s))"; exit 0; }
  echo "corpus-selfcheck: FAILED" >&2
  exit 1
fi

if [ "${1:-}" = "--grade" ]; then
  case_id="${2:-}"; review_file="${3:-}"; corpus="${4:-$CORPUS}"
  [ -n "$case_id" ] && [ -n "$review_file" ] || usage
  [ -f "$corpus" ] || die "corpus not found: $corpus"
  if [ "$case_id" = "CLEAN0" ]; then
    grade_precision "$review_file"
    exit $?
  fi
  row="$(parse_corpus "$corpus" | awk -F'\t' -v id="$case_id" '$1==id')"
  [ -n "$row" ] || die "unknown case id: $case_id"
  grade_recall "$row" "$review_file"
  exit $?
fi

# ============================== live run (default) ===================================
[ "$#" -ge 1 ] || usage
MODELS=("$@")

[ -f "$CORPUS" ] || die "corpus not found: $CORPUS"
[ -x "$CHARON_RUN" ] || die "charon-run.sh not found/executable at $CHARON_RUN"
command -v git >/dev/null || die "git not found"

mkdir -p "$RESULTS_DIR"
TS="$(date -u +%Y%m%dT%H%M%SZ)"
SUMMARY="$RESULTS_DIR/reviewer-dogfood-${TS}-SUMMARY.md"
: > "$SUMMARY"
{
  printf '# REVIEWER-DOGFOOD-REDS replay — %s\n\n' "$TS"
  printf '| model | recall | precision | caught/total | fp | verdict | note |\n'
  printf '|---|---|---|---|---|---|---|\n'
} >> "$SUMMARY"

CASES="$(parse_corpus "$CORPUS")"
[ -n "$CASES" ] || die "corpus parsed to zero cases — refusing to run a vacuous eval"

SCORECARD_SCRIPT="$FLEET_DIR/state/scorecard-append-reviewer-${TS}.sh"
: > "$SCORECARD_SCRIPT"
{
  echo "#!/usr/bin/env bash"
  echo "# GENERATED by reviewer-dogfood.sh from $SUMMARY on $(date -u +%F) (UTC)."
  echo "# model-scorecard.tsv is bench-grader-owned; run this AS that user:"
  echo "#   sudo -u bench-grader bash $SCORECARD_SCRIPT"
  echo "# stage=provisional (a REVIEWER-tier pass is a RECOMMENDATION, never auto-"
  echo "# promoted — see REDS-CORPUS.md PART 3: favor a panel, keep Claude as the"
  echo "# money-path escalation regardless of this replay's verdict)."
  echo "set -euo pipefail"
  echo "S=$FLEET_DIR/model-scorecard.sh"
  echo "export CHARON_SCORECARD_STAGE=provisional"
  echo
} >> "$SCORECARD_SCRIPT"

for model in "${MODELS[@]}"; do
  safe_model="$(printf '%s' "$model" | tr -c 'A-Za-z0-9._-' '-')"
  echo "[reviewer-dogfood] === candidate: $model ===" >&2
  caught=0 total=0 skipped=0 fp=0 sum_wall=0

  while IFS= read -r row; do
    [ -z "$row" ] && continue
    id="$(printf '%s' "$row" | cut -f1)"
    total=$((total + 1))
    diff_text="$(case_diff "$row")"
    if [ -z "$diff_text" ]; then
      echo "  $id: FATAL — corpus reference broken (see --corpus-selfcheck)" >&2
      exit 2
    fi
    diff_file="$RESULTS_DIR/${safe_model}-${id}-${TS}.diff"
    prompt_file="$RESULTS_DIR/${safe_model}-${id}-${TS}.prompt.md"
    out_log="$RESULTS_DIR/${safe_model}-${id}-${TS}.out.log"
    printf '%s\n' "$diff_text" > "$diff_file"
    build_prompt "$diff_file" "$prompt_file"

    scratch="$(mktemp -d)"
    start_epoch="$(date -u +%s)"
    CHARON_RUN_TIMEOUT_S="$LATENCY_BUDGET_S" "$CHARON_RUN" "$scratch" "$out_log" "$prompt_file" "$model"
    rc=$?
    end_epoch="$(date -u +%s)"
    wall=$((end_epoch - start_epoch))
    rm -rf "$scratch"
    sum_wall=$((sum_wall + wall))

    attribution="$(classify_attribution "$rc" "$out_log")"
    # latency-is-a-failure-class: an intrinsic budget miss overrides any other
    # attribution the log-classifier guessed at — too slow fails by itself.
    if [ "$wall" -ge "$LATENCY_BUDGET_S" ]; then
      attribution="too-slow(latency-budget-exceeded:${wall}s>=${LATENCY_BUDGET_S}s)"
    fi

    case "$attribution" in
      provider-*|local-error*)
        echo "  $id: SKIPPED (provider/infra symptom: $attribution — not counted against the model)" >&2
        skipped=$((skipped + 1))
        continue
        ;;
      too-slow*)
        echo "  $id: MISSED (too-slow: $attribution)" >&2
        continue
        ;;
    esac

    verdict="$(grade_recall "$row" "$out_log")"
    if [ "$verdict" = "CAUGHT" ]; then
      caught=$((caught + 1))
      echo "  $id: CAUGHT (${wall}s)" >&2
    else
      echo "  $id: MISSED (${wall}s)" >&2
    fi
  done <<< "$CASES"

  # ---- clean/precision probe ----
  clean_text="$(clean_diff "$CORPUS")"
  diff_file="$RESULTS_DIR/${safe_model}-CLEAN0-${TS}.diff"
  prompt_file="$RESULTS_DIR/${safe_model}-CLEAN0-${TS}.prompt.md"
  out_log="$RESULTS_DIR/${safe_model}-CLEAN0-${TS}.out.log"
  printf '%s\n' "$clean_text" > "$diff_file"
  build_prompt "$diff_file" "$prompt_file"
  scratch="$(mktemp -d)"
  CHARON_RUN_TIMEOUT_S="$LATENCY_BUDGET_S" "$CHARON_RUN" "$scratch" "$out_log" "$prompt_file" "$model"
  rc=$?
  rm -rf "$scratch"
  attribution="$(classify_attribution "$rc" "$out_log")"
  case "$attribution" in
    provider-*|local-error*)
      echo "  CLEAN0: SKIPPED (provider/infra symptom: $attribution)" >&2
      precision_note="skipped(infra)"
      ;;
    *)
      pverdict="$(grade_precision "$out_log")"
      if [ "$pverdict" = "FALSE-POSITIVE" ]; then
        fp=1
        echo "  CLEAN0: FALSE-POSITIVE" >&2
      else
        echo "  CLEAN0: CLEAN" >&2
      fi
      precision_note="$pverdict"
      ;;
  esac

  attempted=$((total - skipped))
  recall="0.00"
  [ "$attempted" -gt 0 ] && recall="$(awk -v c="$caught" -v t="$attempted" 'BEGIN{printf "%.2f", c/t}')"
  precision_ok=1
  [ "$fp" -eq 1 ] && [ "$ALLOW_FP" -eq 0 ] && precision_ok=0

  pass_recall=0
  awk -v r="$recall" -v thr="$RECALL_THRESHOLD" 'BEGIN{exit !(r+0 >= thr+0)}' && pass_recall=1

  if [ "$pass_recall" -eq 1 ] && [ "$precision_ok" -eq 1 ]; then
    verdict="PROMOTE-CANDIDATE(favor-panel-not-solo;claude-stays-escalation-for-money-path)"
    score=100
    sc_verdict="MERGE"
  else
    verdict="NOT-YET(recall=${recall}<${RECALL_THRESHOLD}-or-false-positive)"
    score="$(awk -v r="$recall" 'BEGIN{printf "%d", r*100}')"
    sc_verdict="BLOCK"
  fi

  note="reviewer-dogfood-reds caught=${caught}/${attempted} skipped=${skipped} fp=${fp}"
  printf '| %s | %s | %s | %s/%s | %s | %s | %s |\n' \
    "$model" "$recall" "$precision_note" "$caught" "$attempted" "$fp" "$verdict" "$note" >> "$SUMMARY"

  avg_wall="-"
  [ "$total" -gt 0 ] && avg_wall="$(awk -v s="$sum_wall" -v n="$total" 'BEGIN{printf "%.0f", s/n}')"
  note_safe="$(printf '%s' "$note" | tr '\t' ' ')"
  printf '"$S" append %s live REVIEWER-DOGFOOD-REDS tests - %s %s - %s %s - 0 %s\n' \
    "$(date -u +%F)" "$model" "$sc_verdict" "$score" "$avg_wall" "$note_safe" >> "$SCORECARD_SCRIPT"

  echo "[reviewer-dogfood] $model -> recall=$recall precision=$precision_note verdict=$verdict" >&2
done

chmod +x "$SCORECARD_SCRIPT" 2>/dev/null || true
echo "" >&2
echo "[reviewer-dogfood] summary: $SUMMARY" >&2
echo "[reviewer-dogfood] scorecard-append script (review before running): $SCORECARD_SCRIPT" >&2
echo "[reviewer-dogfood] NEVER auto-run: sudo -u bench-grader bash $SCORECARD_SCRIPT" >&2
cat "$SUMMARY" >&2
