# WORK-BEARINGS-WORKPATH — carry body+accept through the `charon work` path

## What
WORK-AGENT-BEARINGS added `acp._build_prompt` (goal + body + acceptance) and wired
it into `charon run` (`api.run_task` via `RichWorkUnit`). But the `charon work`
path still dispatched a PLAIN `WorkUnit`, so `_build_prompt`'s
`getattr(unit, "body"/"accept_text", "")` came back empty → the work agent got the
title alone. This ticket carries the bearings the whole way through the work path.

## Changes
- **types.py** — `body` and `accept_text` moved onto the base `WorkUnit` (defaults
  `""`). The engine work path can now populate them WITHOUT importing
  `api.RichWorkUnit`, so the engine→orchestrator boundary guard
  (`tools/check_boundary.py`) stays green. `api.RichWorkUnit` is left untouched
  (out of `owns:`); it still subclasses `WorkUnit`, redeclares the same two fields
  with identical defaults, and `run_task` is unaffected (full suite green).
- **engine/board.py** — `Unit` gains `body: str = ""`, round-tripped through
  `to_dict`/`from_dict` so the board reads back the prose intake already writes
  into plan.json via `PlanUnit.to_dict`.
- **engine/scheduler.py** `CoordinatorRunner` + **cli.py** `_ReviewingRunner` —
  both now build `WorkUnit(..., body=unit.body, accept_text="\n".join(unit.accept))`.

## One source of truth
`accept_text` is `"\n".join(unit.accept)` — the SAME `accept` list the gate turns
into `AcceptanceCheck`s. What the agent is shown can never diverge from what is
judged.

## Test (end-to-end, the coverage the groundwork lacked)
`tests/test_work_bearings.py` extended: a board `Unit` is driven through the real
work-path `CoordinatorRunner` (NOT a hand-built `RichWorkUnit`) with a capture-stub
ACP backend. The captured `session/prompt` text is asserted to contain goal + body
+ each accept check. Plus a no-secrets check and a body-less backward-compat case.

## Boundary
`check_boundary.py src` green — the engine layer never imports `api`/the
orchestrator; the new fields live on core `types.WorkUnit`.
