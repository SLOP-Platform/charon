#!/usr/bin/env bash
# """": true
# handoff.sh — generate the machine-state section of SESSION-HANDOFF.md.
#
# Usage:
#   SESSION=mace-windu bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF-mace-windu.md
#   # or, recommended: let handoff.sh auto-claim a fresh Jedi name (pool minus exclusion-set):
#   bash /home/stack/charon-private/fleet/handoff.sh > fleet/SESSION-HANDOFF-<claimed>.md
# Then the operator fills in the Human analysis section below the auto-generated block.
#
# Per-session handoffs: SESSION names the Jedi; output goes to
# SESSION-HANDOFF-<session>.md. Multiple concurrent sessions never collide.
# If $SESSION is unset, handoff.sh calls claim-jedi-name.sh to ATOMICALLY claim a fresh
# name (first-available from fleet/state/jedi-name-pool.txt with every previously-used
# name excluded — live-tree AND git-history). The claimed name is emitted in the
# Bootstrap block below so the operator reads it instead of free-picking.
# Override by setting SESSION explicitly; the override still claims-verify
# (refuses if the chosen name's live file is already present).
#
# Contract: this script MUST be idempotent. It reads the current repo state and
# writes markdown to stdout. The ONLY side-effect outside stdout is:
#   * when SESSION is unset, an atomic claim-stub write via claim-jedi-name.sh
#     into fleet/SESSION-HANDOFF-<claimed-name>.md BEFORE stdout begins (so a
#     concurrent claim-jedi-name.sh cannot race the same name). The rest of the
#     output is generated, then the operator commits the populated file.
#
# HANDOFF-MECHANIZE: the auto-emitted sections now ALSO contain every section handoff-check.sh
# requires (Bootstrap / done-SHA / next-action / gotchas / session-bridge) as MECHANIZED BLOCKS
# (not free-text placeholders). The live machine state the manager used to hand-type (worktree
# list, in-flight charon-run jobs + their CHARON_RUN_RESULT, provider-exhaustion-ledger tail,
# session-bridge board) is now auto-pulled from disk so facts are accurate by construction.
# handoff-check.sh's required-section patterns match the literal headers in this file, so any
# generated handoff passes the gate by default; the manager only has to fill the human-analysis
# sections (Key findings, Collision matrix, etc.) below the auto-state block.

set -euo pipefail

CHARON_REPO="/home/stack/code/charon"
PRIV_REPO="/home/stack/charon-private"
DATE_UTC="$(date -u +%Y-%m-%dT%H:%M:%SZ)"
DATE_HUMAN="$(date -u +%Y-%m-%d)"

# The machine-GENERATED-STATE emitter (truth-of-record block: origin/master SHAs, open PRs,
# stranded-work signal — all from LIVE queries, timeout-bounded + fail-soft on a gh/network
# outage). Sourced (not inlined) so the SAME generator can be exercised hermetically by
# fleet/tests/handoff-generated-state.test.sh for the GitHub-outage resilience path without
# running this whole script. CHARON_REPO/PRIV_REPO above seed its repo-location defaults.
_HS_HERE="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
# shellcheck source=/dev/null
source "$_HS_HERE/handoff-generated-state.sh"
# ANTI-CLOBBER: SESSION must be REAL (not the literal string "unknown") — a copied/placeholder
# handoff (e.g. seeding a new session's file from a different session's old content, as happened in
# 3647e0e) is only obviously-wrong if the provenance stamp below actually names the CURRENT
# session and CURRENT repo state. Previously this line contained an escaped \${SESSION:-unknown}
# that was NEVER expanded.
#
# HANDOFF-NAME-ALLOCATOR (2026-07-23): SESSION is no longer REQUIRED to be pre-supplied. If unset,
# handoff.sh now calls claim-jedi-name.sh to atomically claim a fresh Jedi name (pool minus
# exclusion-set, where exclusion-set unions the live-tree SESSION-HANDOFF-*.md files AND every
# name ever created in git history — the latter is what would have caught luminara-unduli, the
# 2026-07-23 stale-handoff incident whose file was deleted from the live tree but persisted in
# git history until reuse 2 days later). The claimed name is then emitted into the Bootstrap
# block below so the operator reads it instead of free-picking. Set SESSION explicitly to override
# (e.g. for a deterministically-named replay session); the override still runs the same
# claim-verify so reusing a name whose live file is present REFUSES, and reusing one whose file
# is only-in-git-history is allowed ONLY when no fresh-pool-name remains.
if [ -z "${SESSION:-}" ]; then
  CLAIMED_NAME="$(bash "$_HS_HERE/claim-jedi-name.sh")" \
    || { printf 'handoff.sh: claim-jedi-name.sh refused to claim a name — pool exhausted or allocator broken.\n' >&2; exit 2; }
  export SESSION="$CLAIMED_NAME"
else
  exported_session="$SESSION"
  if ! bash "$_HS_HERE/claim-jedi-name.sh" --verify "$exported_session" >/dev/null 2>&1; then
    printf 'handoff.sh: SESSION=%s refused by claim-jedi-name.sh — that name is already in use (live file present). Pass an unused Jedi name, or unset SESSION and let the allocator pick a fresh one.\n' "$exported_session" >&2
    exit 2
  fi
  export SESSION="$exported_session"
fi

# ANTI-CLOBBER freshness stamp: resolve the REAL upstream per repo (never a hardcoded
# origin/main — see check_push_status.sh fix) and record behind-count + HEAD sha. A stale
# or copied handoff shows a mismatched/stale stamp instead of silently looking current.
resolve_upstream() {
  local repo="$1" u
  u=$(git -C "$repo" rev-parse --abbrev-ref --symbolic-full-name '@{u}' 2>/dev/null) || u=""
  if [ -z "$u" ]; then
    u=$(git -C "$repo" symbolic-ref --quiet refs/remotes/origin/HEAD 2>/dev/null | sed 's@^refs/remotes/@@')
  fi
  printf '%s' "$u"
}
freshness_stamp() {
  local repo="$1" label="$2" upstream behind sha
  git -C "$repo" fetch --quiet origin 2>/dev/null || true
  upstream="$(resolve_upstream "$repo")"
  sha="$(git -C "$repo" rev-parse --short HEAD 2>/dev/null || echo "?")"
  if [ -z "$upstream" ]; then
    echo "**$label HEAD:** $sha (upstream UNRESOLVED — cannot verify freshness)"
    return
  fi
  behind=$(git -C "$repo" rev-list --count "HEAD..$upstream" 2>/dev/null || echo 0)
  if [ "${behind:-0}" -gt 0 ]; then
    echo "**$label HEAD:** $sha — ⚠ STALE: $behind commit(s) behind $upstream"
  else
    echo "**$label HEAD:** $sha — current with $upstream"
  fi
}

cat <<PREAMBLE
# Charon Fleet — Session Handoff ($DATE_UTC) — $SESSION

> **Per-session handoff.** Each session writes: \`SESSION-HANDOFF-\$SESSION.md\`.
> No collisions. Next session reads ALL: \`SESSION-HANDOFF-*.md\`.

**Date:** $DATE_HUMAN
**Session:** $SESSION

---

## Bootstrap (copy-paste into next session)

\`\`\`
Read and fully follow /home/stack/charon-private/fleet/SESSION-HANDOFF-$SESSION.md — you are the fresh Charon fleet MANAGER, carry it out, then flip to fleet mode.
\`\`\`

### Context discipline (always on)
See MANAGER-OPERATING-RULES.md §9 (token-economy is DEFAULT) and §13 (startup budget gate). Key: auto-compact ON; sub-sessions write/don't-dump; read big docs in slices once; keep-alive = light heartbeat folded into real work, NOT a 4-min wakeup loop.

---

## Provenance (anti-clobber — verify this matches the session/filename before trusting this handoff)

**Session:** $SESSION
**Generated:** $DATE_UTC
$(freshness_stamp "$CHARON_REPO" "Product")
$(freshness_stamp "$PRIV_REPO" "Rig")

---
PREAMBLE

# GENERATED-STATE (truth-of-record) — emitted from LIVE queries here so a session physically
# cannot hand-assert false state ("PR #NN can't merge") in this region: the handoff PULLS its
# state instead of asserting it. origin/master SHAs, real open-PR state, stranded branches and
# uncommitted work are all machine-queried; a gh/network outage fails soft to UNAVAILABLE lines.
emit_generated_state

cat <<'DONEHDR'

---

## Done / committed@SHA

> Latest 5 SHAs on master (rig + product). Edit only to highlight commits the next session must NOT regress.
DONEHDR

# --- done / committed@SHA -------------------------------------------------------
# A red gate is fatal, but section rendering is best-effort: we wrap in { ; } || true so a
# transient git failure (network down, repo missing) renders "(git unavailable)" rather than
# halting the whole handoff. The GATE_RC block at the end of the script still fails the
# handoff if the gate itself is red.
{
  echo '```'
  echo "rig master HEAD:    $(git -C "$PRIV_REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  echo "rig master subject: $(git -C "$PRIV_REPO" log -1 --format='%s' 2>/dev/null || echo '?')"
  echo "product master HEAD:    $(git -C "$CHARON_REPO" rev-parse --short HEAD 2>/dev/null || echo '?')"
  echo "product master subject: $(git -C "$CHARON_REPO" log -1 --format='%s' 2>/dev/null || echo '?')"
  echo
  echo "--- last 5 rig master commits ---"
  git -C "$PRIV_REPO" log --oneline -5 2>/dev/null || echo "(git log failed)"
  echo
  echo "--- last 5 product master commits ---"
  git -C "$CHARON_REPO" log --oneline -5 2>/dev/null || echo "(git log failed)"
  echo '```'
} || echo "```\n(git unavailable — done/committed section blank)\n```"

cat <<'PREAMBLE2'

---

## Next-action / in-flight

> Auto-emitted machine state is under `## Auto-generated state` below. Fill `### Manager's first actions` terse (numbered, one file/script per item).

PREAMBLE2

# (4) Narrative placeholder for the manager's first-action list.
cat <<'PREAMBLE2B'
### Manager's first actions (priority order — fill below)

1. <first action — the smallest thing that lets the next session start safe>
2. <second>
3. <third>

---
PREAMBLE2B

cat <<'PREAMBLE3'
---

## Gotchas (avoid re-discovering / DENIED)

> Auto-surfaced from reds.tsv open reds matching gotcha markers. Fill session-specific below.

- `git push` is DENIED to the manager (settings deny-list; verbal authority does NOT override it). The operator pushes.
PREAMBLE3

# (5) Any pre-existing tracked red in reds.tsv whose description text starts with a known
#     gotcha-marker is surfaced here automatically. This makes "what burned us last time"
#     a property of the registry, not of hand-typed prose that drifts.
{
  TSV="$PRIV_REPO/fleet/reds.tsv"
  if [ -f "$TSV" ]; then
    # Pull descriptions of any OPEN red that mentions a gotcha-marker. Bounded: at most 5.
    awk -F'\t' '$7=="open"' "$TSV" \
      | grep -iE 'DENIED|never-ignore|never commit|never push|never deploy' \
      | cut -f1,3,5 | head -5 \
      | awk -F'\t' '{printf "- **%s** (%s) — %s\n", $1, $2, $3}'
  fi
} || true

cat <<'PREAMBLE4'
- <session-specific gotcha 1>
- <session-specific gotcha 2>

---

## session-bridge (auto — live board)

> Live `~/.charon/session-bridge.db` snapshot at handoff time.

PREAMBLE4

# (6) session-bridge board — read live from sqlite. If the DB is absent or unreadable
#     (e.g. fresh checkout, no bridge has run), say so loudly.
{
  echo '```'
  DB="$HOME/.charon/session-bridge.db"
  if [ -f "$DB" ] && command -v python3 >/dev/null 2>&1; then
    python3 - "$DB" <<'PY' 2>/dev/null || echo "(python3 probe of session-bridge.db failed)"
import sqlite3, sys
db = sys.argv[1]
try:
    c = sqlite3.connect(db)
    rows = c.execute(
        "SELECT name, repo, status, ticket, last_seen FROM sessions "
        "WHERE last_seen > datetime('now','-30 minutes') ORDER BY last_seen DESC"
    ).fetchall()
    if not rows:
        print("(no active bridge sessions in the last 30 min)")
    else:
        print(f"{'NAME':<30} {'REPO':<11} {'STATUS':<11} {'TICKET':<28} LAST_SEEN")
        for n, r, s, t, l in rows:
            print(f"{(n or '?')[:30]:<30} {(r or '?')[:11]:<11} {(s or '?')[:11]:<11} {(t or '-'):<28} {l}")
except Exception as e:
    print(f"(session-bridge probe error: {e})")
PY
  else
    echo "(no ~/.charon/session-bridge.db — bridge has not run yet)"
  fi
  echo '```'
} || echo "```\n(session-bridge probe failed)\n```"

cat <<'PREAMBLE5'
> Coordination: review the board above for collisions/blockers before claiming work. If blocked, surface in `blockers=` on `register()`. If inheriting a timed-out session, pick a NEW Jedi name.

---

## Auto-generated state
PREAMBLE5

echo "### Active worktrees (\`git worktree list\`)"
{
  echo '```'
  cd "$CHARON_REPO" && git worktree list 2>/dev/null || echo "(charon repo not found)"
  echo
  cd "$PRIV_REPO" && git worktree list 2>/dev/null || echo "(rig repo not found)"
  echo '```'
} || echo "```\n(git worktree list failed)\n```"

# (2) In-flight charon-run jobs + their CHARON_RUN_RESULT — from the live result log dir.
echo "### In-flight charon-run jobs (CHARON_RUN_RESULT)"
{
  JOBS_DIR="$PRIV_REPO/fleet/state/dogfood-eval/results"
  echo '```'
  if [ -d "$JOBS_DIR" ]; then
    # 8 most recent logs (mtime-sorted); show the JOB NAME + the CHARON_RUN_RESULT line.
    # If the log is still being written (no CHARON_RUN_RESULT line yet), label it IN-FLIGHT.
    find "$JOBS_DIR" -name '*.charon-run.log' -type f -printf '%T@ %p\n' 2>/dev/null \
      | sort -nr | head -8 | cut -d' ' -f2- | while read -r log; do
        name="$(basename "$log" .charon-run.log)"
        result="$(grep -E '^CHARON_RUN_RESULT=' "$log" 2>/dev/null | tail -1 | sed 's/^CHARON_RUN_RESULT=//')"
        if [ -n "$result" ]; then
          echo "$name  ->  $result"
        else
          echo "$name  ->  IN-FLIGHT (no CHARON_RUN_RESULT line yet)"
        fi
      done
  else
    echo "(no dogfood-eval/results dir at $JOBS_DIR)"
  fi
  echo '```'
} || echo "```\n(charon-run jobs probe failed)\n```"

# (3) provider-exhaustion-ledger.tsv tail — last 10 lines of the live ledger (after the header).
echo "### Provider-exhaustion-ledger tail (\`provider-exhaustion-ledger.tsv\`)"
{
  echo '```'
  LEDGER="$PRIV_REPO/fleet/provider-exhaustion-ledger.tsv"
  if [ -f "$LEDGER" ]; then
    head -1 "$LEDGER"
    tail -10 "$LEDGER"
  else
    echo "(ledger not found at $LEDGER — no provider-exhaustion telemetry yet)"
  fi
  echo '```'
} || echo "```\n(ledger probe failed)\n```"

# --- git state ---------------------------------------------------------------
echo "### Git"
echo '```'
{
  git -C "$CHARON_REPO" branch --show-current 2>/dev/null || echo "(charon repo not found)"
  echo
  git -C "$CHARON_REPO" status --short 2>/dev/null || echo "(charon status failed)"
  echo
  echo "--- last 10 commits ---"
  git -C "$CHARON_REPO" log --oneline -10 2>/dev/null || echo "(charon log failed)"
} || true
echo '```'

# --- open PRs ----------------------------------------------------------------
# The AUTHORITATIVE open-PR list is the GENERATED-STATE block above (both repos, timeout-bounded).
# This is a convenience raw dump; bound it with `timeout` so a gh/GitHub outage cannot HANG the
# whole handoff (2026-07-19 incident) — fail-soft to a note, never block.
echo "### Open PRs (raw — see GENERATED-STATE block above for the authoritative list)"
echo '```'
timeout "${HANDOFF_STATE_TIMEOUT:-15}" gh pr list --repo SLOP-Platform/charon --state open --json number,title,headRefName,state 2>/dev/null || echo "(gh unavailable / timed out — see GENERATED-STATE block above)"
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
if [ -n "${CHARON_GATE_ACTIVE:-}" ]; then
  # REENTRANCY GUARD (2026-07-15 fork-bomb incident): we are already running
  # INSIDE gate.sh (it runs the fleet test suite, and handoff-mechanize.test.sh
  # invokes this script). Re-running gate.sh here would recurse exponentially
  # (handoff->gate->test->handoff->...) and fork-bomb the box. Skip when nested.
  gate_out="(gate skipped: already inside a gate run — reentrancy guard, see gate.sh CHARON_GATE_ACTIVE)"
else
  gate_out="$( { FLEET="${FLEET:-/home/stack/charon-private/fleet}"; bash "$FLEET/gate.sh" 2>&1; } )" || GATE_RC=$?
fi
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

# --- foreman tier-health (auto) ----------------------------------------------
echo "### Foreman tier-health (auto)"
echo '```'
bash /home/stack/charon-private/fleet/foreman-cadence.sh handoff 2>&1 || true
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
