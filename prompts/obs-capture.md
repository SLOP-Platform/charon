# OBS-CAPTURE — persist each unit's ACP agent transcript (WORK-OBSERVABILITY follow-on)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `adapters/acp.py` (+ its test) ONLY; deliberately scoped off
`scheduler.py`/`cli.py` so it does NOT collide with WCI. Its owns are DISJOINT from every other
backlog ticket → safe to run CONCURRENTLY with all other Wave-1 tickets. A fresh Charon can claim it
immediately, in parallel, with no risk of stepping on another ticket's files.

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

## Scope decision (optimization pass) — acp.py ONLY
Derive the per-unit log path from the **worktree** `acp._start` already receives (e.g.
`<worktree>/.charon/agent.log` or alongside the unit's state dir) — do NOT thread a new arg through
`scheduler.py`/`cli.py`. This keeps the ticket's sole owned file `adapters/acp.py`, avoiding a
collision with WCI (which owns `scheduler.py`). Keep it minimal; do NOT add cost to the gateway path.

## Acceptance
- A `charon work` unit run leaves a non-empty `.charon/<id>/agent.log` with the agent's output;
  absence of the dir doesn't crash. No secrets/tokens written to the log. Existing acp tests GREEN.

## CONSTRAINTS
Own ONLY: `src/charon/adapters/acp.py`, `tests/test_acp_capture.py` (log path derived from the
worktree — do NOT touch scheduler.py/cli.py). Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/OBS-CAPTURE.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked).
