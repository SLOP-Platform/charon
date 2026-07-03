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

Read \`/home/stack/charon-private/fleet/SESSION-HANDOFF-*.md\` fully, then run
\`bash /home/stack/charon-private/fleet/status.sh && bash /home/stack/charon-private/fleet/validate_board.sh\`,
check the board for claimed names, register with an unused Jedi name + \`repo="charon"\`, then go.

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
echo "### Gate"
echo '```'
PYTHONPATH=src python3 -m pytest -q --no-header 2>&1 | tail -3 || true
ruff check src tests 2>&1 | tail -3 || true
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

---

## Human analysis

**Previous session name:**  <fill in>
**Previous session model:** <fill in>

### What was done this session

<Describe each ticket / change that landed.  Be specific: what was built, what
tests were added, what was verified.  Include commit SHAs or PR numbers if
pushed.>

### Key findings / decisions

<Surprises, discoveries, design decisions the next session needs to know.
Gatekeeper decisions — e.g. "we chose Option B over Option A because…".>

### What must happen next (in priority order)

<Numbered list with concrete actions.  Name the ticket, the files it owns,
the branch name, the accept command.  List dependencies explicitly.>

### Collision matrix

| File | Owner (live) | Owner (next) |
|---|---|---|
| <filename> | <current ticket> | <next dependent ticket> |

### Open questions / Blockers

<Anything that needs operator input before the next session can proceed.>

### Files modified this session

| File | Change |
|---|---|
| <path> | <description> |

### Cross-repo improvements to propose

<Improvements discovered this session that would benefit the other repo
(Charon → mediastack, or mediastack → Charon).  Include: problem, concrete fix,
files touched, expected benefit.  Deliver via session bridge if the other session
is active, otherwise preserved here for the next handoff.>

---

## Handoff file maintenance

- **Per-session files:** \`SESSION-HANDOFF-\$SESSION.md\`. Never reuse a session name.
  Each boot picks a fresh unused Jedi name from the board. No collisions.
- **Generate:** run \`SESSION=<name> bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF-<name>.md\`
  at session end, then fill in the Human analysis section.
- **Commit:** commit the completed \`SESSION-HANDOFF-<name>.md\` to the charon-private fleet repo.
- **Read:** the next session reads ALL \`SESSION-HANDOFF-*.md\` files to ground itself.
FOOTER
