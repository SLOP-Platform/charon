#!/usr/bin/env python3
"""Real-task grader — grades reds-replay tasks (#25) and other real sub-session
actuals using out-of-band answer keys (``/home/bench-grader/keys/``).

This module is OWNED by the grader-daemon (#26).  It is NEVER imported by
product code or by the graded agent's session.  The daemon is the sole caller.

Grading contract:
    grade(snapshot: Path, unit_id: str) -> dict

Returns ``{score, verdict, gate, reason}`` or ``None`` if the unit is not
found in the keys registry (caller handles the fallback).

The answer key for reds-replay is ``$KEYS/reds-replay.tsv``:
    unit_id  red_id  prefix_snapshot  check_cmd  expect_green_exit  work_class  note

The daemon substitutes ``{worktree}`` in ``check_cmd`` with the snapshot path
before executing it.  Exit 0 → MERGE (100).  Non-zero → BLOCK (0).
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

KEYS_DIR = Path("/home/bench-grader/keys")
REDS_REPLAY_TSV = KEYS_DIR / "reds-replay.tsv"

GRADER_TIMEOUT_S = 300


def grade_reds_replay(snapshot: Path, unit_id: str) -> dict | None:
    """Grade a reds-replay unit by running its check_cmd from the keys.

    Returns a grader-compatible result dict or None if the unit is not found.
    """
    if not REDS_REPLAY_TSV.exists():
        return None

    for line in REDS_REPLAY_TSV.read_text().splitlines():
        if not line or line.startswith("#"):
            continue
        cols = line.split("\t")
        if cols[0] == "unit_id":
            continue
        if len(cols) < 5:
            continue
        if cols[0] != unit_id:
            continue
        # cols: unit_id, red_id, prefix_snapshot, check_cmd, expect_green_exit, work_class, note
        check_cmd = cols[3].replace("{worktree}", str(snapshot))
        try:
            proc = subprocess.run(
                check_cmd, shell=True, capture_output=True, text=True,
                timeout=GRADER_TIMEOUT_S, cwd=str(snapshot),
            )
        except subprocess.TimeoutExpired:
            return {
                "score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"check_cmd timed out after {GRADER_TIMEOUT_S}s",
            }

        passed = proc.returncode == 0
        if passed:
            return {
                "score": 100, "verdict": "MERGE", "gate": "pass",
                "reason": "reds-replay: check_cmd passed",
            }
        else:
            return {
                "score": 0, "verdict": "BLOCK", "gate": "fail",
                "reason": f"reds-replay: check_cmd failed (exit {proc.returncode})",
            }

    return None


def grade(snapshot: Path, unit_id: str) -> dict | None:
    """Dispatch real-task grading by unit_id.

    Currently only reds-replay is supported.  Returns None if the unit is
    not recognized (caller should fall back to synthetic section grading or
    emit a BLOCK).
    """
    return grade_reds_replay(snapshot, unit_id)
