#!/usr/bin/env python3
"""diff-cover patch-coverage gate.

Fails if any line added or modified in the PR diff is not exercised by the
test suite. Uses coverage.py's XML report (cobertura format) + diff-cover
to compare the diff against executed-line data.

Exit non-zero on uncovered new/changed lines.
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

_GC_ROOT = Path(__file__).resolve().parent.parent


def main() -> int:
    diff_file = Path(sys.argv[1]) if len(sys.argv) > 1 else _GC_ROOT / "pr_diff.patch"
    coverage_xml = Path(sys.argv[2]) if len(sys.argv) > 2 else _GC_ROOT / "coverage.xml"

    if not diff_file.exists():
        print("diff-cover-gate: no diff file — cannot check coverage", file=sys.stderr)
        print("WORK-UNITS: 0")
        return 1

    if not coverage_xml.exists():
        print("diff-cover-gate: no coverage XML — run pytest with --cov --cov-report=xml first", file=sys.stderr)
        print("WORK-UNITS: 0")
        return 1

    result = subprocess.run(
        ["diff-cover", str(coverage_xml), "--diff-file", str(diff_file)],
        capture_output=True,
        text=True,
        cwd=_GC_ROOT,
    )

    total = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if line:
            total += 1

    print(f"WORK-UNITS: {total}")

    if result.returncode != 0:
        print(result.stdout, file=sys.stderr)
        if result.stderr:
            print(result.stderr, file=sys.stderr)
        return result.returncode

    print(result.stdout)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
