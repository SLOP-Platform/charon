#!/usr/bin/env python3
"""Grader for item `general-tooluse`.

A minimal tool-use task. The grader checks (a) a TOOL_CALL line is
present, (b) the result in answer.txt is correct (= 32.0 for
(3 + 4) * 5 - 6 / 2). Calibration anchor for `general` work_class's
"tool-use" slice: a strong model emits a tool call AND a result; a
weak model skips the tool call.
"""
from __future__ import annotations

import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    if "TOOL_CALL" not in text:
        return fail_closed("answer.txt does not contain a TOOL_CALL line")
    # Find a number in the file. Acceptable anywhere — the task is
    # tool-use + correct-result, not a strict format. The grader is
    # tolerant of the model writing the result on the same line as the
    # tool call, or on a separate line, or in a comment.
    nums = re.findall(r"-?\d+(?:\.\d+)?", text)
    if not nums:
        return fail_closed("no number found in answer.txt")
    # Try each numeric token; the first one that == 32.0 (within float
    # tolerance) is the model's reported result.
    for n in nums:
        try:
            v = float(n)
        except ValueError:
            continue
        if abs(v - 32.0) < 1e-6:
            return pass_result(100, f"tool call present, correct result: {v}")
    return fail_closed(f"no token equal to 32.0 found; tokens: {nums}")
