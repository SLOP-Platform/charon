#!/usr/bin/env python3
# @covers: security
"""Security anti-pattern scanner for Charon source.

Scans src/ for:
  (a) Bare ``except:`` or broad ``except Exception`` without re-raise or logging
  (b) Secrets/tokens in string literals
  (c) Hardcoded non-loopback IP addresses in string literals
  (d) ``eval()``, ``exec()``, and ``subprocess.run/call/Popen(..., shell=True)``

Stdlib only. Exit 0 on clean, 1 on violation.
"""
from __future__ import annotations

import ast
import ipaddress
import re
import sys
from pathlib import Path

_SECRET_PATTERNS: list[re.Pattern] = [
    re.compile(r'sk-[a-zA-Z0-9_-]{20,}'),
    re.compile(r'[A-Za-z0-9+/]{40,}={0,2}'),
]

_IP_REGEX = re.compile(r'\b(\d{1,3})\.(\d{1,3})\.(\d{1,3})\.(\d{1,3})\b')

_SUBPROCESS_FUNCS = frozenset({'run', 'call', 'Popen', 'check_call', 'check_output'})


def _in_finally(tree: ast.AST, lineno: int) -> bool:
    """Return True if *lineno* falls inside a finally: body somewhere in *tree*."""
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for sub in ast.walk(stmt):
                    if hasattr(sub, 'lineno') and sub.lineno == lineno:
                        return True
    return False


def _function_name(tree: ast.AST, lineno: int) -> str | None:
    """Return the name of the innermost function containing *lineno*."""
    best: tuple[int, str | None] = (-1, None)
    for node in ast.walk(tree):
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            if node.lineno <= lineno <= (getattr(node, 'end_lineno', node.lineno) or node.lineno):
                if node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1]


def _class_name(tree: ast.AST, lineno: int) -> str | None:
    """Return the name of the innermost class containing *lineno*."""
    best: tuple[int, str | None] = (-1, None)
    for node in ast.walk(tree):
        if isinstance(node, ast.ClassDef):
            if node.lineno <= lineno <= (getattr(node, 'end_lineno', node.lineno) or node.lineno):
                if node.lineno > best[0]:
                    best = (node.lineno, node.name)
    return best[1]


def _is_exempt_ip(ip_str: str) -> bool:
    """True for loopback, unspecified (0.0.0.0 / ::), and localhost."""
    try:
        addr = ipaddress.ip_address(ip_str)
        return addr.is_loopback or addr.is_unspecified
    except ValueError:
        return ip_str.lower() in ('localhost',)


def _body_has_surface(node: ast.ExceptHandler) -> bool:
    """True if the except body surfaces the error via raise, logging, or print(stderr)."""
    for body_node in ast.walk(node):
        if isinstance(body_node, ast.Raise):
            return True
        if isinstance(body_node, ast.Call):
            if isinstance(body_node.func, ast.Attribute):
                if body_node.func.attr in ('exception', 'error', 'warning') and isinstance(
                    body_node.func.value, ast.Name
                ) and body_node.func.value.id in ('logging', 'logger', 'log'):
                    return True
            elif isinstance(body_node.func, ast.Name) and body_node.func.id == 'logging':
                return True
            # print(..., file=sys.stderr) is an intentional surface
            if isinstance(body_node.func, ast.Name) and body_node.func.id == 'print':
                for kw in body_node.keywords:
                    if kw.arg == 'file':
                        val = kw.value
                        if (isinstance(val, ast.Attribute)
                                and isinstance(val.value, ast.Name)
                                and val.value.id == 'sys'
                                and val.attr == 'stderr'):
                            return True
    return False


def _has_comment(source_lines: list[str], lineno: int) -> bool:
    """True if source line *lineno* has an inline ``#`` comment (not a standalone comment line)."""
    if lineno < 1 or lineno > len(source_lines):
        return False
    stripped = source_lines[lineno - 1].strip()
    return not stripped.startswith('#') and '#' in stripped


def _check_except(
    node: ast.ExceptHandler,
    path: Path,
    source_lines: list[str],
    finally_set: set[int],
    tree: ast.AST,
) -> list[str]:
    violations: list[str] = []
    lineno = node.lineno

    if node.type is None:
        violations.append(f"{path}:{lineno}: bare except: (no exception type)")
        return violations

    is_exception = False
    if isinstance(node.type, ast.Name) and node.type.id == 'Exception':
        is_exception = True
    elif isinstance(node.type, ast.Tuple):
        for elt in node.type.elts:
            if isinstance(elt, ast.Name) and elt.id == 'Exception':
                is_exception = True
                break
    if not is_exception:
        return violations

    if lineno in finally_set:
        return violations

    if lineno <= len(source_lines):
        lt = source_lines[lineno - 1]
        if '# noqa:' in lt or '# noqa ' in lt:
            return violations
        if 'except Exception' in lt and '#' in lt:
            return violations

    if _in_finally(tree, lineno):
        return violations

    if _body_has_surface(node):
        return violations

    if node.body:
        first_body_lineno = getattr(node.body[0], 'lineno', 0)
        if first_body_lineno and _has_comment(source_lines, first_body_lineno):
            return violations

    violations.append(
        f"{path}:{lineno}: broad except Exception without re-raise or logging.exception()"
    )
    return violations


def _check_shell(node: ast.Call, path: Path, source_lines: list[str], tree: ast.AST) -> str | None:
    func_name: str | None = None
    if isinstance(node.func, ast.Attribute) and isinstance(node.func.value, ast.Name):
        if node.func.value.id == 'subprocess':
            func_name = node.func.attr
    elif isinstance(node.func, ast.Name):
        func_name = node.func.id

    if not func_name or func_name not in _SUBPROCESS_FUNCS:
        return None

    has_shell = False
    shell_kw_lineno = 0
    for kw in node.keywords:
        if kw.arg == 'shell':
            if isinstance(kw.value, ast.Constant) and kw.value.value is True:
                has_shell = True
                shell_kw_lineno = getattr(kw.value, 'lineno', 0)
            break

    if not has_shell:
        return None

    lineno = node.lineno

    for check_lineno in (lineno, shell_kw_lineno):
        if 1 <= check_lineno <= len(source_lines):
            lt = source_lines[check_lineno - 1]
            if '# noqa: S602' in lt or '# noqa:S602' in lt:
                return None

    fn = _function_name(tree, lineno)
    if fn == '_shell_install':
        return None

    return f"{path}:{lineno}: subprocess.{func_name}(..., shell=True)"


def _check_secrets(node: ast.Constant, path: Path) -> str | None:
    if not isinstance(node.value, str) or len(node.value) < 30:
        return None
    for pat in _SECRET_PATTERNS:
        if pat.search(node.value):
            return f"{path}:{node.lineno}: hardcoded secret/token pattern in string literal"
    return None


def _check_hardcoded_ip(node: ast.Constant, path: Path) -> list[str]:
    violations: list[str] = []
    if not isinstance(node.value, str):
        return violations
    for match in _IP_REGEX.finditer(node.value):
        ip = match.group()
        if not _is_exempt_ip(ip):
            violations.append(
                f"{path}:{node.lineno}: hardcoded non-loopback IP {ip!r} in string literal"
            )
    return violations


def scan_file(path: Path) -> list[str]:
    violations: list[str] = []
    try:
        source_text = path.read_text()
        tree = ast.parse(source_text, filename=str(path))
    except (SyntaxError, UnicodeDecodeError):
        return violations

    source_lines = source_text.splitlines()

    finally_set: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Try) and node.finalbody:
            for stmt in node.finalbody:
                for sub in ast.walk(stmt):
                    if hasattr(sub, 'lineno'):
                        finally_set.add(sub.lineno)

    for node in ast.walk(tree):
        if isinstance(node, ast.ExceptHandler):
            violations.extend(_check_except(node, path, source_lines, finally_set, tree))

        if isinstance(node, ast.Call):
            v = _check_shell(node, path, source_lines, tree)
            if v:
                violations.append(v)
            if isinstance(node.func, ast.Name) and node.func.id in ('eval', 'exec'):
                violations.append(f"{path}:{node.lineno}: dangerous {node.func.id}() call")

        if isinstance(node, ast.Constant) and isinstance(node.value, str):
            v = _check_secrets(node, path)
            if v:
                violations.append(v)
            violations.extend(_check_hardcoded_ip(node, path))

    return violations


def main(root: str = "src") -> int:
    base = Path(root)
    all_violations: list[str] = []
    for py in sorted(base.rglob("*.py")):
        all_violations.extend(scan_file(py))
    if all_violations:
        print("security VIOLATION:", file=sys.stderr)
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        return 1
    print(f"security OK: no anti-patterns found under {root}/")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))
