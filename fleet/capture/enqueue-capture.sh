#!/usr/bin/env bash
# fleet/capture/enqueue-capture.sh — build capture JSON per §1/§2 and drop in
# spool/req/ (Chunk A). Calls log-model-report.sh when discrepancy detected (Chunk F).
#
# Usage:
#   enqueue-capture.sh --model <model> --claimed-result <result> \
#       [--ref <ref>] [--work-class <class>] [--difficulty <tier>] \
#       [--stage provisional|active] [--brief-meta <path>] \
#       [--actual-verdict <verdict>] [--actual-gate <gate>] \
#       [--score <0-100>] [--evidence <text>] \
#       [--call-log-report] [--dry-run]
#
# Env fallbacks (for use from charon-run.sh hook):
#   CHARON_JOB_WORK_CLASS  CHARON_JOB_REF  CHARON_JOB_DIFFICULTY
#   CAPTURE_SPOOL_DIR (default /var/lib/bench-grader/spool/req)
set -euo pipefail

PROG="${0##*/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Arg parse ────────────────────────────────────────────────────────────────
MODEL=""
CLAIMED_RESULT=""
REF=""
WORK_CLASS=""
DIFFICULTY=""
STAGE="provisional"
BRIEF_META=""
ACTUAL_VERDICT=""
ACTUAL_GATE=""
SCORE=""
EVIDENCE=""
CALL_LOG_REPORT=0
DRY_RUN=0
SPOOL_DIR="${CAPTURE_SPOOL_DIR:-/var/lib/bench-grader/spool/req}"

while [ $# -gt 0 ]; do
  case "$1" in
    --model)           MODEL="$2"; shift 2 ;;
    --claimed-result)  CLAIMED_RESULT="$2"; shift 2 ;;
    --ref)             REF="$2"; shift 2 ;;
    --work-class)      WORK_CLASS="$2"; shift 2 ;;
    --difficulty)      DIFFICULTY="$2"; shift 2 ;;
    --stage)           STAGE="$2"; shift 2 ;;
    --brief-meta)      BRIEF_META="$2"; shift 2 ;;
    --actual-verdict)  ACTUAL_VERDICT="$2"; shift 2 ;;
    --actual-gate)     ACTUAL_GATE="$2"; shift 2 ;;
    --score)           SCORE="$2"; shift 2 ;;
    --evidence)        EVIDENCE="$2"; shift 2 ;;
    --call-log-report) CALL_LOG_REPORT=1; shift ;;
    --dry-run)         DRY_RUN=1; shift ;;
    --help|-h)
      sed -n '2,/^set -euo pipefail/p' "$0" | sed 's/^# //; s/^#//' >&2
      exit 0 ;;
    *) echo "$PROG: unknown arg '$1'" >&2; exit 1 ;;
  esac
done

# ── Load job-meta (Chunk B) ──────────────────────────────────────────────────
# shellcheck source=./job-meta.sh
source "${SCRIPT_DIR}/job-meta.sh"
_load_brief_meta "${BRIEF_META:-}"

[ -z "$REF" ]        && [ -n "$JM_REF" ]        && REF="$JM_REF"
[ -z "$WORK_CLASS" ] && [ -n "$JM_WORK_CLASS" ] && WORK_CLASS="$JM_WORK_CLASS"
[ -z "$DIFFICULTY" ] && [ -n "$JM_DIFFICULTY" ] && DIFFICULTY="$JM_DIFFICULTY"

# Fall back to env
[ -z "$REF" ]        && REF="${CHARON_JOB_REF:-}"
[ -z "$WORK_CLASS" ] && WORK_CLASS="${CHARON_JOB_WORK_CLASS:-}"
[ -z "$DIFFICULTY" ] && DIFFICULTY="${CHARON_JOB_DIFFICULTY:-}"

# ── Validation ───────────────────────────────────────────────────────────────
VALID_WORK_CLASSES="money-path routing ci-infra refactor bugfix tests greenfield-feature docs frontend generalist"
VALID_STAGES="provisional active"
VALID_VERDICTS="MERGE FIXES BLOCK"
VALID_GATES="pass fail"

missing=""
[ -z "$MODEL" ]          && missing="$missing --model"
[ -z "$CLAIMED_RESULT" ] && missing="$missing --claimed-result"
if [ -n "$missing" ]; then
  echo "$PROG: missing required argument(s):$missing" >&2
  exit 1
fi

if ! echo "$VALID_STAGES" | grep -qw "$STAGE"; then
  echo "$PROG: invalid stage '$STAGE' (valid: $VALID_STAGES)" >&2; exit 1
fi
if [ -n "$ACTUAL_VERDICT" ]; then
  if ! echo "$VALID_VERDICTS" | grep -qw "$ACTUAL_VERDICT"; then
    echo "$PROG: invalid actual-verdict '$ACTUAL_VERDICT' (valid: $VALID_VERDICTS)" >&2; exit 1
  fi
fi
if [ -n "$ACTUAL_GATE" ]; then
  if ! echo "$VALID_GATES" | grep -qw "$ACTUAL_GATE"; then
    echo "$PROG: invalid actual-gate '$ACTUAL_GATE' (valid: $VALID_GATES)" >&2; exit 1
  fi
fi
if [ -n "$WORK_CLASS" ]; then
  if ! echo "$VALID_WORK_CLASSES" | grep -qw "$WORK_CLASS"; then
    echo "$PROG: invalid work-class '$WORK_CLASS' (valid: $VALID_WORK_CLASSES)" >&2; exit 1
  fi
fi

# ── Generate run_id ──────────────────────────────────────────────────────────
RUN_ID="capture-${MODEL}-${REF:-norref}-$(date -u +%s)-$$"

# ── Build JSON with python3 (no jq dependency) ───────────────────────────────
_build_json() {
  python3 -c '
import json, sys
d = {}
d["run_id"] = sys.argv[1]
d["model"] = sys.argv[2]
d["unit_id"] = sys.argv[3]
d["kind"] = "capture"
d["worktree"] = "/dev/null"
d["claimed_result"] = sys.argv[4]
d["stage"] = sys.argv[5]
if sys.argv[6]: d["work_class"] = sys.argv[6]
if sys.argv[7]: d["ref"] = sys.argv[7]
if sys.argv[8]: d["difficulty"] = sys.argv[8]
if sys.argv[9]: d["actual_verdict"] = sys.argv[9]
if sys.argv[10]: d["actual_gate"] = sys.argv[10]
if sys.argv[11]: d["score"] = int(sys.argv[11])
if sys.argv[12]: d["evidence"] = sys.argv[12]
print(json.dumps(d, indent=2))
' "$RUN_ID" "$MODEL" "CAPTURE-${REF:-norref}" "$CLAIMED_RESULT" "$STAGE" \
    "$WORK_CLASS" "$REF" "$DIFFICULTY" "$ACTUAL_VERDICT" "$ACTUAL_GATE" \
    "$SCORE" "$EVIDENCE"
}

JSON="$(_build_json)"

# ── Output ───────────────────────────────────────────────────────────────────
if [ "$DRY_RUN" -eq 1 ]; then
  echo "$JSON"
  echo "---"
  echo "DRY-RUN: would enqueue to $SPOOL_DIR/$RUN_ID.json"
  exit 0
fi

if [ ! -d "$SPOOL_DIR" ]; then
  echo "$PROG: spool dir not found: $SPOOL_DIR (operator step E?)" >&2
  exit 1
fi

OUT_FILE="$SPOOL_DIR/$RUN_ID.json"
echo "$JSON" > "$OUT_FILE"
chmod 644 "$OUT_FILE" 2>/dev/null || true
echo "$PROG: enqueued $OUT_FILE" >&2

# ── Chunk F: call log-model-report.sh on discrepancy ─────────────────────────
_detect_discrepancy() {
  [ "$CLAIMED_RESULT" = "SUCCESS" ] || return 1
  if [ -n "$ACTUAL_VERDICT" ] && [ "$ACTUAL_VERDICT" = "BLOCK" ]; then return 0; fi
  if [ -n "$ACTUAL_GATE" ] && [ "$ACTUAL_GATE" = "fail" ]; then return 0; fi
  return 1
}

if [ "$CALL_LOG_REPORT" -eq 1 ] && _detect_discrepancy; then
  LOG_REPORT="${SCRIPT_DIR}/../log-model-report.sh"
  if [ -x "$LOG_REPORT" ]; then
    "$LOG_REPORT" \
      --job "${REF:-unknown}" \
      --model "$MODEL" \
      --incident "FALSE-SUCCESS: claimed=${CLAIMED_RESULT} actual_verdict=${ACTUAL_VERDICT:-?} actual_gate=${ACTUAL_GATE:-?} score=${SCORE:-?}" \
      --evidence "${EVIDENCE:-capture-pipeline auto-detected}" \
      >&2 || true
  fi
fi

exit 0
