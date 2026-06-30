#!/usr/bin/env python3
# @covers: version
"""Version-consistency check (ADR-0002 §4: one true home for version).

The single source of truth is ``pyproject.toml::project.version``. This asserts
the installed package reports the same string, so a satellite copy cannot drift.
"""
from __future__ import annotations

import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path


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
        print(f"VERSION DRIFT: pyproject={declared} installed={installed}",
              file=sys.stderr)
        return 1
    print(f"version OK: {declared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
