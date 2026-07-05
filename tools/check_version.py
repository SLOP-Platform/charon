#!/usr/bin/env python3
# @covers: version
"""Version-consistency check (ADR-0002 §4: one true home for version).

The single source of truth is ``pyproject.toml::project.version``. This asserts
the installed package reports the same string, so a satellite copy cannot drift.
"""
from __future__ import annotations

import os
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


def _in_ci() -> bool:
    # GitHub Actions (and most CI) set CI=true; the release/gate jobs pip-install
    # fresh, so installed metadata ALWAYS matches pyproject there — any drift is
    # real. A local editable install lags pyproject until `pip install -e .`, so
    # drift there is a benign dev artifact, not a satellite copy diverging.
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def main() -> int:
    pyproject = Path("pyproject.toml")
    data = tomllib.loads(pyproject.read_text())
    declared = data["project"]["version"]
    try:
        installed = version("charon")
    except PackageNotFoundError:
        print(f"charon not installed; pyproject declares {declared}")
        return 0
    if installed != declared:
        msg = f"VERSION DRIFT: pyproject={declared} installed={installed}"
        if _in_ci():
            print(msg + " (fresh CI install must match — real drift)", file=sys.stderr)
            return 1
        # Local dev: editable metadata is stale until reinstall — warn, don't fail.
        print(msg + " — stale local editable metadata; run 'pip install -e .' to "
              "refresh. Not failing outside CI.")
        return 0
    print(f"version OK: {declared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
