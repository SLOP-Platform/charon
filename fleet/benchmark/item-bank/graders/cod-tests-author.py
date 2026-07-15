#!/usr/bin/env python3
"""Grader for item `cod-tests-author`.

Verifies the model added the regression test for percent(part, 0) and
fixed the implementation so the test passes. OOB: runs pytest.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result, run_pytest  # noqa: E402


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    for f in ("calc.py", "tests/test_calc.py"):
        if not (snapshot / f).exists():
            return fail_closed(f"{f} missing in worktree")
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "regression test added + implementation fixed: percent(5, 0) raises ZeroDivisionError")
