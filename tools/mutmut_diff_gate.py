#!/usr/bin/env python3
"""Mutation-testing gate (diff-scoped) — every changed line must have a test
that can kill a mutant.

Computes the changed-files set from the git diff, then runs mutmut scoped
to only those files. Fails if any mutant survives or has no covering test.

Usage:
    python3 tools/mutmut_diff_gate.py [base-branch]

Default base branch is origin/master.
"""
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()


def main() -> int:
    base_branch = sys.argv[1] if len(sys.argv) > 1 else "origin/master"

    result = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD", "--name-only", "--diff-filter=AM", "--", "*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    changed_files = [
        f for f in result.stdout.splitlines()
        if f.strip() and not f.startswith("tests/")
    ]

    file_count = len(changed_files)
    print(f"WORK-UNITS: {file_count}")

    if file_count == 0:
        print("mutmut-diff-gate: no Python source files changed, skipping")
        return 0

    tmpdir = Path(tempfile.mkdtemp(prefix="mutmut-gate-"))
    try:
        orig_pyproject = REPO_ROOT / "pyproject.toml"
        bak = tmpdir / "pyproject.bak"
        shutil.copy2(orig_pyproject, bak)

        content = orig_pyproject.read_text()
        content = re.sub(
            r'\n\[tool\.mutmut\].*?(\n\[|\Z)',
            r'\n\1',
            content,
            flags=re.DOTALL,
        )
        content = content.rstrip() + "\n"
        content += "[tool.mutmut]\n"
        content += 'source_paths = ["src"]\n'
        content += f"only_mutate = {changed_files!s}\n"
        orig_pyproject.write_text(content)

        run_result = subprocess.run(
            [sys.executable, "-m", "mutmut", "run"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        if run_result.stdout:
            print(run_result.stdout)
        if run_result.stderr:
            print(run_result.stderr, file=sys.stderr)

        results_result = subprocess.run(
            [sys.executable, "-m", "mutmut", "results"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )

        # Restore original pyproject.toml
        shutil.copy2(bak, orig_pyproject)

        results_out = results_result.stdout.strip()
        if results_out:
            print()
            print("FAIL: non-killed mutants detected:", file=sys.stderr)
            print(results_out, file=sys.stderr)
            cleanup_mutmut_artifacts()
            return 1

        cleanup_mutmut_artifacts()
        print("mutmut-diff-gate: OK")
        return 0
    finally:
        shutil.rmtree(tmpdir, ignore_errors=True)
        cleanup_mutmut_artifacts()


def cleanup_mutmut_artifacts() -> None:
    mutants_dir = REPO_ROOT / "mutants"
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir, ignore_errors=True)
    for p in REPO_ROOT.iterdir():
        if p.name.startswith(".coverage") or p.name == ".mutmut-cache":
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
