#!/usr/bin/env python3
"""grade.py — item-bank OOB grader dispatcher.

Adapter: takes the (snapshot, item_id) the grader-daemon hands us for
kind=="preflight" requests, and dispatches to the right item-specific
grader. Fails CLOSED: an unknown item_id, a missing grader, or a crashed
grader ALL return BLOCK (never PASS). This is the
"exactly one capture path" + "no second writer" guarantee the consolidated
pipeline gives the live lane: the dispatcher is the SINGLE entry point
that can produce a preflight-kind score, and it is OOB / fail-closed.

Mirrors graders.preflight.grade()'s contract; lives at
fleet/benchmark/item-bank/grade.py so the daemon can resolve it via its
existing import path (graders/<unit_id>.py).
"""
from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

ITEM_BANK_DIR = Path(__file__).resolve().parent
GRADERS_DIR = ITEM_BANK_DIR / "graders"

sys.path.insert(0, str(GRADERS_DIR))


def _fail_closed(reason: str) -> dict:
    return {
        "score": 0,
        "verdict": "FAIL",
        "gate": "fail",
        "reason": reason[:500] if reason else "dispatcher-error",
    }


def grade(snapshot: Path, unit_id: str) -> dict:
    """OOB-grade `snapshot` against the item whose `item_id == unit_id`.

    Mirrors graders.preflight.grade()'s contract so the daemon can treat
    it as just another grader import. Fails CLOSED on any error.
    """
    if not snapshot or not Path(snapshot).exists():
        return _fail_closed(f"item-bank: snapshot dir missing: {snapshot!r}")
    grader_path = GRADERS_DIR / f"{unit_id}.py"
    if not grader_path.exists():
        return _fail_closed(f"item-bank: no grader for item_id={unit_id!r} (looked for {grader_path})")
    # Each grader exposes a top-level `grade(snapshot, unit_id) -> dict`.
    # The dispatcher loads it by file name and forwards. We deliberately
    # do NOT auto-discover (glob import) to keep the wiring explicit; a
    # grep for "item_id == " finds every item the bank actually grades.
    try:
        mod_name = f"item_{unit_id.replace('-', '_')}_grader"
        spec = importlib.util.spec_from_file_location(mod_name, str(grader_path))
        if spec is None or spec.loader is None:
            return _fail_closed(f"item-bank: cannot load grader spec for {unit_id!r}")
        mod = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(mod)
    except Exception as exc:  # noqa: BLE001 — a crash loading the grader is a BLOCK
        return _fail_closed(f"item-bank: grader load failed for {unit_id!r}: {exc!r}")
    fn = getattr(mod, "grade", None)
    if fn is None:
        return _fail_closed(f"item-bank: grader {unit_id!r} has no `grade(snapshot, unit_id)` function")
    try:
        result = fn(Path(snapshot), unit_id)
    except Exception as exc:  # noqa: BLE001 — a crash running the grader is a BLOCK
        return _fail_closed(f"item-bank: grader {unit_id!r} raised: {exc!r}")
    # Coerce to the daemon's expected schema. A grader that returns None
    # or a non-dict is a fail-closed BLOCK.
    if not isinstance(result, dict):
        return _fail_closed(f"item-bank: grader {unit_id!r} returned non-dict: {type(result).__name__}")
    score = result.get("score", 0)
    verdict = result.get("verdict", "FAIL")
    gate = result.get("gate", "fail")
    reason = result.get("reason", "")
    try:
        score = int(score)
    except (TypeError, ValueError):
        score = 0
    if verdict not in ("PASS", "FAIL"):
        verdict = "PASS" if gate == "pass" else "FAIL"
    if gate not in ("pass", "fail"):
        gate = "pass" if verdict == "PASS" else "fail"
    return {
        "score": max(0, min(100, score)),
        "verdict": verdict,
        "gate": gate,
        "reason": str(reason)[:500],
    }


if __name__ == "__main__":
    # Manual smoke entry: `python3 grade.py <snapshot> <item_id>`
    if len(sys.argv) != 3:
        print(json.dumps(_fail_closed("usage: grade.py <snapshot> <item_id>")))
        sys.exit(1)
    snap = Path(sys.argv[1])
    uid = sys.argv[2]
    print(json.dumps(grade(snap, uid)))
