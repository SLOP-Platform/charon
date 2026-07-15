#!/usr/bin/env python3
"""Grader for item `cod-bugfix-typo`.

Verifies that the model fixed the misspelled enum value `'chearp'` to
`'cheap'` and did not break the other enum values. OOB: runs the
fixture's test suite in the model's worktree. Fails CLOSED on any
grader-side error.
"""
from __future__ import annotations

import sys
from pathlib import Path

# Make the item-base importable regardless of CWD the daemon launched us with.
HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result, run_pytest  # noqa: E402


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    app_py = snapshot / "app.py"
    if not app_py.exists():
        return fail_closed(f"app.py missing in worktree: {app_py}")
    # The simplest direct check first: the misspelling must be gone.
    text = app_py.read_text(errors="ignore")
    if "chearp" in text:
        return fail_closed("app.py still contains the misspelled 'chearp'")
    if '"cheap"' not in text and "'cheap'" not in text:
        return fail_closed("app.py does not contain the corrected 'cheap' value")
    # Run the fixture's pytest to confirm the enum still resolves + classifies.
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "typo fixed: 'chearp' -> 'cheap'; pytest green")
