#!/usr/bin/env python3
# @covers: version
"""Version-consistency check (ADR-0002 §4: one true home for version).

Single source of truth is ``pyproject.toml::project.version``. Two drift modes,
both caught:
  * a hardcoded ``__version__ = "x"`` LITERAL in the source disagreeing with
    pyproject — the real "a satellite copy cannot drift" (checked everywhere);
  * the INSTALLED package metadata disagreeing with pyproject — only meaningful
    in CI (fresh install); a local editable install lags until ``pip install -e .``,
    so that is a benign dev artifact, not real drift.
"""
from __future__ import annotations

import os
import re
import sys
import tomllib
from importlib.metadata import PackageNotFoundError, version
from pathlib import Path

_LITERAL = re.compile(r"""__version__\s*=\s*['"]([^'"]+)['"]""")


def _in_ci() -> bool:
    return os.environ.get("CI") == "true" or os.environ.get("GITHUB_ACTIONS") == "true"


def _literal_drift(declared: str) -> list[str]:
    """Source files hardcoding a ``__version__`` literal that disagrees with
    pyproject. Skips ``__init__.py`` — the sanctioned home reads the version from
    importlib.metadata and only carries a non-version ``0+unknown`` fallback."""
    src = Path("src")
    bad: list[str] = []
    if not src.is_dir():
        return bad
    for py in src.rglob("*.py"):
        if py.name == "__init__.py":
            continue
        for m in _LITERAL.finditer(py.read_text(encoding="utf-8")):
            if m.group(1) != declared:
                bad.append(f"{py}:{m.group(1)}")
    return bad


def main() -> int:
    declared = tomllib.loads(Path("pyproject.toml").read_text())["project"]["version"]

    drift = _literal_drift(declared)
    if drift:
        print(f"VERSION DRIFT: pyproject={declared} but source literals disagree: "
              + ", ".join(drift), file=sys.stderr)
        return 1

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
        print(msg + " — stale local editable metadata; run 'pip install -e .' to "
              "refresh. Not failing outside CI.")
        return 0
    print(f"version OK: {declared}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
