# TOOL-REPAIR-MUTATING — review notes

## Fix

Added the `is_mutating` marker as a first-class gate to `tool_repair.py` so
the `allow_mutating` flag is no longer a NO-OP. The module still does NOT
classify calls as mutating; the caller (deferred proxy wiring) supplies the
marker from config and the registry.

## Marker sources (either is honored, schema wins)

- **Top-level schema marker**: `schema["is_mutating"] = True/False`.  This is
  the registry's authoritative declaration that ALL calls of a given tool are
  mutating (e.g. filesystem write tools, code exec tools).
- **Per-call marker on the tool_call dict**: `tool_call["is_mutating"]` is
  forwarded to `repair_arguments` as the `is_mutating` kwarg, allowing
  per-call classification when a single tool name can be invoked both
  mutating and non-mutatingly.
- **Schema wins over kwarg** when both are present — the schema is the
  registry's source of truth and prevents a caller-side mistake from
  under-repairing a mutating call.

## Gate semantics

- `allow_mutating=False` AND call is mutating  ->  short-circuit, return
  original `arguments` string unchanged, no rules fire, no counters move.
- `allow_mutating=True`  OR  call is non-mutating  ->  normal repair flow.

The short-circuit returns a `RepairResult(arguments=arguments, changed=False,
fired_rules=[])` with `unrepaired=False` — the call was *intentionally*
passed through, not a failed repair. Counters staying at zero lets the
operator see at a glance that the gate, not the rules, suppressed repair.

## Why the kwarg exists alongside the schema marker

`repair_tool_calls` plumbs the per-call marker through automatically so the
common case (call-site already knows the call's mutating status) needs no
schema declaration. The schema marker remains the safer default for
shared/global schemas.

## No design judgement

The fix is mechanical and self-contained. No proxy wiring, no caller-side
classification logic, no policy/registry work — all of that belongs to the
deferred wiring ticket that consumes this gate.
