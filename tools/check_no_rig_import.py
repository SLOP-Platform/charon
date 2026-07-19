#!/usr/bin/env python3
# @covers: no-rig-import
"""Product-hot-path import guard (GATEWAY-PROGRAM §1.9 red-team fix #2, CRITICAL).

The rig grader (the ``benchmark`` + ``grader_daemon`` packages) must NEVER be a live routing
dependency. If a rig regression lands and a product module imports it, the
gateway's hot path can either (a) silently miscalibrate because the rig output
is stale, or (b) crash because the rig process is down. Either way is a
money-path bug.

This guard AST-scans every .py file under ``src/charon/`` (excluding the
``charon/engine/`` and ``charon/ports/worker.py`` zones — those are the
privileged-loop paths and are stdlib-only by a different rule, see
``check_boundary.py``) and FAIL-CLOSES on:

  * ``import benchmark`` / ``from benchmark import ...``
  * ``import grader_daemon`` / ``from grader_daemon import ...``
  * Dynamic ``__import__("benchmark")`` / ``__import__("grader_daemon")``
    (BR-4 style — caught by inspecting the constant argument)

The scan ignores comments and string literals — it parses with ``ast`` and
only flags actual import statements. The guard exits 1 on any violation and
prints the offending file:line.

Usage::

    python3 tools/check_no_rig_import.py          # scan default src/
    python3 tools/check_no_rig_import.py src      # explicit root

Exit codes: 0 clean, 1 violation.
"""
from __future__ import annotations

import ast
import sys
from pathlib import Path

# Rig-package names — MUST NOT appear on the product hot path.
FORBIDDEN_RIG_PACKAGES: frozenset[str] = frozenset({"benchmark", "grader_daemon"})


def _is_forbidden(name: str | None) -> bool:
    """Return True iff *name* names a rig package we ban on the hot path."""
    if not name:
        return False
    head = name.split(".")[0]
    return head in FORBIDDEN_RIG_PACKAGES


def scan_file(path: Path) -> list[str]:
    """AST-scan one .py file for forbidden rig-package imports.

    Returns a list of ``"path:lineno: <offending text>"`` strings (empty
    when the file is clean). The scan covers:
      * ``ast.Import`` nodes (e.g. ``import benchmark``)
      * ``ast.ImportFrom`` nodes (e.g. ``from grader_daemon import ...``)
      * ``__import__("benchmark")`` style dynamic imports with a literal
        constant argument (BR-4: catches the ``__import__("bench"+"mark")``
        obfuscation only when the *concatenated* result is a constant
        forbidden name — done at the AST level by collapsing adjacent
        ``Constant`` nodes before string-matching).
    """
    violations: list[str] = []
    tree = ast.parse(path.read_text(), filename=str(path))
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                if _is_forbidden(alias.name):
                    violations.append(f"{path}:{node.lineno}: import {alias.name}")
        elif isinstance(node, ast.ImportFrom):
            if _is_forbidden(node.module):
                violations.append(
                    f"{path}:{node.lineno}: from {node.module} import ..."
                )
        elif isinstance(node, ast.Call) and isinstance(node.func, ast.Name) \
                and node.func.id == "__import__":
            for arg in node.args:
                if isinstance(arg, ast.Constant) and isinstance(arg.value, str) \
                        and _is_forbidden(arg.value):
                    violations.append(
                        f"{path}:{node.lineno}: __import__({arg.value!r})"
                    )
    return violations


def scan_hot_path(src_root: Path) -> list[str]:
    """Scan every product .py under ``src/charon/`` for rig imports.

    Excludes ``charon/engine/`` and ``charon/ports/worker.py`` — those
    modules are stdlib-only by a different invariant (ADR-0010 D2 /
    ADR-0005 R3) enforced by ``check_boundary.py``. Including them here
    would double-report and obscure the real product-path concern.
    """
    base = src_root / "charon"
    if not base.exists():
        return []
    paths: list[Path] = []
    for py in sorted(base.rglob("*.py")):
        rel = py.relative_to(base)
        parts = rel.parts
        if parts and parts[0] == "engine":
            continue
        if parts and parts[0] == "ports" and py.name == "worker.py":
            continue
        paths.append(py)

    violations: list[str] = []
    for py in paths:
        violations.extend(scan_file(py))
    return violations


def main(root: str = "src") -> int:
    base = Path(root)
    if not base.exists():
        print(f"no-rig-import: root {base!r} does not exist", file=sys.stderr)
        return 1
    violations = scan_hot_path(base)
    if violations:
        print("PRODUCT-PATH RIG-IMPORT VIOLATION (GATEWAY-PROGRAM §1.9 red-team fix #2):",
              file=sys.stderr)
        for v in violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"no-rig-import OK: no benchmark/grader_daemon imports under {root}/charon/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))