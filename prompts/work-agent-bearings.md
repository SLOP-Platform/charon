# WORK-AGENT-BEARINGS — give the dispatched agent real bearings, not just a title

## Why (verified in code on origin/master 2026-06-27 — do NOT re-derive)
When `charon work` dispatches a unit to the ACP agent, the agent receives **only the ticket title**
as its prompt. It cannot autonomously complete a real ticket from one line.

- `intake.py` builds each `PlanUnit` with `goal=item.title` (intake.py:536, :550) and **discards the
  ticket body/description**. The body is parsed only to scavenge inline-code `owns` paths
  (`_INLINE_CODE_RE` over `item.body`, intake.py:188) and to gate "too thin" items
  (intake.py:523-527) — its prose is never carried onto the unit.
- The ACP dispatch sends only the goal: `acp.py:170` → `"prompt": [{"type":"text","text":
  unit.goal}]` — a single line.
- The acceptance criteria (`accept`) run as the post-hoc gate but are **never shown to the agent**,
  so it can't aim at the checks it will be judged against.

## What to build
Carry the ticket **body/description** AND the **acceptance criteria** onto the unit and into the
ACP dispatch prompt, so the agent knows what to change, why, and exactly how it will be verified.

1. **intake.py** — add a field to `PlanUnit` (e.g. `context`/`body`) that preserves the ticket
   body/description (the prose currently discarded). Keep the existing title→goal and the inline
   `owns` scavenging unchanged.
2. **api.py** — propagate that field through the engine `Unit`/`WorkUnit` so it reaches the backend
   at dispatch (the goal field already flows; carry the body + accept alongside it). Make the
   minimal plumbing change; do not alter routing/scheduling behavior.
3. **adapters/acp.py** — build the dispatch prompt from goal + body + the acceptance criteria
   (the EXACT checks the gate runs), in generic, agent-agnostic prose. Example shape:
   `"<goal>\n\n<body>\n\nAcceptance — your work must satisfy:\n<accept checks>"`. No opencode- or
   provider-specific framing.

## Hard constraints (from the ticket)
- **Agent/provider-agnostic** — generic prompt text; do not name or special-case any agent.
- The acceptance criteria shown to the agent must be the **SAME** checks the gate runs — no
  divergence between what the agent is told and what it is judged on.
- **Do not leak secrets** into the prompt (no tokens/keys in the dispatched text).
- Product-clean (no SLOP/fleet/rig leak); privileged core stays **stdlib-only**.

## Acceptance
- `tests/test_intake.py` (or owned new test): a ticket with a body produces a `PlanUnit` that
  retains the body (not just the title); the "too thin" gate and `owns` scavenging still behave.
- `tests/test_work_bearings.py` (new, owned): the ACP dispatch prompt for a unit contains the
  goal, the body, AND the acceptance criteria text — assert at the dispatch seam (mirror how
  existing acp dispatch tests inspect the sent prompt). Assert no secret/token string is included.
- The accept checks shown == the checks the gate executes (one source of truth).

## CONSTRAINTS
Own ONLY: `src/charon/intake.py`, `src/charon/api.py`, `src/charon/adapters/acp.py`,
`tests/test_intake.py`, `tests/test_work_bearings.py`. Stdlib core only; no `pip install -e`; no
secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/WORK-AGENT-BEARINGS.md` (per-ticket fragment; NEVER the shared REVIEW-LOG.md).
Open a DRAFT PR (base master), run `submit.sh WORK-AGENT-BEARINGS`, then STOP — never merge. If a
fix genuinely needs a file outside owns, STOP and `release.sh WORK-AGENT-BEARINGS` with the reason.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
