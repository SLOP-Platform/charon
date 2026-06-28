# Review note — WORK-AGENT-BEARINGS

## Decision: RichWorkUnit subclass instead of modifying types.py

`types.py` is not in `owns:`, so `WorkUnit` cannot be modified. Instead, `api.py`
defines `RichWorkUnit(WorkUnit)` — a frozen dataclass subclass adding `body: str`
and `accept_text: str` with empty defaults. This is backward-compatible: any existing
`WorkUnit` passed to `acp.py:dispatch()` still works (goal-only prompt).

`acp.py:_build_prompt()` uses `getattr(unit, "body", "")` / `getattr(unit,
"accept_text", "")` to avoid importing from `api.py` (which would create a circular
import, since `api.py` already imports `AcpBackend`).

## Coverage

- `test_intake.py`: body retention, too-thin gate unaffected, owns-scavenging
  unaffected (3 new tests, 31 pre-existing).
- `test_work_bearings.py` (new): dispatch-seam tests via subprocess stub (mirrors
  `test_tier_lifecycle.py`); unit tests for `_build_prompt` in isolation; backward-
  compat test for plain `WorkUnit`; no-secrets assertion.

## Board/scheduler path

`engine/scheduler.py` creates plain `WorkUnit` (not `RichWorkUnit`) — not in `owns:`.
The board path therefore sends goal-only prompts. To thread body+accept through the
board path, `engine/board.py` and `engine/scheduler.py` would also need changes (those
are separate ticket scope). This ticket covers the `run_task` / direct-dispatch path
and the `intake.py` → `PlanUnit.body` preservation, which are the scoped deliverables.
