#!/usr/bin/env bash
# """": true
# checkin.sh — append a per-ticket check-in to session-notes/<timestamp>-<session>.md
#
# Usage:
#   SESSION=qui-gon-jinn \
#   bash fleet/checkin.sh "W0:B1" "T0.3" "ADOPT-CACHE" \
#     "Reduce duplicate upstream calls by caching identical prompt+model responses" \
#     "SemanticCache — LRU eviction, TTL expiry, thread-safe with RLock" \
#     "src/charon/cache.py (+87) tests/test_cache.py (+95)" \
#     "11/11 ruff✓ mypy✓ boundary✓"
#
set -euo pipefail

SESSION="${SESSION:-unknown}"
WAVE_BATCH="${1:?}"
TICKET="${2:?}"
NAME="${3:?}"
GOAL="${4:?}"
BUILT="${5:?}"
FILES="${6:?}"
GATE="${7:?}"

NOTES_DIR="/home/stack/charon-private/fleet/session-notes"
mkdir -p "$NOTES_DIR"

NOTES_FILE="$NOTES_DIR/$(date -u +%Y%m%dT%H%MZ)-${SESSION}.md"

cat <<BLOCK >> "$NOTES_FILE"

[${WAVE_BATCH}] ${TICKET}  ${NAME}
  Goal  ${GOAL}
  Built ${BUILT}
  Files ${FILES}
  Gate  ${GATE}
BLOCK

echo "checkin appended → ${NOTES_FILE}"
