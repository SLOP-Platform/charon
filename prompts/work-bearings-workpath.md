# WORK-BEARINGS-WORKPATH — carry body+accept through the `charon work` path to the agent

## Why (completes WORK-AGENT-BEARINGS, which only did the groundwork)
WORK-AGENT-BEARINGS (merged) added `acp._build_prompt` (goal + body + acceptance) and a
`RichWorkUnit`, and wired them into `charon run` (`api.run_task`). BUT the `charon work` path — the
actual target — still dispatches a PLAIN unit, so the agent there still gets only the title:
- `engine/board.py` `Unit` has **no `body` field** (intake writes `body` into plan.json via
  `PlanUnit.to_dict`, but the board Unit never reads it back).
- `engine/scheduler.py` `CoordinatorRunner` (~line 142) and `cli.py` `_ReviewingRunner` (added by
  WORK-LAND-PR) both build `WorkUnit(task_id=unit.id, goal=unit.goal)` — no body, no accept.
So `_build_prompt`'s `getattr(unit, "body"/"accept_text", "")` returns empty → title only.

## What to build
Carry the ticket body + acceptance criteria from the engine Unit, through BOTH work-path runners,
into the dispatched unit so `_build_prompt` emits full bearings in `charon work`.
1. **engine/board.py** — `Unit` gains a `body: str = ""` field, populated when the board loads
   units from plan.json (the field is already present in the plan via intake's `to_dict`).
2. **types.py** — add optional `body: str = ""` and `accept_text: str = ""` to the base `WorkUnit`.
   **Do NOT make the engine import `api.RichWorkUnit`** — that would create an engine→orchestrator
   dependency and trip the boundary guard (`tools/check_boundary.py`). Put the fields on the base
   `WorkUnit` in `types.py` so the engine layer stays clean. (`api.RichWorkUnit` may then be
   simplified/kept as a thin alias — your call, but don't break `run_task`.)
3. **engine/scheduler.py** + **cli.py `_ReviewingRunner`** — build the WorkUnit with
   `body=unit.body, accept_text="\n".join(unit.accept)` (the SAME accept checks the gate runs — one
   source of truth, no divergence).

## Acceptance
- `tests/test_work_bearings.py` (extend): an END-TO-END `charon work` dispatch (drive a unit through
  the runner, NOT a hand-built RichWorkUnit) sends a `session/prompt` whose text contains the goal,
  the body, AND the acceptance criteria. This is the end-to-end coverage the groundwork lacked.
- The accept text shown == the unit's `accept` checks the gate executes.
- No secret/token strings in the prompt. `charon run` (`run_task`) bearings still work.
- `tools/check_boundary.py src` stays GREEN (engine must not import the orchestrator/api layer).

## CONSTRAINTS
Own ONLY: `src/charon/engine/board.py`, `src/charon/engine/scheduler.py`, `src/charon/cli.py`,
`src/charon/types.py`, `tests/test_work_bearings.py`. Stdlib core only; no `pip install -e`; no
secrets committed. Gate GREEN every commit:
`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`.
Conventional commits; new behavior ships with its test in the same commit. Review note →
`docs/review-log/WORK-BEARINGS-WORKPATH.md` (per-ticket fragment; NEVER the shared REVIEW-LOG.md).
Open a DRAFT PR (base master), run `submit.sh WORK-BEARINGS-WORKPATH`, then STOP — never merge.

## ⚠ SEQUENCING — PARKED until WORK-LAND-PR merges
Owns `cli.py` (and must modify the `_ReviewingRunner` that WORK-LAND-PR introduces) → cannot run
concurrently with LAND-PR. `depends_on: WORK-LAND-PR`. Unpark
(`mv WORK-BEARINGS-WORKPATH.md.parked WORK-BEARINGS-WORKPATH.md`) after #69 merges.

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
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
