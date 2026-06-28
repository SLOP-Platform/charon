# OBS-UI — surface work/board state in a UI (WORK-OBSERVABILITY follow-on)

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `proxy_server.py` + new `console_work.py` (+ test). These are
DISJOINT from every other backlog ticket → safe to run CONCURRENTLY with all other Wave-1 tickets. A
fresh Charon can claim it immediately, in parallel. (If implementation forces a `cli.py` touch,
STOP — that would overlap WCI/other cli.py work and must be sequenced.)

## Why
`charon work` state is only visible via the CLI (`charon runs`, `charon ledger <id>`) and raw
`.charon` files. The gateway web console shows ONLY gateway traffic; the Mode-B dashboard
(`python -m charon.service`) exists but is wired to `run_task`, not the `work` engine, and isn't
reachable from a `charon` subcommand.

## Decision (settled for this ticket — gateway-first, anti-dilution)
Add a **read-only work/board panel to the existing gateway web console**, served on a SEPARATE
console route that reads `.charon` run state on demand. It is a single pane the user already has.
**Hard anti-dilution rule:** this must NOT touch or add cost to the per-request gateway hot path —
it's a distinct read-only endpoint, gated/optional, that loads work state lazily.
(Alternative, if the console route proves wrong: wire the Mode-B `charon.service` dashboard to the
work engine + expose it via a `charon` subcommand. Pick the console-panel first; note in the
review-log if you switch and why.)

## What to build
A console route (e.g. `/console/work` or a panel in the existing console) that renders the current
run(s): per-unit status / checkpoints / land decision / PR — reading the same `.charon` state
`charon runs` aggregates. Read-only; no mutation; no secrets rendered.

## Acceptance
- Hitting the work panel/endpoint returns the current run rollup (mock `.charon` state in the test).
- The per-request gateway path is byte-for-byte unchanged (assert no new work on the hot path).
- No token/secret rendered. Existing proxy_server tests GREEN.

## CONSTRAINTS
Likely owns: `src/charon/proxy_server.py` (+ a new `src/charon/console_work.py` module if the panel
is sizeable) + `tests/test_console_work.py`. Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/OBS-UI.md`. Draft PR, `submit.sh`, STOP.
BACKLOG (parked). Branch `feat/obs-ui`. NOTE: if it touches `cli.py`, sequence vs any live cli.py ticket.
