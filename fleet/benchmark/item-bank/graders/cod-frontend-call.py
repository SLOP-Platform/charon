#!/usr/bin/env python3
"""Grader for item `cod-frontend-call`.

CALIBRATION DEBT (manifest.tsv saturated="0"): this item is in the bank
on a calibration promise but the MUST-PASS / MUST-FAIL split is
unverified. The grader fails CLOSED with an explicit "calibration debt"
signal so the runner's logs are honest about the bank state. The runner
is expected to skip this item when a saturated item exists for the same
work_class + difficulty.
"""
from __future__ import annotations

import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
sys.path.insert(0, str(HERE))
from _item_base import fail_closed  # noqa: E402


def grade(snapshot: Path, unit_id: str) -> dict:
    return fail_closed(
        "calibration-debt: cod-frontend-call has no verified MUST-PASS / MUST-FAIL "
        "split; runner should skip when a saturated item exists for (coding, D2). "
        "See item-bank/manifest.tsv saturated=0 rows."
    )
