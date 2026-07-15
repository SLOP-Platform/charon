#!/usr/bin/env python3
"""Grader for item `reason-lcm`.

Exact-match on a small numerical reasoning task. The grader scans the
last non-empty line of the worktree's `answer.txt` for the first run
of digits and compares to the expected value (120 = smallest multiple
of lcm(6,15) = 30 strictly > 100).
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402

EXPECTED = "120"


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    # First run of digits in the model's reply.
    m = re.search(r"-?\d+", text or "")
    if not m:
        return fail_closed("no digit found in answer.txt")
    got = m.group(0)
    if got == EXPECTED:
        return pass_result(100, f"exact match: {got}")
    return fail_closed(f"expected {EXPECTED}, got {got!r}")
