#!/usr/bin/env python3
"""SLOP-boundary check (ADR-0002 INV-B1/B5; reconciliation BR-4).

GROUND: parses every .py file under src/ with the ast module and fails if any
import (``import x``, ``from x import``, or a literal ``__import__("x")``) names
a forbidden package. This is an AST scan, not a grep — it ignores comments,
docstrings, and strings, and it catches the ``__import__("slo"+"p")`` style by
flagging any ``__import__`` whose argument is a constant containing a forbidden
token. Exit non-zero on violation.

Also enforces the ADR-0010 D2 / ADR-0005 R3 engine stdlib-only rule: any file
under src/charon/engine/ (or src/charon/ports/worker.py) may only import stdlib
or charon.* packages — no third-party dependencies. The engine/ modules now
exist; this pass enforces the constraint actively.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN = ("slop", "mediastack")

# Available from Python 3.10+; covers all stdlib top-level names.
_STDLIB_TOPS: frozenset[str] = sys.stdlib_module_names  # type: ignore[attr-defined]


def _forbidden(name: str | None) -> bool:
    if not name:
        return False
    head = name.split(".")[0].lower()
    return head in FORBIDDEN or any(tok in name.lower() for tok in FORBIDDEN)


def scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _forbidden(alias.name):
                    violations.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if _forbidden(node.module):
                violations.append(f"{path}:{node.lineno}: from {node.module} import ...")
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "__import__":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and _forbidden(arg.value):
                    violations.append(f"{path}:{node.lineno}: __import__({arg.value!r})")
    return violations


def _engine_allowed(name: str | None) -> bool:
    """Return True iff the import is permitted inside engine/ (stdlib or charon.*)."""
    if not name:
        return True
    head = name.split(".")[0]
    return head in _STDLIB_TOPS or name == "charon" or name.startswith("charon.")


def scan_engine_file(path: Path) -> list[str]:
    """AST-scan one engine/*.py (or ports/worker.py): only stdlib + charon.* allowed."""
    violations: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if not _engine_allowed(alias.name):
                    violations.append(
                        f"{path}:{node.lineno}: engine-stdlib-only: import {alias.name!r}"
                    )
        elif isinstance(node, ast.ImportFrom):
            # level >= 1 means a relative import (e.g. `from .board import X`);
            # those are intra-charon and always allowed.
            if (node.level or 0) == 0 and not _engine_allowed(node.module):
                violations.append(
                    f"{path}:{node.lineno}: engine-stdlib-only: from {node.module!r} import ..."
                )
    return violations


def scan_engine(src_root: Path) -> list[str]:
    """Scan engine/ + ports/worker.py for non-stdlib/non-charon imports."""
    engine_dir = src_root / "charon" / "engine"
    worker_file = src_root / "charon" / "ports" / "worker.py"

    paths: list[Path] = []
    if engine_dir.exists():
        paths.extend(sorted(engine_dir.rglob("*.py")))
    if worker_file.exists():
        paths.append(worker_file)

    violations: list[str] = []
    for py in paths:
        violations.extend(scan_engine_file(py))
    return violations


def main(root: str = "src") -> int:
    base = Path(root)
    all_violations: list[str] = []
    for py in base.rglob("*.py"):
        all_violations.extend(scan_file(py))
    # Engine stdlib-only guard (ADR-0010 D2 / ADR-0005 R3).
    all_violations.extend(scan_engine(base))
    if all_violations:
        print("SLOP-boundary VIOLATION (ADR-0002 INV-B1/B5):", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"boundary OK: no SLOP references under {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))
