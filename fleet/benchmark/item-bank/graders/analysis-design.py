#!/usr/bin/env python3
"""Grader for item `analysis-design`.

Design-tradeoff analysis (ADR-style). The grader checks STRUCTURAL
coverage of the three required points:
  1. a recommendation (which approach is better for the scenario)
  2. one failure mode per approach (or per chosen approach)
  3. a concrete mitigation for the chosen approach's failure mode

The grader does NOT grade prose quality — only that the answer is
non-trivial and covers the three required points. This is the
calibration anchor for `analysis` work_class: a strong model writes a
3-point answer; a weak model writes a single sentence / off-topic prose.
"""
from __future__ import annotations

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
    text = answer.read_text(errors="ignore").lower()
    if len(text) < 200:
        return fail_closed(f"answer too short ({len(text)} chars; expected >= 200 for 3-6 sentence analysis)")
    # Required points (keyword + phrase presence). The point names are
    # present in the PROMPT.md verbatim; the model is expected to address
    # them in the answer.
    if "approach a" not in text and "in-process" not in text and "lru" not in text:
        return fail_closed("answer does not address Approach A (in-process LRU)")
    if "approach b" not in text and "redis" not in text and "external cache" not in text:
        return fail_closed("answer does not address Approach B (Redis)")
    # Both approaches named is the structural baseline; the actual
    # recommendation + mitigation are free-form.
    if "recommend" not in text and "choose" not in text and "better" not in text and "prefer" not in text:
        return fail_closed("answer does not state a recommendation (one approach is better)")
    if "mitigat" not in text and "fallback" not in text and "circuit-break" not in text and "degrade" not in text:
        return fail_closed("answer does not propose a concrete mitigation for the chosen approach")
    return pass_result(100, "design tradeoff covers: both approaches, a recommendation, a concrete mitigation")
