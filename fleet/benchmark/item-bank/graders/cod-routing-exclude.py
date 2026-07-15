#!/usr/bin/env python3
"""Grader for item `cod-routing-exclude`.

Verifies the model added a vision-aware HARD exclusion to
`forward_with_failover`: image requests narrow to vision-capable routes
and raise NoVisionRouteError when no such route exists; text requests
keep the existing reasoning-soft-fallback path unchanged.
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
    if not (snapshot / "forwarder.py").exists():
        return fail_closed("forwarder.py missing in worktree")
    if not (snapshot / "types.py").exists():
        return fail_closed("types.py missing in worktree")
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "vision-aware exclusion correct: image->vision-only, no-vision->raise, text unaffected")
