#!/usr/bin/env python3
# @covers: arch
"""Architecture-layer audit tool — validates Charon's architectural invariants.

Checks:
1. Layer isolation: engine/ never imports from gateway, proxy_server, adapters,
   cli, config, connect, providers, secrets.
2. Gateway isolation: gateway.py, proxy_server.py never import from engine/.
3. No circular imports: walk full import graph, detect cycles.
4. Product-clean: no vendor/provider names hardcoded in engine/ or gateway/
   (string-literal scan, excluding docstrings and long templates).

NOTE (2026-07-21): the former "stdlib-only core" check was REMOVED per the
operator ADOPT-FIRST directive — a maintained runtime dependency is allowed and
no ADR is required to add one. Layer isolation, circular-import, and
product-clean invariants remain enforced; third-party imports are no longer a
violation.

Exit 0 on clean, 1 on violation. Diagnostics go to stderr.
"""
from __future__ import annotations

import ast
import sys
from collections import defaultdict
from pathlib import Path

# Repo root on sys.path so the gate contract resolves both when this file is run
# standalone (python3 tools/check_*.py, sys.path[0]=tools/) and when the test
# suite imports it as tools.check_* (sys.path[0]=repo root).
_GC_ROOT = Path(__file__).resolve().parent.parent
if str(_GC_ROOT) not in sys.path:
    sys.path.insert(0, str(_GC_ROOT))
from tools.gate_contract import emit_work_units  # noqa: E402

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


def _is_type_checking_test(test: ast.expr) -> bool:
    """True if *test* is ``TYPE_CHECKING`` or ``typing.TYPE_CHECKING``."""
    if isinstance(test, ast.Name):
        return test.id == "TYPE_CHECKING"
    if isinstance(test, ast.Attribute):
        return test.attr == "TYPE_CHECKING"
    return False


def _collect_type_checking_import_ids(tree: ast.AST) -> set[int]:
    """Collect ``id()`` of every Import/ImportFrom node guarded by an
    ``if TYPE_CHECKING:`` block. These execute only under a type checker, never at
    runtime, so they can never form a real (runtime) import cycle and must be
    excluded from the import graph (only the guarded body — not its ``else``)."""
    ids: set[int] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.If) and _is_type_checking_test(node.test):
            for stmt in node.body:
                for sub in ast.walk(stmt):
                    if isinstance(sub, (ast.Import, ast.ImportFrom)):
                        ids.add(id(sub))
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


def _resolve_import_target(
    node: ast.Import | ast.ImportFrom, pkg: str, mod: str,
) -> str | None:
    """Resolve an Import/ImportFrom node to an absolute charon module name, or None."""
    if isinstance(node, ast.Import):
        for alias in node.names:
            head = alias.name.split(".")[0]
            if head not in _STDLIB_TOPS and head != "charon":
                continue
            if alias.name == "charon" or alias.name.startswith("charon."):
                return alias.name
        return None
    if isinstance(node, ast.ImportFrom):
        target: str | None = None
        if node.level and node.level > 0:
            target = _resolve_relative(pkg, node.level, node.module)
        elif node.module:
            head = node.module.split(".")[0]
            if head not in _STDLIB_TOPS and head != "charon":
                return None
            target = node.module
        if target and (target == "charon" or target.startswith("charon.")):
            return target
    return None


def _scan_module_level_imports(
    src_root: Path,
) -> tuple[dict[tuple[str, str], str], set[tuple[str, str]]]:
    """Scan *src_root*/*.py for module-level charon imports.

    Returns:
      - bare_relative: ``{(source_file, sibling_name): parent_package}`` for
        ``from . import X`` forms (resolved to parent pkg, not sibling).
      - module_edges: ``{(source_mod, target_mod)}`` of module-level charon
        imports (excluding TYPE_CHECKING-guarded bodies).
    """
    base = src_root / "charon"
    bare_relative: dict[tuple[str, str], str] = {}
    module_edges: set[tuple[str, str]] = set()

    for py_file in sorted(base.rglob("*.py")):
        mod = _module_name(py_file)
        if mod is None:
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        pkg = _pkg_of(py_file)
        tc_ids = _collect_type_checking_import_ids(tree)

        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if id(node) in tc_ids:
                    continue
                target = _resolve_import_target(node, pkg, mod)
                if target:
                    # Record bare relative imports (from . import X)
                    # for remapping — AST code resolves these to parent pkg.
                    if (
                        isinstance(node, ast.ImportFrom)
                        and node.level is not None
                        and node.level > 0
                        and node.module is None
                    ):
                        for alias in node.names:
                            # The parent-package target from _resolve_import_target
                            # is the parent pkg (e.g. "charon" for level=1).
                            # We need to record that (rel_source_file, sibling_name)
                            # maps to this parent pkg.
                            rel_path = str(py_file.relative_to(src_root.parent))
                            bare_relative[(rel_path, alias.name)] = target
                    module_edges.add((mod, target))
    return bare_relative, module_edges


def _build_import_graph_from_graphify(
    src_root: Path, graph_path: Path,
    bare_relative: dict[tuple[str, str], str],
    module_edges: set[tuple[str, str]],
) -> dict[str, set[str]]:
    """Build the import graph from graphify's pre-computed graph.json.

    Only edges present in *module_edges* (module-level charon imports,
    excluding TYPE_CHECKING guards) are included.  ``from . import X``
    edges are remapped to the parent package.
    """
    import json

    data = json.loads(graph_path.read_text())
    nodes_by_id: dict[str, dict] = {}
    for n in data["nodes"]:
        nodes_by_id[n["id"]] = n

    prefix = f"{src_root}/charon/"
    graph: dict[str, set[str]] = defaultdict(set)

    for link in data["links"]:
        if link["relation"] not in ("imports", "imports_from"):
            continue

        source_sf = link.get("source_file", "")
        if not source_sf.startswith(prefix):
            continue
        source_mod = _module_name(Path(source_sf))
        if source_mod is None:
            continue

        target_node = nodes_by_id.get(link["target"])
        if target_node is None:
            continue
        target_sf = target_node.get("source_file", "")
        if not target_sf.startswith(prefix):
            continue
        target_mod = _module_name(Path(target_sf))
        if target_mod is None or target_mod == source_mod:
            continue

        # Check if this edge is a module-level import (skip TYPE_CHECKING-only).
        if (source_mod, target_mod) not in module_edges:
            continue

        # Remap from . import X to parent package.
        sibling_name = target_mod.split(".")[-1]
        if (source_sf, sibling_name) in bare_relative:
            target_mod = bare_relative[(source_sf, sibling_name)]

        graph[source_mod].add(target_mod)

    return dict(graph)


def _build_import_graph_from_ast(src_root: Path) -> dict[str, set[str]]:
    """Build import graph via from-scratch AST walk (fallback path).

    Used when graphify's pre-computed graph is not available.
    """
    graph: dict[str, set[str]] = defaultdict(set)
    base = src_root / "charon"
    for py_file in sorted(base.rglob("*.py")):
        mod = _module_name(py_file)
        if mod is None:
            continue
        tree = ast.parse(py_file.read_text(), filename=str(py_file))
        pkg = _pkg_of(py_file)
        tc_ids = _collect_type_checking_import_ids(tree)
        for node in ast.walk(tree):
            if isinstance(node, (ast.Import, ast.ImportFrom)):
                if id(node) in tc_ids:
                    continue
                target = _resolve_import_target(node, pkg, mod)
                if target:
                    graph[mod].add(target)
    return dict(graph)


def _build_import_graph(src_root: Path) -> dict[str, set[str]]:
    """Build a directed graph: module → {imported modules} for all
    src/charon/**/*.py.

    Prefers graphify's pre-computed graph (graphify-out/graph.json),
    falling back to a from-scratch AST walk when unavailable.
    """
    graphify_path = src_root.parent / "graphify-out" / "graph.json"
    if graphify_path.exists():
        bare_relative, module_edges = _scan_module_level_imports(src_root)
        return _build_import_graph_from_graphify(
            src_root, graphify_path, bare_relative, module_edges,
        )
    return _build_import_graph_from_ast(src_root)


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


# ── check 4: product-clean (vendor names in literals) ──────────────────────


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
    ("product-clean", check_product_clean),
]


def main(root: str = "src") -> int:
    base = Path(root)
    emit_work_units(len(sorted(base.rglob("*.py"))))
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
        f"arch OK: no layer-isolation, circular-import, "
        f"or vendor-name violations under {root}/"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1] if len(sys.argv) > 1 else "src"))
