#!/usr/bin/env python3
"""Grader for item `general-followinstr`.

Trivial exact-match on a 4-line instruction-following task. Calibration
anchor for `general` work_class: a strong model follows multi-step
instructions; a weak model drops lines or reorders.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


EXPECTED = ("hello world", "goodbye world", "42", "done")


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    lines = [ln.strip() for ln in text.splitlines() if ln.strip()]
    if lines != list(EXPECTED):
        return fail_closed(f"expected {list(EXPECTED)}, got {lines}")
    return pass_result(100, "exact 4-line instruction-follow match")
