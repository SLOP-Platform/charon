#!/usr/bin/env python3
"""Grader for item `creative-structured`.

Structured-generation task. The grader parses the answer as JSON and
verifies the structural schema. The actual content is NOT graded —
a strong model produces a coherent product description; a weak model
produces something that doesn't parse or doesn't fit the schema. The
calibration anchor for `creative` work_class: schema compliance, not
prose.
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result  # noqa: E402


def _extract_json(text: str) -> dict | None:
    """Find the first {...} block that parses as JSON. Tolerates
    surrounding prose (some chatty models wrap the JSON in a sentence)."""
    # First try: the whole file.
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass
    # Second try: a JSON object span.
    for m in re.finditer(r"\{.*\}", text, re.DOTALL):
        candidate = m.group(0)
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            continue
    return None


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    answer = snapshot / "answer.txt"
    if not answer.exists():
        return fail_closed("answer.txt missing in worktree")
    text = answer.read_text(errors="ignore")
    data = _extract_json(text)
    if data is None:
        return fail_closed("answer.txt does not contain a parseable JSON object")
    for key in ("name", "tagline", "audience"):
        v = data.get(key)
        if not isinstance(v, str) or not v.strip():
            return fail_closed(f"field {key!r} must be a non-empty string")
    feats = data.get("features")
    if not isinstance(feats, list) or len(feats) != 3:
        return fail_closed(f"field 'features' must be a list of exactly 3 items, got {type(feats).__name__}")
    for i, f in enumerate(feats):
        if not isinstance(f, str) or not f.strip():
            return fail_closed(f"feature {i} must be a non-empty string")
    return pass_result(100, "structured JSON output: name + tagline + audience + 3 features, all valid")
