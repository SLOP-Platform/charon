# DTC-1 — gate registry + self-validator

## Dependencies & sequence
**depends_on: NONE — Wave 1.** Owns `tools/gates.json` + `tools/check_gate_registry.py` ALREADY BUILT.
No file overlap with any other ticket → runs CONCURRENTLY with all Wave-1 tickets. Confirm files exist
and the checker passes clean.

## Why
`tools/gates.json` is the machine-readable register of every active validation rule (gates, checks,
structural rules, CI steps). The checker (`tools/check_gate_registry.py`) validates that every rule
has a living enforcer, that no two rules cover the same domain, and that `@covers:` annotations in
tool files match the registry. This is the source of truth for Rule 5 and Rule 6 — before writing any
new test or gate, consult this registry.

## What to build
- ALREADY BUILT. Verify:
  - `tools/gates.json` exists and contains entries for all existing gates
  - `tools/check_gate_registry.py` exists and passes clean (`python3 tools/check_gate_registry.py`)

## Acceptance
- `python3 tools/check_gate_registry.py` exits 0 with "check_gate_registry: OK"
- `tools/gates.json` is valid JSON and contains at least 10 gate entries
- All gate entries have id, domain, and enforcer fields

## CONSTRAINTS
Own ONLY: `tools/gates.json`, `tools/check_gate_registry.py`. Already built — confirm, don't create.
Stdlib core only; gate GREEN. Conventional commits; review note → `docs/review-log/DTC-1.md`.
