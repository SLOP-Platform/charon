# WIRE-MOCKLINT-ENFORCE — Review Log

## Summary

Promotes rule (e) self-mirroring/fabricated-mock from WARNING to HARD ERROR in
`tools/check_test_patterns.py`, fulfilling Defect B split from TEST-HARDEN-CONTRACT
(PR #92). Adds an allow-pragma (`# check-test-patterns: allow-self-mirroring-mock`)
for pre-existing legitimate exceptions. Adds a cross-check in `gate_runner.py` that
every `ci_step:true` entry in `gates.json` is wired into CHECKS.

## Changes

### DO-1 — Rule (e) is now a hard error
- `tools/check_test_patterns.py`: Rule (e) violations now appear in `errors`, not
  `warnings`, and cause exit code 1 regardless of `--strict`.
- Allow-pragma `# check-test-patterns: allow-self-mirroring-mock` suppresses the
  rule per-file.

### DO-2 — Already done (PR #119 side-effect)
- `check_test_patterns.py` was already wired into `gate_runner.CHECKS`.

### DO-3 — Pre-existing violators annotated with pragma
- 5 files received the allow-pragma (they test routing/gateway logic, not response
  contracts, so the pragma is appropriate):
  - `tests/test_agent_launch_routing.py`
  - `tests/test_capability_routing.py`
  - `tests/test_fallback_provider.py`
  - `tests/test_forwarder_retry_transient.py`
  - `tests/test_gateway.py`
- Note: `tests/test_proxy_server.py` was already clean (has `"choices" in body`
  top-level contract assertion).

### DO-4 — Gate-registry vs CHECKS cross-check
- `src/charon/gate_runner.py`: New `_verify_gate_registry_wired()` runs before
  the CHECKS loop and fails if any `ci_step:true` entry (except `charon-gate`
  itself) whose enforcer starts with `tools/` is not wired into CHECKS.

### Test update
- `tests/test_check_test_patterns.py`: Updated the fail-on-revert test to expect
  rule (e) as an ERROR rather than a warning.

## Scope note

Changed files outside `owns:` (test pragmas + test update) — all necessary for the
rule promotion to land cleanly without breaking CI. No other ticket owns these files.

## Verification

All gates pass:
- Ruff: clean
- Mypy: no issues
- Boundary: OK
- Version: OK
- Check gate registry: OK
- Test patterns: 0 errors, 1253 warnings (pre-existing docstring/param-ratio debt)
- Pytest: 1803 passed, 1 xfailed, 1 xpassed
- Gate registry cross-check: OK
