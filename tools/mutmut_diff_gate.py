#!/usr/bin/env python3
"""Mutation-testing gate (diff-scoped) — every changed line must have a test
that can kill a mutant.

Computes the changed-files set from the git diff, then runs mutmut scoped to
only those files (via the ``only_mutate`` globs). Fails RED if any mutant
survives, is not checked, has no covering test, times out, or is suspicious —
or if mutmut itself is missing / errors. GREEN only when every mutant in the
diff's changed files is provably killed.

Tool ground-truth (mutmut 3.6.x, verified live):
  * mutmut reads ``[tool.mutmut]`` from pyproject.toml (falls back to setup.cfg).
  * ``source_paths`` is the correct key; ``paths_to_mutate`` is DEPRECATED and
    only emits a warning. Diff-scoping is done with ``only_mutate`` glob patterns
    (each must end in ``.py`` or ``*``).
  * ``mutmut results`` prints one ``    <key>: <status>`` line per NON-killed
    mutant (killed mutants are silent). Empty output alone is NOT proof of pass —
    a missing/broken mutmut also prints nothing, so we additionally verify the
    run return code and that mutants were actually generated.

Usage:
    python3 tools/mutmut_diff_gate.py [base-branch]

Default base branch is origin/master.
"""
from __future__ import annotations

import importlib.util
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path.cwd().resolve()

# Any of these mutant statuses means the diff is NOT adequately tested → RED.
# (Everything except "killed" and a deliberately "skipped" mutant.)
BAD_STATUSES = frozenset({"survived", "not checked", "no tests", "timeout", "suspicious"})

_STATUS_LINE = re.compile(r"^\s*(?P<key>\S+):\s*(?P<status>.+?)\s*$")
_MUTATED_COUNT = re.compile(r"\((?P<n>\d+)\s+files?\s+mutated")


def _mutmut_installed() -> bool:
    return importlib.util.find_spec("mutmut") is not None


def _changed_source_files(base_branch: str) -> list[str]:
    result = subprocess.run(
        ["git", "diff", f"{base_branch}...HEAD", "--name-only", "--diff-filter=AM", "--", "*.py"],
        cwd=REPO_ROOT, capture_output=True, text=True,
    )
    return [
        f for f in result.stdout.splitlines()
        if f.strip() and not f.startswith("tests/")
    ]


def _scoped_pyproject(original: str, changed_files: list[str]) -> str:
    """Return pyproject content with a diff-scoped [tool.mutmut] section."""
    stripped = re.sub(
        r'\n\[tool\.mutmut\].*?(\n\[|\Z)',
        r'\n\1',
        original,
        flags=re.DOTALL,
    )
    stripped = stripped.rstrip() + "\n"
    body = "\n[tool.mutmut]\n"
    body += 'source_paths = ["src"]\n'
    # only_mutate takes glob patterns; the changed .py paths are valid globs.
    body += f"only_mutate = {changed_files!r}\n"
    return stripped + body


def _parse_statuses(results_stdout: str) -> dict[str, int]:
    counts: dict[str, int] = {}
    for line in results_stdout.splitlines():
        m = _STATUS_LINE.match(line)
        if not m:
            continue
        status = m.group("status").strip()
        counts[status] = counts.get(status, 0) + 1
    return counts


def main() -> int:
    base_branch = sys.argv[1] if len(sys.argv) > 1 else "origin/master"

    changed_files = _changed_source_files(base_branch)
    file_count = len(changed_files)
    print(f"WORK-UNITS: {file_count}")

    if file_count == 0:
        print("mutmut-diff-gate: no Python source files changed, skipping")
        return 0

    if not _mutmut_installed():
        print(
            "FAIL: mutmut is not installed — cannot verify mutation coverage.\n"
            "      Install it with:  pip install '.[dev]'   (mutmut>=3.6)",
            file=sys.stderr,
        )
        return 1

    orig_pyproject = REPO_ROOT / "pyproject.toml"
    original_text = orig_pyproject.read_text()

    try:
        orig_pyproject.write_text(_scoped_pyproject(original_text, changed_files))

        run_result = subprocess.run(
            [sys.executable, "-m", "mutmut", "run"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
        results_result = subprocess.run(
            [sys.executable, "-m", "mutmut", "results"],
            cwd=REPO_ROOT, capture_output=True, text=True,
        )
    finally:
        # Restore the tracked SSOT UNCONDITIONALLY — no window where a crash
        # leaves pyproject.toml corrupted.
        orig_pyproject.write_text(original_text)
        _cleanup_mutmut_artifacts()

    if run_result.stdout:
        print(run_result.stdout)
    if run_result.stderr.strip():
        print(run_result.stderr, file=sys.stderr)

    # How many files did mutmut actually mutate? 0 means diff-scoping matched
    # nothing (misconfig) or the changed lines carry no mutatable code.
    mutated = None
    m = _MUTATED_COUNT.search(run_result.stdout)
    if m:
        mutated = int(m.group("n"))

    status_counts = _parse_statuses(results_result.stdout)
    bad = {s: n for s, n in status_counts.items() if s in BAD_STATUSES}
    survived = status_counts.get("survived", 0)

    print(
        f"mutmut-diff-gate: files_mutated={mutated} run_rc={run_result.returncode} "
        f"survived={survived} statuses={status_counts or '{}'}"
    )

    if bad:
        print(file=sys.stderr)
        print("FAIL: non-killed mutants detected in the diff:", file=sys.stderr)
        for status, n in sorted(bad.items()):
            print(f"    {status}: {n}", file=sys.stderr)
        if results_result.stdout.strip():
            print(results_result.stdout, file=sys.stderr)
        return 1

    # No bad statuses reported. Empty output is only trustworthy if mutmut
    # actually ran to completion AND generated mutants — otherwise a broken
    # tool / crash would fake a green.
    if run_result.returncode != 0:
        print(
            f"FAIL: mutmut run exited {run_result.returncode} with no scored mutants — "
            "treating as an error, not a pass. See stderr above.",
            file=sys.stderr,
        )
        return 1

    if mutated == 0:
        print(
            "FAIL: mutmut mutated 0 files despite changed source — diff-scoping "
            "matched nothing (check only_mutate globs / changed paths).",
            file=sys.stderr,
        )
        return 1

    print("mutmut-diff-gate: OK — all mutants in the diff were killed")
    return 0


def _cleanup_mutmut_artifacts() -> None:
    import shutil

    mutants_dir = REPO_ROOT / "mutants"
    if mutants_dir.exists():
        shutil.rmtree(mutants_dir, ignore_errors=True)
    for p in REPO_ROOT.iterdir():
        if p.name.startswith(".coverage") or p.name == ".mutmut-cache":
            p.unlink(missing_ok=True)


if __name__ == "__main__":
    raise SystemExit(main())
