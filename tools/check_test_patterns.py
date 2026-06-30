#!/usr/bin/env python3
# @covers: test-patterns
"""Test-pattern enforcement gate.

Scans test files and enforces:
  (a) No duplicate test-function names at module level (ERROR)
  (b) Every test function has a docstring (WARNING)
  (c) Parametrize usage ratio >= 1 per 10 test functions (WARNING)
  (d) No test function exceeds 50 lines (WARNING)

Stdlib only. Exit 0 on clean, 1 on error violations.
Warnings are printed but do not affect exit code unless --strict.
"""

from __future__ import annotations

import ast
import sys
from pathlib import Path

_PARAMETRIZE_TARGET_RATIO = 0.1
_MAX_LINES = 50


def _is_test_function(node: ast.AST, *, in_class: bool = False) -> bool:
    if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    if node.name.startswith("__"):
        return False
    if node.name.startswith("test_"):
        return True
    if node.name.startswith("_test_"):
        return True
    return False


def _is_parametrize_decorator(node: ast.expr) -> bool:
    if not isinstance(node, ast.Call):
        return False
    if not isinstance(node.func, ast.Attribute):
        return False
    if node.func.attr != "parametrize":
        return False
    if not isinstance(node.func.value, ast.Attribute):
        return False
    if node.func.value.attr != "mark":
        return False
    if not isinstance(node.func.value.value, ast.Name):
        return False
    return node.func.value.value.id == "pytest"


def _function_line_count(node: ast.FunctionDef | ast.AsyncFunctionDef) -> int:
    end = getattr(node, "end_lineno", None)
    if end is None:
        return sys.maxsize
    return end - node.lineno + 1


def _class_test_methods(
    class_node: ast.ClassDef,
) -> list[ast.FunctionDef | ast.AsyncFunctionDef]:
    methods: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    for node in ast.iter_child_nodes(class_node):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_test_function(node, in_class=True):
                methods.append(node)
    return methods


def check_file(path: Path) -> tuple[list[str], list[str]]:
    """Return (errors, warnings) for a single test file."""
    errors: list[str] = []
    warnings: list[str] = []
    source = path.read_text()

    try:
        tree = ast.parse(source)
    except SyntaxError:
        errors.append(f"{path}:1: syntax error — could not parse file")
        return errors, warnings

    test_funcs: list[ast.FunctionDef | ast.AsyncFunctionDef] = []
    parametrize_count = 0
    module_names: dict[str, int] = {}

    for node in ast.iter_child_nodes(tree):
        if isinstance(node, ast.ClassDef) and node.name.startswith("Test"):
            methods = _class_test_methods(node)
            test_funcs.extend(methods)
            for m in methods:
                for dec in m.decorator_list:
                    if _is_parametrize_decorator(dec):
                        parametrize_count += 1

        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if _is_test_function(node, in_class=False):
                test_funcs.append(node)
                name = node.name
                module_names[name] = module_names.get(name, 0) + 1
                for dec in node.decorator_list:
                    if _is_parametrize_decorator(dec):
                        parametrize_count += 1

    # (a) Duplicate module-level test function names
    for name, count in module_names.items():
        if count > 1:
            errors.append(
                f"{path}: duplicate test function name {name!r} "
                f"({count} occurrences — module-level shadowing)"
            )

    # (b) Docstring check on every test function
    for fn in test_funcs:
        if ast.get_docstring(fn) is None:
            warnings.append(
                f"{path}:{fn.lineno}: test function {fn.name!r} has no docstring"
            )

    # (c) Parametrize ratio
    total = len(test_funcs)
    if total > 0:
        ratio = parametrize_count / total
        if ratio < _PARAMETRIZE_TARGET_RATIO:
            warnings.append(
                f"{path}: parametrize ratio {ratio:.2f} "
                f"({parametrize_count} parametrize / {total} test funcs) "
                f"below target {_PARAMETRIZE_TARGET_RATIO:.2f}"
            )

    # (d) Line count check
    for fn in test_funcs:
        lines = _function_line_count(fn)
        if lines > _MAX_LINES:
            warnings.append(
                f"{path}:{fn.lineno}: test function {fn.name!r} "
                f"is {lines} lines (max {_MAX_LINES})"
            )

    return errors, warnings


def scan_tests(root: str) -> tuple[list[str], list[str]]:
    all_errors: list[str] = []
    all_warnings: list[str] = []
    base = Path(root)
    for py in sorted(base.rglob("test_*.py")):
        if "/__pycache__/" in str(py):
            continue
        errs, warns = check_file(py)
        all_errors.extend(errs)
        all_warnings.extend(warns)
    return all_errors, all_warnings


def main(argv: list[str] | None = None) -> int:
    if argv is None:
        argv = sys.argv

    strict = "--strict" in argv
    args = [a for a in argv[1:] if not a.startswith("-")]
    root = args[0] if args else "tests"

    errors, warnings = scan_tests(root)

    exit_code = 0
    if errors:
        print(f"test-patterns ERRORS ({len(errors)}):", file=sys.stderr)
        for e in errors:
            print(f"  {e}", file=sys.stderr)
        exit_code = 1

    warning_count = len(warnings)
    if warnings:
        label = "WARNINGS" if strict else "warnings"
        print(f"test-patterns {label} ({warning_count}):", file=sys.stderr)
        for w in warnings:
            print(f"  {w}", file=sys.stderr)
        if strict:
            exit_code = 1

    if exit_code == 0:
        verb = "clean"
    else:
        verb = "issues found"
    print(
        f"test-patterns: {verb} — "
        f"{len(errors)} errors, {warning_count} warnings "
        f"across {root}/"
    )
    return exit_code


if __name__ == "__main__":
    raise SystemExit(main())
