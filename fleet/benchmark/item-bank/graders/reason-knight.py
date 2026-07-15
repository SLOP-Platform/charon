#!/usr/bin/env python3
"""Grader for item `reason-knight`.

Verifies the model's 8-queens solution: 8 distinct column placements,
no diagonal conflicts. The grader computes the constraint check itself
— never trusts the model's prose.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


def _is_valid_solution(cols: list[int]) -> bool:
    if len(cols) != 8:
        return False
    if sorted(cols) != list(range(1, 9)):
        return False
    for r1 in range(8):
        for r2 in range(r1 + 1, 8):
            if abs(cols[r1] - cols[r2]) == abs(r1 - r2):
                return False
    return True


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    cols: list[int] = []
    for line in text.splitlines():
        s = line.strip()
        if not s:
            continue
        try:
            cols.append(int(s))
        except ValueError:
            # tolerate prose lines, but stop at the first 8 ints
            if len(cols) >= 8:
                break
            continue
        if len(cols) >= 8:
            break
    if len(cols) != 8:
        return fail_closed(f"expected 8 column integers, got {len(cols)}")
    if not _is_valid_solution(cols):
        return fail_closed(f"8-queens constraint violated by {cols}")
    return pass_result(100, f"valid 8-queens solution: {cols}")
