#!/usr/bin/env python3
"""Grader for item `cod-regression-fix`.

Verifies the model fixed the regression in `backoff.clamp` (cap is
applied AFTER the jitter offset, not before) by making the seeded RED
test pass — and that the model did NOT touch the test to make it pass
(fix-don't-delete: the test is the spec).
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result, run_pytest  # noqa: E402

# Snapshot of the EXPECTED test_backoff.py contents (the spec). If the
# model's worktree test_backoff.py diverges from this snapshot, the model
# cheated by editing the test instead of the implementation. We check
# the FILE-WHOLE-IDENTICAL invariant, not the test passing (which would
# also pass after a cheating edit) — the FAIL-ON-REVERT for "fix-don't-
# delete" is the file identity check, not the test outcome.
EXPECTED_TEST = (
    "tests/test_backoff.py"
)


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    backoff = snapshot / "backoff.py"
    if not backoff.exists():
        return fail_closed("backoff.py missing in worktree")
    test = snapshot / EXPECTED_TEST
    if not test.exists():
        return fail_closed(f"{EXPECTED_TEST} missing in worktree")
    # The test was committed as the spec — verify it was NOT modified
    # by hashing the file the runner seeded (kept here as the canonical
    # spec text). Cheating on the test (delete/loosen) is the exact
    # attack vector fix-don't-delete exists to prevent.
    spec_text = (
        '"""test_backoff.py — SEEDED RED spec test. Do NOT modify.\n'
        "\n"
        "The test asserts the contract the FIX must satisfy: the cap is applied\n"
        "AFTER the jitter offset (not before). The current `backoff.clamp` does\n"
        "the opposite, so the test reds today. The model fixes backoff.py to\n"
        "make this test green — without modifying the test itself.\n"
        '"""\n'
        "from backoff import clamp\n"
        "\n"
        "\n"
        "def test_no_jitter_default_unchanged():\n"
        '    """The no-jitter path must keep its prior contract."""\n'
        "    assert clamp(10.0, 100.0) == 10.0\n"
        "    assert clamp(150.0, 100.0) == 100.0\n"
        "\n"
        "\n"
        "def test_jitter_under_cap():\n"
        '    """delay=10, jitter=0.5 -> jittered=15 -> below cap -> returns 15."""\n'
        "    assert clamp(10.0, 100.0, jitter=0.5) == 15.0\n"
        "\n"
        "\n"
        "def test_jitter_above_cap():\n"
        '    """delay=80, jitter=0.5 -> jittered=120 -> exceeds cap=100 -> returns 100.\n'
        "    This is the regression: previously the cap was applied to the\n"
        "    un-jittered delay, returning 80, and 80 + 80*0.5 = 120 was returned\n"
        "    unconstrained. The fix enforces the cap on the jittered value.\"\"\"\n"
        "    assert clamp(80.0, 100.0, jitter=0.5) == 100.0\n"
        "\n"
        "\n"
        "def test_jitter_at_cap_boundary():\n"
        '    """delay=66.66, jitter=0.5 -> jittered=100.0 (approx) -> at cap -> 100.\n'
        "    Tolerant of float noise: anything in [99.99, 100.0] is acceptable.\"\"\"\n"
        "    out = clamp(66.66, 100.0, jitter=0.5)\n"
        "    assert 99.99 <= out <= 100.0 + 1e-9, f\"got {out}, expected ~100\"\n"
    )
    actual_text = test.read_text(errors="ignore")
    if actual_text != spec_text:
        return fail_closed(
            "tests/test_backoff.py was MODIFIED (spec drift) — fix the implementation, "
            "not the test (fix-don't-delete)"
        )
    # Now run the test. It should pass after the fix; it red before.
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "regression fixed: cap applied after jitter; seeded test green and unmodified")
