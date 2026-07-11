#!/usr/bin/env bash
# fleet/log-model-report.sh — append a structured lie-detection entry to the
# model self-report reliability log (MODEL-SELF-REPORT-RELIABILITY.md).
#
# Doctrine: document model self-report lies. Given ticket/session + claimed-vs-actual,
# appends a correctly-formatted markdown-table row. Idempotent via sidecar hash file.
#
# Usage:
#   log-model-report.sh --job <job> --model <model> \
#                       --incident <text> --evidence <text> [options]
#
# Options:
#   --date <YYYY-MM-DD>    default: today UTC
#   --log <path>           default: $REPO_ROOT/fleet/state/MODEL-SELF-REPORT-RELIABILITY.md
#   --dry-run              print the row + metadata instead of appending
#
# Env fallbacks (useful for CI / review-flow call-sites):
#   MODEL_LIE_DATE, MODEL_LIE_JOB, MODEL_LIE_MODEL, MODEL_LIE_INCIDENT,
#   MODEL_LIE_EVIDENCE, MODEL_LIE_LOG
#
# Exit: 0 = newly appended or already present; 1 = error / missing required arg.
set -uo pipefail

PROG="${0##*/}"

# ------------------------------------------------------------------
# Arg parse
# ------------------------------------------------------------------
DATE="${MODEL_LIE_DATE:-}"
JOB="${MODEL_LIE_JOB:-}"
MODEL="${MODEL_LIE_MODEL:-}"
INCIDENT="${MODEL_LIE_INCIDENT:-}"
EVIDENCE="${MODEL_LIE_EVIDENCE:-}"
LOG="${MODEL_LIE_LOG:-}"
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --date)    DATE="$2"; shift 2; ;;
    --job)     JOB="$2";  shift 2; ;;
    --model)   MODEL="$2"; shift 2; ;;
    --incident) INCIDENT="$2"; shift 2; ;;
    --evidence) EVIDENCE="$2"; shift 2; ;;
    --log)     LOG="$2";   shift 2; ;;
    --dry-run) DRY_RUN=1;  shift; ;;
    --help|-h)
      sed -n '2,/^# Exit:/p' "$0" | sed 's/^# //; s/^#//' >&2
      exit 0
      ;;
    *) echo "$PROG: unknown arg '$1'" >&2; exit 1 ;;
  esac
done

# ------------------------------------------------------------------
# Defaults & validation
# ------------------------------------------------------------------
[ -z "$DATE" ] && DATE="$(date -u +%F)"

missing=""
[ -z "$JOB" ]      && missing="$missing --job"
[ -z "$MODEL" ]    && missing="$missing --model"
[ -z "$INCIDENT" ] && missing="$missing --incident"
[ -z "$EVIDENCE" ] && missing="$missing --evidence"
if [ -n "$missing" ]; then
  echo "$PROG: missing required argument(s):$missing" >&2
  exit 1
fi

# ------------------------------------------------------------------
# Resolve default log path relative to repo root
# ------------------------------------------------------------------
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null || true)"
if [ -z "$REPO_ROOT" ]; then
  # fallback: script is in fleet/ => repo root is parent of fleet/
  REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"
fi

LOG_PATH="${LOG:-$REPO_ROOT/fleet/state/MODEL-SELF-REPORT-RELIABILITY.md}"
SIDECAR="${LOG_PATH%.md}.ids"

mkdir -p "$(dirname "$LOG_PATH")"

# ------------------------------------------------------------------
# Sanitize cell text for markdown pipe table
# ------------------------------------------------------------------
sanitize_cell(){
  local txt="$1"
  # collapse literal newlines to spaces
  txt="$(printf '%s' "$txt" | tr '\n\r' '  ')"
  # escape literal pipe characters so they don't break the table
  txt="$(printf '%s' "$txt" | sed 's/|/\\|/g')"
  # trim leading/trailing whitespace
  txt="$(printf '%s' "$txt" | sed 's/^[[:space:]]*//; s/[[:space:]]*$//')"
  printf '%s' "$txt"
}

INCIDENT_SAN="$(sanitize_cell "$INCIDENT")"
EVIDENCE_SAN="$(sanitize_cell "$EVIDENCE")"

# ------------------------------------------------------------------
# Deterministic signature for idempotency
# ------------------------------------------------------------------
sig(){
  printf '%s\0%s\0%s\0%s\0%s' "$DATE" "$JOB" "$MODEL" "$INCIDENT" "$EVIDENCE" \
    | sha256sum | awk '{print $1}'
}
HASH="$(sig)"

# Idempotency check
if [ -f "$SIDECAR" ] && grep -qx "$HASH" "$SIDECAR" 2>/dev/null; then
  echo "$PROG: idempotent skip — entry already logged (lie-id=$HASH)" >&2
  exit 0
fi

# ------------------------------------------------------------------
# Build the markdown row
# ------------------------------------------------------------------
ROW="| $DATE | $JOB | $MODEL | $INCIDENT_SAN | $EVIDENCE_SAN |"

if [ "$DRY_RUN" -eq 1 ]; then
  echo "--- DRY-RUN ---"
  echo "log : $LOG_PATH"
  echo "hash: $HASH"
  echo "row : $ROW"
  exit 0
fi

# ------------------------------------------------------------------
# Seed header if file is missing / empty
# ------------------------------------------------------------------
if [ ! -f "$LOG_PATH" ] || [ ! -s "$LOG_PATH" ]; then
  cat > "$LOG_PATH" <<'HEADER'
# Model self-report reliability log

**Directive (operator, 2026-07-10):** DOCUMENT every incident where a model's self-report LIES —
claims success / passing tests / committed work that turns out false. This is a first-class model-quality
signal: a model that fabricates outcomes must be DOWN-RANKED for autonomous build work regardless of its
raw coding ability. Feeds the ACTUALS-LEDGER / quality-feedback ranker (grade REAL outcomes, not claims;
see [[benchmark-not-a-valid-ranker]], [[charon-work-composition-intelligence]]).

**How we catch it:** never trust the build's own SUCCESS line — verify the branch diff actually exists
(`git log master..HEAD`, `git diff --stat`), tests were really run, and work landed on the RIGHT branch.
Merge gate = FULL CI on the merge commit, and every change must add a test that FAILS on revert.

| date | job | model | incident | evidence |
|---|---|---|---|---|
HEADER
fi

# ------------------------------------------------------------------
# Append row and record hash
# ------------------------------------------------------------------
printf '%s\n' "$ROW" >> "$LOG_PATH"
printf '%s\n' "$HASH" >> "$SIDECAR"
echo "$PROG: appended entry to $LOG_PATH (lie-id=$HASH)"
exit 0
