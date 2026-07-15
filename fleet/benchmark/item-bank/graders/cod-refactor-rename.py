#!/usr/bin/env python3
"""Grader for item `cod-refactor-rename`.

Verifies the rename `cost_rank` -> `price_rank` is complete (every
call site updated, no stragglers) and that unrelated `cost_*` names
were NOT touched. OOB: runs the fixture's test suite.
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
    for f in ("config.py", "routing.py", "meter.py", "providers.py"):
        if not (snapshot / f).exists():
            return fail_closed(f"{f} missing in worktree")
    # Sanity: no source file should still reference the old name (the
    # only legitimate mention would be a literal "renamed from" doc
    # comment, which the task did not ask for and we reject).
    for f in ("config.py", "routing.py", "meter.py", "providers.py"):
        text = (snapshot / f).read_text(errors="ignore")
        if "cost_rank" in text:
            return fail_closed(f"{f} still references the old name `cost_rank`")
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "rename complete: cost_rank -> price_rank across all 4 files; unrelated cost_* untouched")
