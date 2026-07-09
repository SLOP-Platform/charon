#!/usr/bin/env python3
# @covers: arch
"""Architecture-layer audit tool — validates Charon's architectural invariants.

Checks:
1. Layer isolation: engine/ never imports from gateway, proxy_server, adapters,
   cli, config, connect, providers, secrets.
2. Gateway isolation: gateway.py, proxy_server.py never import from engine/.
3. No circular imports: walk full import graph, detect cycles.
4. Stdlib-only core: src/charon/*.py uses only stdlib + charon.* imports.
5. Product-clean: no vendor/provider names hardcoded in engine/ or gateway/
   (string-literal scan, excluding docstrings and long templates).

Exit 0 on clean, 1 on violation. Diagnostics go to stderr.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

# ── constants ───────────────────────────────────────────────────────────────

_ENGINE_FORBIDDEN: frozenset[str] = frozenset({
    "gateway", "proxy_server", "adapters", "cli", "config",
    "connect", "providers", "secrets",
    # proxy_server decompose modules — same gateway boundary as proxy_server.
    "proxy_console_assets", "proxy_response", "console_router", "forwarder",
})

_VENDOR_NAMES: frozenset[str] = frozenset({
    "openai", "anthropic", "google", "cohere", "mistral",
    "deepseek", "groq", "together", "openrouter", "vertex",
    "bedrock", "azure", "replicate", "perplexity",
})

_STDLIB_TOPS: frozenset[str] = sys.stdlib_module_names
_STRING_LIMIT = 200  # strings longer than this are treated as templates/docs


# ── helpers ──────────────────────────────────────────────────────────────────


def _module_name(path: Path) -> str | None:
    """Return ``charon.foo.bar`` for a .py file under src/charon/."""
    try:
        idx = path.parts.index("charon")
    except ValueError:
        return None
    relative = ".".join(path.parts[idx:])
    if relative.endswith(".py"):
        relative = relative[:-3]
    if relative.endswith(".__init__"):
        relative = relative[:-9]
    return relative


def _pkg_of(path: Path) -> str:
    """Return the package path of *path*.

    Example: ``charon.engine`` for ``src/charon/engine/board.py``.
    """
    try:
        idx = path.parts.index("charon")
    except ValueError:
        return ""
    sub = list(path.parts[idx:])
    # drop filename (e.g. board.py) to get package dir
    sub.pop()
    return ".".join(sub)


def _resolve_relative(pkg: str, level: int, module: str | None) -> str:
    """Resolve a ``from {dots}{module} import ...`` to an absolute charon module name."""
    if level == 0:
        return module or ""
    parts = pkg.split(".") if pkg else []
    # level: 1 = current dir, 2 = parent, ...
    stay = max(0, len(parts) - (level - 1))
    resolved = parts[:stay]
    if module:
        resolved.append(module.replace("/", "."))
    return ".".join(resolved)


def _is_docstring(node: ast.AST, parent_body: list[ast.stmt], idx: int) -> bool:
    """Return True if *node* at *idx* in *parent_body* is a docstring expression."""
    if idx != 0:
        return False
    return (
        isinstance(node, ast.Expr)
        and isinstance(node.value, ast.Constant)
        and isinstance(node.value.value, str)
    )


def _collect_docstring_ids(tree: ast.AST) -> set[int]:
    """Collect ``id()`` of every docstring Constant node in *tree*."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            if node.body and isinstance(node.body[0], ast.Expr):
                val = node.body[0].value
                if isinstance(val, ast.Constant) and isinstance(val.value, str):
                    ids.add(id(val))
    return ids


# ── check 1: engine → forbidden imports ────────────────────────────────────


def check_engine_isolation(src_root: Path) -> list[str]:
    """Engine/ files must not import from gateway, proxy_server, adapters, etc."""
    violations: list[str] = []
    engine_dir = src_root / "charon" / "engine"
    if not engine_dir.exists():
        return violations

    for py_file in sorted(engine_dir.rglob("*.py")):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    if alias.name == "charon" or alias.name.startswith("charon."):
                        parts = alias.name.split(".")
                        for part in parts:
                            if part in _ENGINE_FORBIDDEN:
                                violations.append(
                                    f"{py_file}:{node.lineno}: engine→forbidden: "
                                    f"import {alias.name}"
                                )
                                break
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    pkg = _pkg_of(py_file)
                    resolved = _resolve_relative(pkg, node.level, node.module)
                    for part in resolved.split("."):
                        if part in _ENGINE_FORBIDDEN:
                            dots = "." * node.level
                            mod = f"{dots}{node.module or ''}"
                            violations.append(
                                f"{py_file}:{node.lineno}: engine→forbidden: "
                                f"from {mod} import ..."
                            )
                            break
                elif node.module and (node.module == "charon" or node.module.startswith("charon.")):
                    parts = node.module.split(".")
                    for part in parts:
                        if part in _ENGINE_FORBIDDEN:
                            violations.append(
                                f"{py_file}:{node.lineno}: engine→forbidden: "
                                f"from {node.module} import ..."
                            )
                            break
    return violations


# ── check 2: gateway → engine forbidden imports ────────────────────────────


def check_gateway_isolation(src_root: Path) -> list[str]:
    """gateway.py / proxy_server.py must not import from engine/."""
    violations: list[str] = []
    targets = [
        src_root / "charon" / "gateway.py",
        src_root / "charon" / "proxy_server.py",
    ]

    for py_file in targets:
        if not py_file.exists():
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    mod = alias.name
                    if mod == "charon.engine" or mod.startswith("charon.engine."):
                        violations.append(
                            f"{py_file}:{node.lineno}: gateway→engine: import {mod}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    pkg = _pkg_of(py_file)
                    resolved = _resolve_relative(pkg, node.level, node.module)
                    if "engine" in resolved.split("."):
                        dots = "." * node.level
                        mod = f"{dots}{node.module or ''}"
                        violations.append(
                            f"{py_file}:{node.lineno}: gateway→engine: from {mod} import ..."
                        )
                elif node.module and (
                    node.module == "charon.engine" or node.module.startswith("charon.engine.")
                ):
                    violations.append(
                        f"{py_file}:{node.lineno}: gateway→engine: from {node.module} import ..."
                    )
    return violations


# ── check 3: circular imports ───────────────────────────────────────────────


def _build_import_graph(src_root: Path) -> dict[str, set[str]]:
    """Build a directed graph: module → {imported modules} for all src/charon/**/*.py."""
    graph: dict[str, set[str]] = defaultdict(set)
    base = src_root / "charon"
    for py_file in sorted(base.rglob("*.py")):
        mod = _module_name(py_file)
        if mod is None:
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        pkg = _pkg_of(py_file)
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")[0]
                    if head not in _STDLIB_TOPS and head != "charon":
                        continue
                    if alias.name == "charon" or alias.name.startswith("charon."):
                        graph[mod].add(alias.name)
            elif isinstance(node, ast.ImportFrom):
                target: str | None = None
                if node.level and node.level > 0:
                    target = _resolve_relative(pkg, node.level, node.module)
                elif node.module:
                    head = node.module.split(".")[0]
                    if head not in _STDLIB_TOPS and head != "charon":
                        continue
                    target = node.module
                if target and (target == "charon" or target.startswith("charon.")):
                    graph[mod].add(target)
    return dict(graph)


def check_circular_imports(src_root: Path) -> list[str]:
    """Walk the import graph with DFS; report the first cycle found."""
    graph = _build_import_graph(src_root)

    WHITE, GRAY, BLACK = 0, 1, 2
    color: dict[str, int] = {m: WHITE for m in graph}

    def dfs(u: str, path: list[str]) -> list[str] | None:
        color[u] = GRAY
        path.append(u)
        for v in sorted(graph.get(u, set())):
            if v not in color:
                continue
            if color[v] == GRAY:
                idx = path.index(v)
                return path[idx:] + [v]
            if color[v] == WHITE:
                result = dfs(v, list(path))
                if result is not None:
                    return result
        color[u] = BLACK
        return None

    for mod in sorted(graph):
        if color[mod] == WHITE:
            cycle = dfs(mod, [])
            if cycle is not None:
                return [f"circular-import: {' → '.join(cycle)}"]
    return []


# ── check 4: stdlib-only core ───────────────────────────────────────────────


def check_stdlib_only(src_root: Path) -> list[str]:
    """Top-level ``src/charon/*.py`` files must use only stdlib + charon.* imports."""
    violations: list[str] = []
    for py_file in sorted((src_root / "charon").glob("*.py")):
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    head = alias.name.split(".")[0]
                    if head not in _STDLIB_TOPS and head != "charon" and head != "__future__":
                        violations.append(
                            f"{py_file}:{node.lineno}: stdlib-only: "
                            f"import {alias.name}"
                        )
            elif isinstance(node, ast.ImportFrom):
                if node.level and node.level > 0:
                    continue  # relative → intra-charon, always ok
                if node.module is None:
                    continue
                head = node.module.split(".")[0]
                if head not in _STDLIB_TOPS and head != "charon" and head != "__future__":
                    violations.append(
                        f"{py_file}:{node.lineno}: stdlib-only: "
                        f"from {node.module} import ..."
                    )
    return violations


# ── check 5: product-clean (vendor names in literals) ──────────────────────


def check_product_clean(src_root: Path) -> list[str]:
    """Scan engine/ + gateway/ files for vendor names in non-docstring string literals."""
    violations: list[str] = []
    paths: list[Path] = []
    engine_dir = src_root / "charon" / "engine"
    if engine_dir.exists():
        paths.extend(sorted(engine_dir.rglob("*.py")))
    for name in ("gateway.py", "proxy_server.py"):
        p = src_root / "charon" / name
        if p.exists():
            paths.append(p)

    for py_file in paths:
        try:
            tree = ast.parse(py_file.read_text(), filename=str(py_file))
        except SyntaxError:
            continue
        doc_ids = _collect_docstring_ids(tree)
        for node in ast.walk(tree):
            if not isinstance(node, ast.Constant):
                continue
            if not isinstance(node.value, str):
                continue
            if id(node) in doc_ids:
                continue
            if len(node.value) > _STRING_LIMIT:
                continue
            lower = node.value.lower()
            for kw in _VENDOR_NAMES:
                if kw in lower:
                    snippet = node.value[:80].replace("\n", "\\n")
                    violations.append(
                        f"{py_file}:{node.lineno}: product-clean: "
                        f"vendor name {kw!r} in string literal {snippet!r}"
                    )
                    break
    return violations


# ── main ────────────────────────────────────────────────────────────────────


_CHECKS = [
    ("engine isolation", check_engine_isolation),
    ("gateway isolation", check_gateway_isolation),
    ("circular imports", check_circular_imports),
    ("stdlib-only core", check_stdlib_only),
    ("product-clean", check_product_clean),
]


def main(root: str = "src") -> int:
    base = Path(root)
    all_violations: list[str] = []
    for name, fn in _CHECKS:
        violations = fn(base)
        for v in violations:
            all_violations.append(f"[{name}] {v}")

    if all_violations:
        print(
            f"arch: {len(all_violations)} violation(s)", file=sys.stderr,
        )
        for v in all_violations:
            print(f"  {v}", file=sys.stderr)
        return 1

    print(
        f"arch OK: no layer-isolation, circular-import, stdlib-only, "
        f"or vendor-name violations under {root}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))
