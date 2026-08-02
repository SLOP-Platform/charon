#!/usr/bin/env python3
# mutmut diff-scoped mutation-testing gate.
#
# Scopes mutation testing to the files that changed in the PR diff. Runs
# mutmut against those files only (never full-tree in the PR gate — full-tree
# is a separate nightly cadence). Fails if any mutant survives, which means the
# test suite could not kill it: either there is no exercising test or the
# assertion is too weak to fail on the mutated behavior.
#
# mutmut is configured via pyproject.toml [tool.mutmut]. This script:
#   1. Saves the current [tool.mutmut] section
#   2. Patches it to scope source_paths to the changed files in the diff
#   3. Runs mutmut run
#   4. Runs mutmut results (parses survived count)
#   5. Restores the original pyproject.toml
from __future__ import annotations

import re
import shutil
import subprocess
import sys
import tomllib
from pathlib import Path

_GC_ROOT = Path(__file__).resolve().parent.parent
_PYPROJECT = _GC_ROOT / "pyproject.toml"
_MUTMUT_DB = _GC_ROOT / ".mutmut.sqlite"
_ORIG_BACKUP = _GC_ROOT / ".pyproject.toml.mutmut.bak"


def _extract_changed_files(diff_path: Path) -> list[Path]:
    """Return the set of .py files added or modified in the diff."""
    changed: list[Path] = []
    if not diff_path.exists():
        return changed
    content = diff_path.read_text(encoding="utf-8")
    for line in content.splitlines():
        m = re.match(r"^\+\+\+ [ab]/(.+)$", line)
        if m:
            path = Path(m.group(1))
            if path.suffix == ".py":
                changed.append(path)
    return changed


def _mutmut_results() -> tuple[int, int]:
    """Run 'mutmut results' and return (survived_count, total_count)."""
    result = subprocess.run(
        ["mutmut", "results"],
        capture_output=True,
        text=True,
        cwd=_GC_ROOT,
    )
    survived = 0
    total = 0
    for line in result.stdout.splitlines():
        line = line.strip()
        if not line or line.startswith("-"):
            continue
        if ": survived" in line or line.endswith("survived"):
            survived += 1
        total += 1
    return survived, total


def main() -> int:
    diff_file = Path(sys.argv[1]) if len(sys.argv) > 1 else _GC_ROOT / "pr_diff.patch"
    changed_files = _extract_changed_files(diff_file)

    print(f"WORK-UNITS: {len(changed_files)}", flush=True)

    if not changed_files:
        print("mutmut-diff-gate: no changed .py files in diff — nothing to mutate")
        return 0

    if not _PYPROJECT.exists():
        print("mutmut-diff-gate: pyproject.toml not found", file=sys.stderr)
        return 1

    data = tomllib.loads(_PYPROJECT.read_bytes().decode("utf-8"))
    orig_section = data.get("tool", {}).get("mutmut", {}).copy()

    _ORIG_BACKUP.write_bytes(_PYPROJECT.read_bytes())

    try:
        patched = dict(orig_section)
        patched["source_paths"] = [str(p) for p in changed_files]
        data.setdefault("tool", {})["mutmut"] = patched

        import io

        buf = io.StringIO()
        import tomli_w

        tomli_w.dump(data, buf)
        _PYPROJECT.write_bytes(buf.getvalue().encode("utf-8"))

        if _MUTMUT_DB.exists():
            _MUTMUT_DB.unlink()

        mutants_dir = _GC_ROOT / "mutants"
        if mutants_dir.exists():
            shutil.rmtree(mutants_dir)

        run_result = subprocess.run(
            ["mutmut", "run"],
            capture_output=True,
            text=True,
            cwd=_GC_ROOT,
            env={**__import__("os").environ, "TERM": "dumb"},
        )

        if run_result.returncode not in (0, 1):
            print(f"mutmut-diff-gate: mutmut run failed (exit {run_result.returncode})", file=sys.stderr)
            print(run_result.stderr[-2000:], file=sys.stderr)
            return 1

        survived, total = _mutmut_results()
        print(f"mutmut-diff-gate: {survived}/{total} mutant(s) survived", flush=True)

        if survived > 0:
            print("MUTANT-SURVIVED: test suite could not kill the above mutant(s)", file=sys.stderr)
            print(run_result.stdout[-1000:], file=sys.stderr)
            return 1

        return 0

    finally:
        if _ORIG_BACKUP.exists():
            _PYPROJECT.write_bytes(_ORIG_BACKUP.read_bytes())
            _ORIG_BACKUP.unlink()


if __name__ == "__main__":
    raise SystemExit(main())
