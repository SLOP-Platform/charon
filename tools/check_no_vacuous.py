#!/usr/bin/env python3
"""No-vacuous gate — 0 tests/0 gates discovered = RED.

Adapter around KSF's ``no_vacuous`` detector (vendored verbatim in
``tools/_vendor/ksf_gates/no_vacuous.py``). KSF's detector runs
``pytest --collect-only`` to verify tests exist, and scans the gates
directory to verify gates exist. An empty suite (0 tests or 0 gates)
fails rather than silently passing.

Exit 0 on clean (tests discovered > 0, gates discovered > 0), 1 on
vacuous-zero.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_gates.no_vacuous import check_no_vacuous  # noqa: E402
from tools.gate_contract import emit_work_units  # noqa: E402


def main() -> int:
    shim_db_path = REPO_ROOT / "_ksf_shim" / "state.db"
    result = check_no_vacuous(db_path=shim_db_path, manifest={}, modules=[])

    # Work units = gates discovered + test files counted
    gates_dir = REPO_ROOT / "tools" / "_vendor" / "ksf_gates"
    gate_count = len([
        p for p in gates_dir.glob("*.py")
        if not p.name.startswith("_") and not p.name.startswith("test_redproof")
    ]) if gates_dir.exists() else 0
    # Add rough count of test files as work units
    tests_dir = REPO_ROOT / "tests"
    test_count = len(list(tests_dir.rglob("test_*.py"))) if tests_dir.exists() else 0
    emit_work_units(gate_count + test_count)

    for msg in result.messages:
        print(msg)

    if result.passed:
        print("check_no_vacuous: OK")
        return 0

    print("\nFAIL: vacuous run (0 tests or 0 gates discovered)", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
