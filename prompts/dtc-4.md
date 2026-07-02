# DTC-4 — unified `charon gate` command

## Dependencies & sequence
**depends_on: DTC-1 — Wave 1, after DTC-1.** Depends on DTC-1 (gate-registry) so the gate-registry
checker exists and can be included in the unified gate. Owns `cli.py`, `check_boundary.py`,
`check_version.py`, and `.github/workflows/ci.yml`. DISJOINT from all other Wave-1 tickets (no
overlap on these files) → safe to run CONCURRENTLY with DTC-2 and DTC-5.

## Why
The CI pipeline runs 7 sequential steps for lint/type/structural checks: ruff check, mypy src,
mypy tests, boundary check, version check, pytest, and gate-registry. Each step parses the same
source files independently — 3-4 redundant AST traversals. Consolidating these into a single
`charon gate` subcommand that shares parse results is faster, reduces CI YAML boilerplate, and
gives developers one command to run locally instead of remembering 4-5 separate invocations.

## What to build
- Add a `charon gate` subcommand to `src/charon/cli.py` that runs, in order:
  1. `ruff check` (lint)
  2. `mypy src tests` (type checking)
  3. Boundary check (the logic from `tools/check_boundary.py`)
  4. Version check (the logic from `tools/check_version.py`)
  5. Gate registry check (the logic from `tools/check_gate_registry.py`)
  Share AST parse results where possible. The individual scripts in `tools/` remain callable
  standalone — `charon gate` just orchestrates them, it doesn't inline their logic.
- Refactor `tools/check_boundary.py` and `tools/check_version.py` to expose their core check logic
  as importable functions (e.g., `check_boundary(src_dir) -> bool`, `check_version() -> bool`).
  Keep their `if __name__ == "__main__"` entry points so they still work as standalone scripts.
- `charon gate` calls these functions, prints a unified summary, and exits with status 0 only if
  all checks pass. If any check fails, print which check failed and exit non-zero.
- Create or update `.github/workflows/ci.yml`: replace the 7 sequential steps with a single
  `charon gate` step + a separate `pytest` step.
- Add `charon gate` as a console_scripts entry point in `pyproject.toml` if needed.

## Acceptance
- `python3 tools/check_boundary.py src && python3 tools/check_version.py` still pass (standalone
  scripts not broken).
- `python3 -m charon gate` passes on a clean codebase; fails with a clear message if ruff, mypy,
  boundary, version, or gate-registry checks fail.
- CI runs `charon gate` as one step instead of the 7 separate check steps.
- `.github/workflows/ci.yml` is minimal and correct.

## CONSTRAINTS
Own ONLY: `src/charon/cli.py`, `tools/check_boundary.py`, `tools/check_version.py`,
`.github/workflows/ci.yml`. Do NOT touch `pyproject.toml` or any other source/test files.
Stdlib core only; gate GREEN (`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ;
python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/DTC-4.md`. BACKLOG (parked).
