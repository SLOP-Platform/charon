#!/usr/bin/env python3
"""Grader for item `reason-coin`.

The 30-coin two-pass flip problem. A coin i is flipped once for each
divisor of i in {2, 3}. So coin i's final state = heads if (the number
of flips i receives) is even, tails if odd. We can compute the answer
ourselves (so we don't trust the model's prose) and check it.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


def _compute_correct():
    """Compute the expected answer: positions that are heads-up after
    the two-pass flip of 30 initially-heads coins."""
    flips = {i: 0 for i in range(1, 31)}
    for i in range(2, 31, 2):
        flips[i] += 1
    for i in range(3, 31, 3):
        flips[i] += 1
    heads = sorted(p for p, f in flips.items() if f % 2 == 0)
    return heads


EXPECTED_POSITIONS = _compute_correct()
EXPECTED_COUNT = len(EXPECTED_POSITIONS)


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    # Parse the positions line + count line. Tolerant of formatting.
    positions_line = ""
    count_line = ""
    for line in text.splitlines():
        low = line.strip().lower()
        if low.startswith("positions"):
            positions_line = line
        elif low.startswith("count"):
            count_line = line
    if not positions_line or not count_line:
        return fail_closed("answer.txt must contain 'positions:' and 'count:' lines")
    # Parse positions.
    try:
        nums = [int(x.strip()) for x in positions_line.split(":", 1)[1].split(",") if x.strip()]
    except ValueError as exc:
        return fail_closed(f"could not parse positions: {exc!r}")
    nums_sorted = sorted(set(nums))
    if nums_sorted != EXPECTED_POSITIONS:
        return fail_closed(
            f"positions mismatch: expected {EXPECTED_POSITIONS}, got {nums_sorted}"
        )
    # Parse count.
    try:
        count = int(count_line.split(":", 1)[1].strip())
    except ValueError as exc:
        return fail_closed(f"could not parse count: {exc!r}")
    if count != EXPECTED_COUNT:
        return fail_closed(f"count mismatch: expected {EXPECTED_COUNT}, got {count}")
    return pass_result(100, f"exact match: {EXPECTED_COUNT} heads at {EXPECTED_POSITIONS[:5]}...")
