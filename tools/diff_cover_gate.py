#!/usr/bin/env python3
"""Diff-coverage gate — every new/changed line must be exercised.

Runs the test suite under coverage.py, exports a coverage XML, then uses
diff-cover to require 100% coverage of the lines added/changed in the PR diff.

Fails RED (with a clear message, never a raw traceback) when:
  * coverage.py or diff-cover is not installed;
  * the test run under coverage errors out;
  * no usable coverage XML is produced (empty / unparseable);
  * any new/changed line in the diff is unexercised.

Usage:
    python3 tools/diff_cover_gate.py [base-branch]

Default base branch is origin/master.
"""
from __future__ import annotations

import importlib.util
import os
import shutil
import subprocess
import sys
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()


def _diff_lines(base_branch: str) -> int:
    result = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD",
         "--diff-filter=AM", "--", "src/", "tools/", "tests/"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    lines = [
        ln for ln in result.stdout.splitlines()
        if (ln.startswith("+") or ln.startswith("-"))
        and not ln.startswith("+++") and not ln.startswith("---")
    ]
    return len(lines)


def _xml_is_usable(path: str) -> bool:
    try:
        if os.path.getsize(path) == 0:
            return False
        ET.parse(path)
        return True
    except (OSError, ET.ParseError):
        return False


def main() -> int:
    base_branch = sys.argv[1] if len(sys.argv) > 1 else "origin/master"

    changed = _diff_lines(base_branch)
    print(f"WORK-UNITS: {changed}")

    if changed == 0:
        print("diff-cover-gate: no changed lines in src/ tools/ tests/, skipping")
        return 0

    # --- tool preflight: fail LOUD, not with an obscure traceback -------------
    if importlib.util.find_spec("coverage") is None:
        print(
            "FAIL: coverage.py is not installed — cannot measure diff coverage.\n"
            "      Install it with:  pip install '.[dev]'   (coverage>=7)",
            file=sys.stderr,
        )
        return 1
    if shutil.which("diff-cover") is None:
        print(
            "FAIL: diff-cover is not installed — cannot check diff coverage.\n"
            "      Install it with:  pip install '.[dev]'   (diff-cover>=9)",
            file=sys.stderr,
        )
        return 1

    with tempfile.NamedTemporaryFile(suffix=".xml", prefix="coverage-", delete=False) as tmp:
        coverage_xml = tmp.name

    try:
        cov_result = subprocess.run(
            [sys.executable, "-m", "coverage", "run",
             "--source=src", "-m", "pytest", "-q", "--tb=short"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if cov_result.stdout:
            for line in cov_result.stdout.splitlines()[-8:]:
                print(line)
        if cov_result.returncode != 0:
            print(
                f"FAIL: test suite exited {cov_result.returncode} under coverage — "
                "diff coverage cannot be trusted while tests are failing.",
                file=sys.stderr,
            )
            if cov_result.stderr.strip():
                print(cov_result.stderr[-2000:], file=sys.stderr)
            return 1

        xml_result = subprocess.run(
            [sys.executable, "-m", "coverage", "xml", "-o", coverage_xml],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if not _xml_is_usable(coverage_xml):
            print(
                "FAIL: coverage produced no usable XML report "
                f"(coverage xml rc={xml_result.returncode}). No coverage data to check.",
                file=sys.stderr,
            )
            if xml_result.stderr.strip():
                print(xml_result.stderr[-1000:], file=sys.stderr)
            return 1

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
        if dc_result.stderr.strip():
            print(dc_result.stderr, file=sys.stderr)

        return dc_result.returncode
    finally:
        try:
            os.unlink(coverage_xml)
        except OSError:
            pass
        _cleanup_coverage_artifacts()


def _cleanup_coverage_artifacts() -> None:
    for p in Path.cwd().iterdir():
        if p.name == ".coverage" or p.name.startswith(".coverage."):
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
