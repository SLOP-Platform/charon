#!/usr/bin/env python3
"""Diff-coverage gate — every new/changed line must be exercised.

Runs the test suite under coverage, then checks that every line in the
git diff is covered. Uses diff-cover for the check.

Usage:
    python3 tools/diff_cover_gate.py [base-branch]

Default base branch is origin/master.
"""
from __future__ import annotations

import os
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()


def main() -> int:
    base_branch = sys.argv[1] if len(sys.argv) > 1 else "origin/master"

    result = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD",
         "--diff-filter=AM", "--", "src/", "tools/", "tests/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    diff_lines = [
        ln for ln in result.stdout.splitlines()
        if ln.startswith("+") or ln.startswith("-")
    ]
    diff_lines = [
        ln for ln in diff_lines
        if not ln.startswith("+++") and not ln.startswith("---")
    ]

    changed = len(diff_lines)
    print(f"WORK-UNITS: {changed}")

    if changed == 0:
        print("diff-cover-gate: no changed lines in src/ tools/ tests/, skipping")
        return 0

    with tempfile.NamedTemporaryFile(suffix=".xml", prefix="coverage-", delete=False) as tmp:
        coverage_xml = tmp.name

    try:
        cov_result = subprocess.run(
            [sys.executable, "-m", "coverage", "run",
             "--source=src", "-m", "pytest", "-q", "--tb=short", "-x"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if cov_result.stdout:
            for line in cov_result.stdout.splitlines()[-5:]:
                print(line)

        subprocess.run(
            [sys.executable, "-m", "coverage", "xml", "-o", coverage_xml],
            cwd=REPO_ROOT, capture_output=True,
        )

        dc_result = subprocess.run(
            [
                "diff-cover",
                coverage_xml,
                "--compare-branch", base_branch,
                "--fail-under=100",
                "--ignore-unstaged",
                "--ignore-staged",
            ],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if dc_result.stdout:
            print(dc_result.stdout)
        if dc_result.stderr:
            print(dc_result.stderr, file=sys.stderr)

        cleanup_coverage_artifacts()
        return dc_result.returncode
    finally:
        try:
            os.unlink(coverage_xml)
        except OSError:
            pass
        cleanup_coverage_artifacts()


def cleanup_coverage_artifacts() -> None:
    for p in Path.cwd().iterdir():
        if p.name == ".coverage":
            p.unlink(missing_ok=True)
        if p.name.startswith(".coverage."):
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
