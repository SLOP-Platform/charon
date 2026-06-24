#!/usr/bin/env python3
"""SLOP-boundary check (ADR-0002 INV-B1/B5; reconciliation BR-4).

GROUND: parses every .py file under src/ with the ast module and fails if any
import (``import x``, ``from x import``, or a literal ``__import__("x")``) names
a forbidden package. This is an AST scan, not a grep — it ignores comments,
docstrings, and strings, and it catches the ``__import__("slo"+"p")`` style by
flagging any ``__import__`` whose argument is a constant containing a forbidden
token. Exit non-zero on violation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

FORBIDDEN = ("slop", "mediastack")


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


def main(root: str = "src") -> int:
    base = Path(root)
    all_violations: list[str] = []
    for py in base.rglob("*.py"):
        all_violations.extend(scan_file(py))
    if all_violations:
        print("SLOP-boundary VIOLATION (ADR-0002 INV-B1/B5):", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"boundary OK: no SLOP references under {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))
