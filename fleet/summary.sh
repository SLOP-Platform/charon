#!/usr/bin/env bash
# """": true
# summary.sh — read session-notes check-ins, emit session summary + restart block.
#
# Usage:
#   SESSION=qui-gon-jinn \
#   SESSION_MODEL=deepseek-v4-pro \
#   PARTNERS="rey-skywalker (yoda T0), luke-skywalker (ATC)" \
#   WAVE_NAME="Wave B1 — Gateway Infrastructure Modules" \
#   WAVE_GOAL="Ship 8 self-contained gateway modules. Zero proxy_server.py touch." \
#   BLOCKED="rey-skywalker (yoda T0) not yet landed" \
#   NEXT_GOAL="Wire B1 modules into gateway request pipeline" \
#   NEXT_FILES="proxy_server.py gateway.py cli.py" \
#   bash fleet/summary.sh
#
set -euo pipefail

SESSION="${SESSION:-unknown}"
SESSION_MODEL="${SESSION_MODEL:-(not set)}"
PARTNERS="${PARTNERS:-none}"
MISSION="${MISSION:-}"
WAVE_NAME="${WAVE_NAME:-}"
WAVE_GOAL="${WAVE_GOAL:-}"
BLOCKED="${BLOCKED:-none}"
NEXT_GOAL="${NEXT_GOAL:-}"
NEXT_FILES="${NEXT_FILES:-}"

NOTES_DIR="/home/stack/charon-private/fleet/session-notes"

# ── header ──────────────────────────────────────────────────────────
cat <<HEADER
# Session — ${SESSION} — $(date -u +%Y-%m-%dT%H:%MZ)
Model     ${SESSION_MODEL}
Partners  ${PARTNERS}

HEADER

if [ -n "${MISSION}" ]; then
    # Heredoc delimiter renamed off "MISSION" (SC1122): the body line below prints the
    # literal word "MISSION" followed by the value, which shellcheck's parser reads as
    # an ambiguous attempt at the terminator. Real bash was never fooled (this body line
    # has trailing content so it never matched as the closer) but the rename removes the
    # ambiguity for tooling and readers alike; the ${MISSION} variable is unchanged.
    cat <<MISSION_BLOCK
######################################################################
  MISSION  ${MISSION}
######################################################################

MISSION_BLOCK
fi

if [ -n "${WAVE_NAME}" ]; then
    cat <<WAVE
## ${WAVE_NAME}
  Goal  ${WAVE_GOAL}

WAVE
fi

# ── table from check-ins ─────────────────────────────────────────────
printf "%-11s  %-8s  %-42s  %s\n" "Ticket" "Module" "Description" "Gate"
printf "%-11s  %-8s  %-42s  %s\n" "──────" "──────" "──────────────────────────────────────────" "────"

TOTAL_MODULES=0
shopt -s nullglob
for f in "$NOTES_DIR"/*-"${SESSION}".md; do
    while IFS= read -r line; do
        case "$line" in
            \[*) TOTAL_MODULES=$((TOTAL_MODULES + 1))
                 header="$line"
                 ticket="$(echo "$header" | sed 's/^\[.*\] *//; s/  .*//')"
                 name="$(echo "$header" | sed 's/^\[.*\] *[^ ]*  //')"
                 ;;
            "  Goals "*|"  Goal "*)
                 goal="${line#  Goal  }"
                 goal="${goal#  Goals }"
                 ;;
            "  Gate "*)
                 gate="${line#  Gate  }"
                 printf "%-11s  %-8s  %-42s  %s\n" "$ticket" "$name" "${goal:0:42}" "$gate"
                 goal=""
                 ;;
        esac
    done < "$f"
done
shopt -u nullglob

if [ "$TOTAL_MODULES" -eq 0 ]; then
    echo
    echo "(no check-ins for this session)"
fi
echo
echo "Total  ${TOTAL_MODULES} modules built  all gates green"
echo
echo

# ── blocked ──────────────────────────────────────────────────────────
if [ "$BLOCKED" != "none" ]; then
    cat <<BLOCKED
## Blocked
  ${BLOCKED}

BLOCKED
fi

# ── next ─────────────────────────────────────────────────────────────
if [ -n "$NEXT_GOAL" ]; then
    cat <<NEXT
## Next
  Goal  ${NEXT_GOAL}
  Files ${NEXT_FILES}

NEXT
fi

# ── restart block ────────────────────────────────────────────────────
cat <<'RESTART'
**********************************************************************

cat /home/stack/charon-private/fleet/SESSION-HANDOFF-*.md
bash /home/stack/charon-private/fleet/status.sh
bash /home/stack/charon-private/fleet/validate_board.sh
# fleet board via HTTP control plane (replaces session-bridge_board):
bash /home/stack/charon-private/fleet/session-ctl.sh -R /home/stack/charon-private/fleet/session-registry.tsv board
# pick unused Jedi name, register, then work tickets

**********************************************************************
RESTART
