# OBS-CAPTURE — persist each unit's ACP agent transcript (WORK-OBSERVABILITY follow-on)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `adapters/acp.py`, `ports/backend.py`, `adapters/mock.py`,
`coordinator.py`, `decompose.py`, plus test. DISJOINT from every other backlog ticket (none of these
files are owned by WCI, ORCH-ROUTE, etc.) → safe to run CONCURRENTLY with all other Wave-1 tickets.
A fresh Charon can claim it immediately.

## Why
`charon work` discards the agent's output: `adapters/acp.py` spawns the ACP child with
`stderr=subprocess.DEVNULL` and does not relay tokens, so the only record of what the agent did is
the commit diff + the terse note. WORK-OBSERVABILITY (#73) added live progress + `charon runs` but
explicitly deferred capturing the agent's own output.

## What to build
Persist each unit's ACP transcript/output to a per-unit log under the unit's `.charon/<id>/` dir
(e.g. `.charon/<id>/agent.log`) so a user can inspect what the agent actually did. Capture the
child's stderr (today → DEVNULL) and, if cheap, the ACP message stream, to that file. Off nothing
by default — this is local disk only, opt-in to read.

## Scope decision (DS-PLAN-REVIEW, operator-approved 2026-06-28) — state_dir seam
Thread a `state_dir: Path` parameter into `AgentBackend.dispatch()` so `AcpBackend` can derive the
durable per-unit log path as `<state_dir>/<task_id>/agent.log`. The seam is minimal:

1. Add `state_dir: Path` to the protocol signature in `ports/backend.py`.
2. Accept it in `AcpBackend.dispatch()` (`adapters/acp.py`) and use `state_dir` + `unit.task_id`
   to open the log file.
3. Accept it in `MockBackend.dispatch()` (`adapters/mock.py`) — ignore; mock doesn't log.
4. Pass `state_dir=ledger.root.parent` at the two `dispatch()` call sites in `coordinator.py` and
   `decompose.py`.

None of these files are owned by WCI (`engine/{reconcile,scheduler,board}.py`), so no collision.
The scheduler path is NOT touched — it delegates to `coordinator.run()` which already has the
ledger in scope. Do NOT add cost to the gateway hot path.

## Acceptance
- A `charon work` unit run leaves a non-empty `.charon/<id>/agent.log` with the agent's output;
  absence of the dir doesn't crash. No secrets/tokens written to the log. Existing acp tests GREEN.

## CONSTRAINTS
Own ONLY: `src/charon/adapters/acp.py`, `src/charon/ports/backend.py`, `src/charon/adapters/mock.py`,
`src/charon/coordinator.py`, `src/charon/decompose.py`, `tests/test_acp_capture.py`. Do NOT touch
`scheduler.py`/`cli.py`. Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/OBS-CAPTURE.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked).

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
