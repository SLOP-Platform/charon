#!/usr/bin/env python3
"""graders/_item_base.py — shared base for item-bank OOB graders.

Every item grader in this directory implements the same `grade(snapshot,
unit_id) -> dict` contract (consumed by grader-daemon.py via
graders.preflight.grade). The contract:

    -> {"score": int 0-100, "verdict": "PASS"|"FAIL",
        "gate": "pass"|"fail", "reason": str}

The grader is OOB: it inspects the model's WORKTREE (passed in as
`snapshot`) and returns the OBJECTIVE outcome. It NEVER reads the model's
prose, NEVER trusts a self-reported success, and NEVER imports the model
or any code the model wrote. It IS allowed to import pytest, run shell
commands, and use the filesystem.

FAIL-CLOSED: if anything goes wrong (the worktree is missing, the seed
fixture is missing, a check tool itself crashes), the grader returns
{"score": 0, "verdict": "FAIL", "gate": "fail", "reason": "<why>"} —
NEVER a partial credit. A flaky grader that defaults to PASS is the
silent-failure mode EVAL-GRADER-PROVISION exists to prevent.
"""
from __future__ import annotations

import json
import subprocess
from pathlib import Path
from typing import Any


def fail_closed(reason: str) -> dict:
    """Return a fail-closed BLOCK result. Use whenever the grader cannot
    produce a reliable PASS/FAIL (missing fixture, crashed check tool,
    ambiguous diff, etc). A flaky grader that defaults to PASS is worse
    than one that defaults to FAIL — the F2 BLOCKER in the adversarial
    review is exactly the inverse bug."""
    return {
        "score": 0,
        "verdict": "FAIL",
        "gate": "fail",
        "reason": reason[:500] if reason else "grader-error",
    }


def pass_result(score: int = 100, reason: str = "") -> dict:
    return {
        "score": int(score),
        "verdict": "PASS",
        "gate": "pass",
        "reason": reason[:500] if reason else "ok",
    }


def run_pytest(snapshot: Path, test_path: str = "tests", timeout: int = 120) -> tuple[int, str]:
    """Run pytest in the worktree. Returns (returncode, output)."""
    try:
        proc = subprocess.run(
            ["python3", "-m", "pytest", test_path, "-q", "--tb=line", "--no-header"],
            cwd=str(snapshot),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
        return proc.returncode, (proc.stdout or "") + (proc.stderr or "")
    except subprocess.TimeoutExpired:
        return 124, "pytest timeout"
    except Exception as exc:  # noqa: BLE001 — anything that breaks the runner is a fail-closed
        return 1, f"pytest-crashed: {exc!r}"


def find_file_with_substring(snapshot: Path, substring: str) -> list[Path]:
    """Return a list of files under `snapshot` whose content contains the
    substring. Used by graders that key on a function name or string
    literal the model was supposed to add (e.g. SECRET-HOTROTATE's
    'force_refresh' kwarg check). The substring match is whole-line,
    not just substring-of-line, to avoid 'force_refreshed' false hits."""
    hits: list[Path] = []
    if not snapshot.exists():
        return hits
    for p in snapshot.rglob("*"):
        if not p.is_file():
            continue
        try:
            text = p.read_text(errors="ignore")
        except Exception:
            continue
        for line in text.splitlines():
            if substring in line:
                hits.append(p)
                break
    return hits


def file_contains(snapshot: Path, relative: str, substring: str) -> bool:
    """Convenience: does a specific file under the snapshot contain the
    substring on some line?"""
    p = snapshot / relative
    if not p.exists():
        return False
    try:
        text = p.read_text(errors="ignore")
    except Exception:
        return False
    return any(substring in line for line in text.splitlines())


def read_json_or_none(text: str) -> dict[str, Any] | None:
    """Parse a JSON line from grader subprocess output. grader-daemon
    expects the LAST non-empty line of stdout to be JSON."""
    if not text:
        return None
    for line in reversed(text.strip().splitlines()):
        line = line.strip()
        if not line:
            continue
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            continue
    return None


def write_grader_result(result: dict) -> None:
    """Print a grader result as a single JSON line to stdout. The
    grader-daemon picks the LAST non-empty line (see its
    json.loads(proc.stdout.strip().split(chr(10))[-1])) so this MUST be
    the last thing the grader prints."""
    print(json.dumps(result, sort_keys=True))
