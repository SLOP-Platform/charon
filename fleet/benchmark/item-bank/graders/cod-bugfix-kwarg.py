#!/usr/bin/env python3
"""Grader for item `cod-bugfix-kwarg`.

Verifies the model added a `force_refresh` keyword-only parameter to
`apply_to_env` with the correct default + behavior, did not break the
default path, and did not weaken the sensitive-env skip list.
"""
from __future__ import annotations

import inspect
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed, pass_result, run_pytest  # noqa: E402


def grade(snapshot: Path, unit_id: str) -> dict:
    if not snapshot.exists():
        return fail_closed(f"snapshot dir does not exist: {snapshot!r}")
    secrets_py = snapshot / "secrets.py"
    if not secrets_py.exists():
        return fail_closed("secrets.py missing in worktree")
    # Direct check on the signature: force_refresh must be keyword-only with default False.
    try:
        sys.path.insert(0, str(snapshot))
        import secrets as secrets_mod  # type: ignore
        sys.path.pop(0)
    except Exception as exc:  # noqa: BLE001
        return fail_closed(f"could not import secrets.py: {exc!r}")
    try:
        sig = inspect.signature(secrets_mod.apply_to_env)  # type: ignore[attr-defined]
    except (TypeError, ValueError) as exc:
        return fail_closed(f"apply_to_env signature unreadable: {exc!r}")
    if "force_refresh" not in sig.parameters:
        return fail_closed("apply_to_env() has no `force_refresh` parameter")
    p = sig.parameters["force_refresh"]
    if p.kind is not inspect.Parameter.KEYWORD_ONLY:
        return fail_closed("`force_refresh` must be KEYWORD_ONLY")
    if p.default is not False:
        return fail_closed("`force_refresh` must default to False (back-compat)")
    # Run the fixture's pytest to confirm behavior matches.
    rc, out = run_pytest(snapshot, "tests")
    if rc != 0:
        return fail_closed(f"fixture pytest failed (rc={rc}): {out[-400:]}")
    return pass_result(100, "force_refresh kwarg added; default + sensitive-env + behavior all correct")
