# TOOL-REPAIR-MUTATING — Fix the allow_mutating NO-OP gate

## Context
The tool_repair module's `allow_mutating` flag is currently a NO-OP — it repairs mutating
tool calls regardless of the flag's value (HANDOFF-2026-07-04-v2 §3). MUST be fixed BEFORE
tool_repair is wired into the proxy.

## Fix
Add an `is_mutating` marker to the tool-call schema so the `allow_mutating` flag can
short-circuit: when `allow_mutating=False` and the tool call is mutating, skip repair
(pass through unchanged). When `allow_mutating=True` or the call is non-mutating, repair
normally.

The tool_repair.py module + tests already exist on `feat/tool-repair` (local commit
e06b193). This ticket may resolve by either:
(a) landing that branch's content via PR (preferred — it also has quota.py), or
(b) cherry-picking just the mutating-gate fix.

## Dependencies & sequence
No depends_on. Small, self-contained in tool_repair.py.

## Gate
`PYTHONPATH=src python3 -m pytest tests/test_tool_repair.py -v -q ; ruff check ; mypy src
tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`
