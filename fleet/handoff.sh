#!/usr/bin/env bash
# """": true
# handoff.sh — generate the machine-state section of SESSION-HANDOFF.md.
#
# Usage:  SESSION=mace-windu bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF-mace-windu.md
# Then the operator fills in the Human analysis section below the auto-generated block.
#
# Per-session handoffs: set $SESSION to your Jedi name. Output goes to
# SESSION-HANDOFF-<session>.md. Multiple concurrent sessions never collide.
#
# Contract: this script MUST be idempotent and MUST NOT modify any files — it only
# reads the current repo state and writes markdown to stdout.

set -euo pipefail

CHARON_REPO="/home/stack/code/charon"
DATE_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"

cat <<PREAMBLE
# Charon Fleet — Session Handoff ($DATE_UTC) — \${SESSION:-unknown}

> **Per-session handoff.** Each session writes: \`SESSION-HANDOFF-\$SESSION.md\`.
> No collisions. Next session reads ALL: \`SESSION-HANDOFF-*.md\`.

---

## Bootstrap (copy-paste into next session)

Read \`/home/stack/charon-private/fleet/SESSION-HANDOFF-*.md\` in narrow line-range slices (not whole-file), then run
\`bash /home/stack/charon-private/fleet/status.sh && bash /home/stack/charon-private/fleet/validate_board.sh\`,
check the board for claimed names, register with an unused Jedi name + \`repo="charon"\`, then go.

### Context discipline (token-burn guard — always on)
1. **Auto-compact ON.** At startup verify \`grep autoCompactEnabled ~/.claude/settings.json\` shows \`true\`. If not, STOP and tell the operator (see \`fleet/SETTINGS-GUARD-PROPOSAL.md\`) — a never-compacting transcript makes per-turn token cost climb all session.
2. **Sub-sessions write, don't dump.** A sub-session WRITES its findings to a file and returns only a 2-3 line pointer + the absolute path. NEVER paste a full sub-session report back into the primary.
3. **Read big docs in narrow slices, once.** Read handoffs/plans by line-range (offset/limit), never the whole file, never re-read each turn.
4. **Keep-alive is a light heartbeat.** Fold the bridge heartbeat into real work (\`board()\` TTL 600s); do NOT run a 4-min idle wakeup loop that reprocesses full context.

---

## Auto-generated state (from \`handoff.sh\` run at $DATE_UTC)

### Git
PREAMBLE

# --- git state ---------------------------------------------------------------
echo '```'
git -C "$CHARON_REPO" branch --show-current
echo
git -C "$CHARON_REPO" status --short
echo
echo "--- last 10 commits ---"
git -C "$CHARON_REPO" log --oneline -10
echo '```'

# --- open PRs ----------------------------------------------------------------
echo "### Open PRs"
echo '```'
gh pr list --repo SLOP-Platform/charon --state open --json number,title,headRefName,state 2>/dev/null || echo "(gh not available)"
echo '```'

# --- gate --------------------------------------------------------------------
# A RED gate MUST be fatal: capture each gate's OWN exit code (not the tail's) so
# a failing pytest/ruff propagates. We keep tail for output brevity but never
# swallow the gate result with '|| true' (that defeated set -e — see reds.tsv
# handoff-pipefail-mask). The full handoff still renders; handoff.sh then exits
# non-zero at the end so a red gate cannot be handed off as green.
echo "### Gate"
echo '```'
GATE_RC=0
gate_out="$( { FLEET="${FLEET:-/home/stack/charon-private/fleet}"; bash "$FLEET/gate.sh" 2>&1; } )" || GATE_RC=$?
printf '%s\n' "$gate_out" | tail -3
echo '```'

# --- roadmap (canonical) -----------------------------------------------------
# The task-list/status section is rendered by the ONE canonical renderer
# (fleet/report.sh <- fleet/state/ROADMAP.tsv). Do NOT hand-type roadmap status
# in a handoff — edit ROADMAP.tsv and this stays in sync every session.
echo "### Roadmap (canonical — fleet/report.sh)"
echo '```'
bash /home/stack/charon-private/fleet/report.sh 2>&1 || echo "(report.sh failed — see fleet/state/ROADMAP.tsv)"
echo '```'

# --- board -------------------------------------------------------------------
echo "### Board"
echo '```'
bash /home/stack/charon-private/fleet/status.sh 2>&1 || true
echo '```'

echo "### Board validation"
echo '```'
bash /home/stack/charon-private/fleet/validate_board.sh 2>&1 || true
echo '```'

# --- parked tickets ----------------------------------------------------------
echo "### Parked tickets"
echo '```'
if [ -d /home/stack/charon-private/fleet/board ]; then
    shopt -s nullglob
    for f in /home/stack/charon-private/fleet/board/*.md.parked; do
        basename "$f"
    done
    shopt -u nullglob
else
    echo "(board dir not found)"
fi
echo '```'

echo "### Live tickets (.md, not parked)"
echo '```'
if [ -d /home/stack/charon-private/fleet/board ]; then
    shopt -s nullglob
    for f in /home/stack/charon-private/fleet/board/*.md; do
        bn="$(basename "$f")"
        tier="$(head -20 "$f" | grep "^tier:" | head -1 | sed 's/tier: *//')"
        deps="$(head -20 "$f" | grep "^depends_on:" | head -1 | sed 's/depends_on: *//')"
        echo "$bn  tier=$tier  depends_on=$deps"
    done
    shopt -u nullglob
else
    echo "(board dir not found)"
fi
echo '```'

cat <<'FOOTER'

**********************************************************************
(handoff.sh auto-state section ends here)
(generate session summary with summary.sh, then copy-paste below)
**********************************************************************

## Session summary — paste output of:
##
##   SESSION=$SESSION \
##   SESSION_MODEL=<model> \
##   PARTNERS="<other-sessions>" \
##   WAVE_NAME="<wave name>" \
##   WAVE_GOAL="<wave goal — why this wave exists>" \
##   BLOCKED="<what's blocking next wave>" \
##   NEXT_GOAL="<next wave goal>" \
##   NEXT_FILES="<files for next wave>" \
##   bash /home/stack/charon-private/fleet/summary.sh
##
## (summary.sh reads check-ins written by checkin.sh during the session)

## Key findings / decisions

<Surprises, discoveries, design decisions the next session needs to know.
Gatekeeper decisions — e.g. "we chose Option B over Option A because…".>

## Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| <filename> | <current ticket> | <next dependent ticket> |

## Open questions

<Anything that needs operator input before the next session can proceed.>

## Files modified this session

| File | Change |
|---|---|
| <path> | <description> |

## Cross-repo improvements to propose

<Improvements discovered this session that would benefit the other repo
(Charon → mediastack, or mediastack → Charon). Include: problem, concrete fix,
files touched, expected benefit.>

---

## Handoff file maintenance

- **Per-session files:** \`SESSION-HANDOFF-\$SESSION.md\`. Never reuse a session name.
  Each boot picks a fresh unused Jedi name from the board. No collisions.
- **Generate:**
  1. During session: \`SESSION=<name> bash fleet/checkin.sh <args>\` per ticket.
  2. At session end: run \`summary.sh\` to emit the session summary.
  3. Pipe handoff.sh into \`fleet/SESSION-HANDOFF-<name>.md\`, paste summary output
     below the auto-state section.
- **Commit:** commit the completed \`SESSION-HANDOFF-<name>.md\` to the charon-private fleet repo.
- **Read:** the next session reads ALL \`SESSION-HANDOFF-*.md\` files to ground itself.
FOOTER

# A red gate is fatal: exit non-zero so handoff.sh cannot report a red gate as a
# clean handoff (it still emitted the full doc above for the operator's record).
exit "${GATE_RC:-0}"
