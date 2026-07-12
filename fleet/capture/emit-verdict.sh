#!/usr/bin/env bash
# fleet/capture/emit-verdict.sh — parse a review packet → verdict.json → enqueue
# FINAL capture request (Chunk C).
#
# Usage:
#   emit-verdict.sh <review-packet> [--model <model>] [--job <job>] [--enqueue]
#
# Reads a review packet (markdown) and extracts the machine verdict, gate, score,
# and evidence. Writes <packet>.verdict.json. With --enqueue, also drops the
# FINAL capture JSON into the spool.
#
# Verdict mapping (human → machine):
#   MERGE / APPROVED → MERGE, pass
#   FIX-REQUIRED / FIXES / CHANGES-REQUESTED → BLOCK
#   REJECT → BLOCK, fail
#
# Severity heuristic score:
#   CRITICAL → score ≤ 20
#   CRITICAL + HIGH → score ~15
#   HIGH only → score ~40
#   MEDIUM/LOW only → score ~60
set -euo pipefail

PROG="${0##*/}"
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# ── Arg parse ────────────────────────────────────────────────────────────────
PACKET=""
MODEL="${CAPTURE_MODEL:-}"
JOB="${CAPTURE_JOB:-}"
ENQUEUE=0
DRY_RUN=0

while [ $# -gt 0 ]; do
  case "$1" in
    --model)   MODEL="$2"; shift 2 ;;
    --job)     JOB="$2"; shift 2 ;;
    --enqueue) ENQUEUE=1; shift ;;
    --dry-run) DRY_RUN=1; shift ;;
    --help|-h)
      sed -n '2,/^set -euo pipefail/p' "$0" | sed 's/^# //; s/^#//' >&2
      exit 0 ;;
    --*) echo "$PROG: unknown arg '$1'" >&2; exit 1 ;;
    *) PACKET="$1"; shift ;;
  esac
done

[ -n "$PACKET" ] || { echo "$PROG: missing <review-packet>" >&2; exit 1; }
[ -f "$PACKET" ] || { echo "$PROG: file not found: $PACKET" >&2; exit 1; }

CONTENT="$(cat "$PACKET")"

# ── Extract verdict ──────────────────────────────────────────────────────────
HUMAN_VERDICT=""
HUMAN_VERDICT_LINE="$(echo "$CONTENT" | grep -iE '^VERDICT:?|^\*\*VERDICT|^## VERDICT' | head -1 || true)"

if echo "$HUMAN_VERDICT_LINE" | grep -qiE 'MERGE|APPROVED|LGTM'; then
  HUMAN_VERDICT="MERGE"
elif echo "$HUMAN_VERDICT_LINE" | grep -qiE 'FIX-REQUIRED|FIXES|CHANGES.REQUESTED|NOT MERGEABLE|BLOCK'; then
  HUMAN_VERDICT="BLOCK"
elif echo "$HUMAN_VERDICT_LINE" | grep -qiE 'REJECT'; then
  HUMAN_VERDICT="BLOCK"
fi

# Fallback: scan the last 15 lines for VERDICT pattern, take the LAST match
if [ -z "$HUMAN_VERDICT" ]; then
  TAIL_VERDICT="$(echo "$CONTENT" | tail -15 | grep -iE 'VERDICT|verdict' | tail -1 || true)"
  if echo "$TAIL_VERDICT" | grep -qiE 'MERGE|APPROVED'; then
    HUMAN_VERDICT="MERGE"
  elif echo "$TAIL_VERDICT" | grep -qiE 'FIX|BLOCK|REJECT|NOT MERGEABLE'; then
    HUMAN_VERDICT="BLOCK"
  fi
fi

# ── Count defects by severity ────────────────────────────────────────────────
CRITICAL_COUNT=$(echo "$CONTENT" | grep -ciE '\[CRITICAL\]|CRITICAL[[:space:]]*[:\\-]|\*\*CRITICAL' || echo 0)
HIGH_COUNT=$(echo "$CONTENT" | grep -ciE '\[HIGH\]|HIGH[[:space:]]*[:\\-]|\*\*HIGH[^L]' || echo 0)
MEDIUM_COUNT=$(echo "$CONTENT" | grep -ciE '\[MEDIUM\]|MEDIUM[[:space:]]*[:\\-]' || echo 0)
LOW_COUNT=$(echo "$CONTENT" | grep -ciE '\[LOW\]|LOW[[:space:]]*[:\\-]' || echo 0)

# ── Compute score ────────────────────────────────────────────────────────────
compute_score() {
  if [ "$CRITICAL_COUNT" -gt 0 ]; then
    if [ "$HIGH_COUNT" -gt 0 ]; then echo 15
    else echo 20; fi
  elif [ "$HIGH_COUNT" -gt 0 ]; then echo 40
  elif [ "$MEDIUM_COUNT" -gt 0 ]; then echo 60
  elif [ "$LOW_COUNT" -gt 0 ]; then echo 70
  else echo 100
  fi
}
SCORE="$(compute_score)"

# ── Determine gate ───────────────────────────────────────────────────────────
if [ "$HUMAN_VERDICT" = "MERGE" ]; then
  GATE="pass"
elif [ "$CRITICAL_COUNT" -gt 0 ] || [ "$HIGH_COUNT" -gt 0 ]; then
  GATE="fail"
else
  GATE="pass"
fi

# ── Evidence excerpt ─────────────────────────────────────────────────────────
EVIDENCE=""
EVIDENCE_LINE="$(echo "$CONTENT" | grep -A2 -i 'CRITICAL' | head -3 | tail -1 | sed 's/^[*#]*[[:space:]]*//' | tr '\n' ' ' | cut -c1-200)"
if [ -z "$EVIDENCE_LINE" ]; then
  EVIDENCE_LINE="$(echo "$HUMAN_VERDICT_LINE" | sed 's/^[#*[:space:]]*//' | tr '\n' ' ')"
fi
EVIDENCE="${EVIDENCE_LINE:-review packet at $(basename "$PACKET")}"

# ── Default model/job from packet filename ───────────────────────────────────
[ -z "$MODEL" ] && MODEL="${CAPTURE_JOB_MODEL:-unknown}"
[ -z "$JOB" ]   && JOB="$(basename "$PACKET" | sed 's/\.[^.]*$//')"

# ── Build verdict JSON with python3 (no jq dependency) ───────────────────────
_build_verdict_json() {
  python3 -c '
import json, sys
d = {
    "verdict": sys.argv[1],
    "gate": sys.argv[2],
    "score": int(sys.argv[3]),
    "evidence": sys.argv[4],
    "source_packet": sys.argv[5],
}
print(json.dumps(d, indent=2))
' "$HUMAN_VERDICT" "$GATE" "$SCORE" "$EVIDENCE" "$(basename "$PACKET")"
}

VERDICT_JSON="$(_build_verdict_json)"

PACKET_BASE="$(dirname "$PACKET")/$(basename "$PACKET" | sed 's/\.[^.]*$//')"
VERDICT_FILE="${PACKET_BASE}.verdict.json"

echo "$VERDICT_JSON" > "$VERDICT_FILE"
echo "$PROG: wrote $VERDICT_FILE" >&2

if [ "$DRY_RUN" -eq 1 ]; then
  echo "$VERDICT_JSON"
  echo "---"
  echo "DRY-RUN: not enqueuing"
  exit 0
fi

# ── Enqueue FINAL capture request ────────────────────────────────────────────
if [ "$ENQUEUE" -eq 1 ]; then
  if [ -z "$MODEL" ] || [ "$MODEL" = "unknown" ]; then
    echo "$PROG: --model required for --enqueue" >&2
    exit 1
  fi
  ENQUEUE_SCRIPT="${SCRIPT_DIR}/enqueue-capture.sh"
  if [ ! -x "$ENQUEUE_SCRIPT" ]; then
    echo "$PROG: enqueue-capture.sh not found/executable at $ENQUEUE_SCRIPT" >&2
    exit 1
  fi
  "$ENQUEUE_SCRIPT" \
    --model "$MODEL" \
    --ref "$JOB" \
    --claimed-result "SUCCESS" \
    --stage active \
    --actual-verdict "$HUMAN_VERDICT" \
    --actual-gate "$GATE" \
    --score "$SCORE" \
    --evidence "$EVIDENCE" \
    --call-log-report
  echo "$PROG: enqueued FINAL capture request via enqueue-capture.sh" >&2
fi

exit 0
