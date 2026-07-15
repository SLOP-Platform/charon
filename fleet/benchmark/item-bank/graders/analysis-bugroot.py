#!/usr/bin/env python3
"""Grader for item `analysis-bugroot`.

Bug root-cause analysis. The grader checks STRUCTURAL coverage of three
required points: a plausible root cause, a verification method, a fix
direction. Prose quality is not graded; the analysis must be
non-trivial and cover the three points.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


# Plausible root-cause vocabulary the model might use. The grader does
# NOT require any specific cause (the bug is hypothetical); it requires
# a TESTABLE mechanism + a verification + a fix. This is the
# calibration anchor for `analysis` work_class: a strong model names a
# specific mechanism; a weak model writes "probably an upstream issue".
ROOT_CAUSE_KEYWORDS = (
    "timeout", "token", "retry", "buffer", "context window", "max_tokens",
    "rate limit", "throttl", "pool", "connection", "header", "payload",
    "size", "limit", "exceed", "truncat", "encoding", "stream", "race",
)


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore").lower()
    if len(text) < 200:
        return fail_closed(f"answer too short ({len(text)} chars; expected >= 200)")
    # Point 1: a testable mechanism. At least one of the keyword set.
    if not any(k in text for k in ROOT_CAUSE_KEYWORDS):
        return fail_closed(
            "answer does not name a specific mechanism (expected one of: "
            "timeout, token limit, retry, buffer, context window, rate limit, "
            "throttle, pool, header, payload size, etc.)"
        )
    # Point 2: a verification method.
    if not any(k in text for k in ("log", "metric", "repro", "test", "check", "verify", "inspect", "trace")):
        return fail_closed("answer does not describe a verification method (log, metric, repro, test, ...)")
    # Point 3: a fix direction.
    if not any(k in text for k in ("fix", "increase", "add ", "lower", "clamp", "paginate", "chunk", "split", "retry", "fallback")):
        return fail_closed("answer does not describe a fix direction (clamp, paginate, retry, fallback, ...)")
    return pass_result(100, "root-cause analysis covers: specific mechanism, verification method, fix direction")
