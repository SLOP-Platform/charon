"""Gate — inert_code: catch UNREGISTERED-inert code (built but never called).

META gate: one AST invariant over ALL symbols, not per-symbol.

Rules:
- Build a call graph of the target project's source tree via stdlib `ast`.
- Compute reachability from entrypoints (pyproject [project.scripts], __main__
  modules, and modules imported by them).
- A public top-level symbol (function/class) with ZERO production callers
  (unreachable) AND not registered as a KSF module AND not annotated
  `@inert_by_design` (must carry a reason/ticket) = INERT = RED.
- Excluded: test files, dunders, names in `__all__`, and `@inert_by_design`.

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/inert_code.py`` (Keystone Framework, a
sibling development checkout — not a runtime or install-time dependency).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only change from the KSF original is the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package).
Everything else — including the KSF-native
``check_inert_code(db_path, manifest, modules)`` signature — is untouched;
see ``tools/check_inert_code.py`` for the Charon-side adapter that supplies
those KSF-shaped arguments. Do not hand-edit the logic below; re-copy from
KSF and re-apply this header if the upstream detector changes. See
``tools/_vendor/README.md``.
"""

from __future__ import annotations

import ast
import json
import tomllib
from pathlib import Path
from typing import Any

from tools._vendor.ksf_gate_result import GateResult


_EXCLUDE_DIRS = {
    "tests",
    "test",
    ".ksf",
    ".git",
    "__pycache__",
    ".venv",
    ".pytest_cache",
    ".github",
}


class _ModuleInfo:
    """Static analysis summary for one Python module."""

    def __init__(self) -> None:
        self.definitions: dict[str, ast.AST] = {}  # module-level func/class nodes
        self.calls: set[str] = set()               # unresolved call names
        self.value_refs: set[str] = set()          # names used as first-class values
        self.imports: dict[str, str] = {}          # alias -> fully-qualified module
        self.from_imports: dict[str, tuple[str, str | None]] = {}  # alias -> (module, orig_name)
        self.has_main_guard = False
        self.all_names: set[str] = set()           # names exported via __all__


def _is_excluded_dir(p: Path) -> bool:
    return any(part in _EXCLUDE_DIRS for part in p.parts)


def _is_test_file(p: Path) -> bool:
    name = p.name
    return name.startswith("test_") or name.endswith("_test.py")


def _module_dotted_name(repo_root: Path, path: Path) -> str:
    """Convert repo-relative path to dotted module name, dropping __init__."""
    rel = path.relative_to(repo_root)
    parts = rel.with_suffix("").parts
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def _gather_source_files(repo_root: Path) -> list[Path]:
    files: list[Path] = []
    for pyfile in repo_root.rglob("*.py"):
        if _is_excluded_dir(pyfile) or _is_test_file(pyfile):
            continue
        files.append(pyfile)
    return files


def _parse_file(path: Path) -> ast.AST | None:
    try:
        return ast.parse(path.read_text())
    except SyntaxError:
        return None


def _call_name(func: ast.expr) -> str | None:
    """Extract dotted name from a Call node (e.g. a.b.c)."""
    if isinstance(func, ast.Name):
        return func.id
    if isinstance(func, ast.Attribute):
        prefix = _call_name(func.value)
        if prefix:
            return f"{prefix}.{func.attr}"
    return None


def _collect_value_refs(tree: ast.AST, info: _ModuleInfo) -> None:
    """Collect names used as first-class values (not just function calls).

    This catches patterns like ``set_defaults(func=cmd_gate)``,
    ``registry[cmd_gate] = ...``, or ``__all__ = [check_wiring_alignment]``
    (where the imported name is listed as a string literal).
    """
    for node in ast.walk(tree):
        if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
            info.value_refs.add(node.id)


def _has_inert_by_design(node: ast.AST) -> bool:
    """True if node carries ``@inert_by_design("reason")`` with a non-empty reason."""
    if not hasattr(node, "decorator_list"):
        return False
    for deco in node.decorator_list:
        if isinstance(deco, ast.Call):
            if isinstance(deco.func, ast.Name) and deco.func.id == "inert_by_design":
                for arg in deco.args:
                    if (
                        isinstance(arg, ast.Constant)
                        and isinstance(arg.value, str)
                        and arg.value.strip()
                    ):
                        return True
    return False


def _public_symbols(info: _ModuleInfo) -> dict[str, ast.AST]:
    """Return module-level definitions whose names are public (not dunder, not _)."""
    result: dict[str, ast.AST] = {}
    for name, node in info.definitions.items():
        if name.startswith("_"):
            continue
        if name.startswith("__") and name.endswith("__"):
            continue
        result[name] = node
    return result


def _analyze_module(tree: ast.AST, mod_name: str, is_init: bool = False) -> _ModuleInfo:
    """Parse a module AST into a ``_ModuleInfo``."""
    info = _ModuleInfo()

    # top-level imports, definitions, and __all__
    for child in ast.iter_child_nodes(tree):
        if isinstance(child, ast.Import):
            for alias in child.names:
                local = alias.asname if alias.asname else alias.name
                info.imports[local] = alias.name
        elif isinstance(child, ast.ImportFrom):
            module = child.module or ""
            if child.level > 0:
                parts = mod_name.split(".")
                # __init__.py files have the package name as mod_name (we stripped
                # the trailing __init__).  For those, ``from .module`` resolves inside
                # the current package (drop 0).  For a regular .py module the import
                # is relative to the parent package (drop = level).
                drop = child.level - 1 if is_init else child.level
                base = ".".join(parts[: max(0, len(parts) - drop)])
                if module:
                    module = base + "." + module if base else module
                else:
                    module = base
            for alias in child.names:
                local = alias.asname if alias.asname else alias.name
                if child.module is None and alias.name:
                    # from . import foo  => foo is a submodule
                    full_mod = module + "." + alias.name if module else alias.name
                    info.imports[local] = full_mod
                else:
                    info.from_imports[local] = (module, alias.name)
        elif isinstance(child, ast.Assign):
            for target in child.targets:
                if isinstance(target, ast.Name) and target.id == "__all__":
                    if isinstance(child.value, (ast.List, ast.Tuple)):
                        for elt in child.value.elts:
                            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                                info.all_names.add(elt.value)
        elif isinstance(child, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            info.definitions[child.name] = child

    # scan whole tree for calls, first-class value refs, and __main__ guards
    for node in ast.walk(tree):
        if isinstance(node, ast.Call):
            name = _call_name(node.func)
            if name:
                info.calls.add(name)
        elif isinstance(node, ast.Name):
            if isinstance(node.ctx, ast.Load) and node.id in info.definitions:
                info.value_refs.add(node.id)
        elif isinstance(node, ast.If):
            test = node.test
            if isinstance(test, ast.Compare) and isinstance(test.left, ast.Name):
                if test.left.id == "__name__":
                    for op in test.ops:
                        if isinstance(op, ast.Eq):
                            for comp in test.comparators:
                                if isinstance(comp, ast.Constant) and comp.value == "__main__":
                                    info.has_main_guard = True

    # Also collect imported names used as values (e.g. decorators, kwargs)
    _collect_value_refs(tree, info)

    # Scan entire tree for nested ImportFrom nodes so aliases in try/except or
    # local scopes are available for best-effort resolution.
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level > 0:
                parts = mod_name.split(".")
                drop = node.level - 1 if is_init else node.level
                base = ".".join(parts[: max(0, len(parts) - drop)])
                if module:
                    module = base + "." + module if base else module
                else:
                    module = base
            for alias in node.names:
                local = alias.asname if alias.asname else alias.name
                if local not in info.from_imports and local not in info.imports:
                    if node.module is None and alias.name:
                        full_mod = module + "." + alias.name if module else alias.name
                        info.imports[local] = full_mod
                    else:
                        info.from_imports[local] = (module, alias.name)

    return info


def _entrypoint_modules(repo_root: Path, modules_info: dict[str, _ModuleInfo]) -> set[str]:
    """Derive entrypoint module set from pyproject.toml scripts, entrypoints.json,
    and __main__ guards."""
    eps: set[str] = set()

    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text())
            scripts = data.get("project", {}).get("scripts", {})
            for spec in scripts.values():
                if isinstance(spec, str) and ":" in spec:
                    eps.add(spec.split(":")[0])
        except Exception:
            pass

    ep_file = repo_root / ".ksf" / "entrypoints.json"
    if ep_file.exists():
        try:
            with ep_file.open() as f:
                data = json.load(f)
                for spec in data.values():
                    if isinstance(spec, str) and ":" in spec:
                        eps.add(spec.split(":")[0])
        except Exception:
            pass

    for mod_name, info in modules_info.items():
        if info.has_main_guard:
            eps.add(mod_name)

    return eps


def _find_module(dotted: str, all_modules: set[str]) -> str | None:
    if dotted in all_modules:
        return dotted
    # DETERMINISM: iterate sorted — all_modules is a set, and returning the FIRST
    # suffix-match over unseeded set order made reachability (hence the whole dead-set)
    # depend on PYTHONHASHSEED, so the merge gate returned different verdicts on identical
    # code. Sorted first-match is stable. (Local patch to vendored KSF; upstream the same.)
    for m in sorted(all_modules):
        if m == dotted or m.endswith("." + dotted):
            return m
    return None


def _resolve_call(
    call_name: str, mod_name: str, info: _ModuleInfo, all_modules: set[str]
) -> str | None:
    """Best-effort resolve a call dotted name to ``module.symbol``."""
    if "." in call_name:
        head, tail = call_name.split(".", 1)
        if head in info.imports:
            real_mod = info.imports[head]
            candidate = f"{real_mod}.{tail}"
            found = _find_module(candidate, all_modules)
            return found if found else candidate
        if head in info.from_imports:
            mod, orig = info.from_imports[head]
            resolved_mod = _find_module(mod, all_modules) if mod else mod_name
            if resolved_mod is None:
                resolved_mod = mod
            candidate = f"{resolved_mod}.{tail}"
            found = _find_module(candidate, all_modules)
            return found if found else candidate
        # local submodule path
        candidate = f"{mod_name}.{call_name}"
        found = _find_module(candidate, all_modules)
        return found if found else candidate
    else:
        if call_name in info.definitions:
            return f"{mod_name}.{call_name}"
        if call_name in info.from_imports:
            mod, orig = info.from_imports[call_name]
            resolved_mod = _find_module(mod, all_modules) if mod else mod_name
            if resolved_mod is None:
                resolved_mod = mod
            if orig:
                return f"{resolved_mod}.{orig}"
            return f"{resolved_mod}.{call_name}"
        return None


def _is_entrypoint_callable(mod_name: str, sym_name: str, repo_root: Path) -> bool:
    """Check whether (mod_name, sym_name) is referenced by pyproject scripts or
    static entrypoints.json."""
    pyproject = repo_root / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text())
            scripts = data.get("project", {}).get("scripts", {})
            for spec in scripts.values():
                if isinstance(spec, str) and ":" in spec:
                    m, s = spec.split(":", 1)
                    # support both bare module and src-prefixed module names
                    if s == sym_name and (
                        m == mod_name
                        or mod_name.endswith("." + m)
                    ):
                        return True
        except Exception:
            pass

    ep_file = repo_root / ".ksf" / "entrypoints.json"
    if ep_file.exists():
        try:
            with ep_file.open() as f:
                data = json.load(f)
                for spec in data.values():
                    if isinstance(spec, str) and ":" in spec:
                        m, s = spec.split(":", 1)
                        if s == sym_name and (
                            m == mod_name
                            or mod_name.endswith("." + m)
                        ):
                            return True
        except Exception:
            pass

    return False


def _normalized_mod_name(mod_name: str) -> str:
    """Strip common source-root prefixes for comparison with registered names."""
    for prefix in ("src.", "lib.", "source."):
        if mod_name.startswith(prefix):
            return mod_name[len(prefix) :]
    return mod_name


def _is_registered(mod_name: str, registered_names: set[str]) -> bool:
    norm = _normalized_mod_name(mod_name)
    for reg in registered_names:
        if norm == reg or norm.startswith(reg + "."):
            return True
    return False


def check_inert_code(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    """Run the inert-code gate."""
    repo_root = db_path.parent.parent
    gaps: list[str] = []
    messages: list[str] = []

    source_files = _gather_source_files(repo_root)
    modules_info: dict[str, _ModuleInfo] = {}
    for pyfile in source_files:
        mod_name = _module_dotted_name(repo_root, pyfile)
        tree = _parse_file(pyfile)
        if tree is None:
            continue
        is_init = pyfile.name == "__init__.py"
        modules_info[mod_name] = _analyze_module(tree, mod_name, is_init)

    all_modules = set(modules_info.keys())
    entry_mods = _entrypoint_modules(repo_root, modules_info)

    # Normalize entry-mod names returned from pyproject / entrypoints.json so
    # they match the dotted module names we computed from source tree paths.
    def _norm_entry_mod(name: str) -> str | None:
        if name in all_modules:
            return name
        for m in sorted(all_modules):  # DETERMINISM: stable first-match (see _find_module)
            if m == name or m.endswith("." + name):
                return m
        return None

    entry_mods = set()
    for ep in _entrypoint_modules(repo_root, modules_info):
        n = _norm_entry_mod(ep)
        if n:
            entry_mods.add(n)

    # BFS over module import graph to find all reachable modules
    reachable_modules: set[str] = set()
    queue = list(entry_mods)
    while queue:
        current = queue.pop(0)
        if current in reachable_modules:
            continue
        reachable_modules.add(current)
        info = modules_info.get(current)
        if info is None:
            continue
        # follow imports to internal modules
        for alias, full_mod in info.imports.items():
            found = _find_module(full_mod, all_modules)
            if found and found not in reachable_modules:
                queue.append(found)
        for alias, (mod, orig) in info.from_imports.items():
            found = _find_module(mod, all_modules)
            if found and found not in reachable_modules:
                queue.append(found)

    # Build set of resolved referenced symbols from reachable modules.
    # Includes both direct calls AND first-class value references.
    referenced_symbols: set[str] = set()
    for mod_name, info in modules_info.items():
        if mod_name not in reachable_modules:
            continue
        for call in info.calls:
            resolved = _resolve_call(call, mod_name, info, all_modules)
            if resolved:
                referenced_symbols.add(resolved)
        for ref in info.value_refs:
            resolved = _resolve_call(ref, mod_name, info, all_modules)
            if resolved:
                referenced_symbols.add(resolved)

    # Build set of symbols exported via __all__ across ALL modules (exported
    # public API is a first-class-reachability contract regardless of whether the
    # re-exporting module itself is reachable).
    exported_symbols: set[str] = set()
    for mod_name, info in modules_info.items():
        for name in info.all_names:
            resolved = _resolve_call(name, mod_name, info, all_modules)
            if resolved:
                exported_symbols.add(resolved)

    # Also scan test files and .ksf red-proof files for reference edges.
    # They are real callers; we use their imports/calls to mark production
    # symbols reachable without flagging test files themselves.
    test_ref_files = [
        p
        for p in repo_root.rglob("*.py")
        if p not in source_files and not any(part in (".venv", "__pycache__") for part in p.parts)
    ]
    for pyfile in test_ref_files:
        mod_name = _module_dotted_name(repo_root, pyfile)
        tree = _parse_file(pyfile)
        if tree is None:
            continue
        is_init = pyfile.name == "__init__.py"
        info = _analyze_module(tree, mod_name, is_init)
        for call in info.calls:
            resolved = _resolve_call(call, mod_name, info, all_modules)
            if resolved:
                referenced_symbols.add(resolved)
        for ref in info.value_refs:
            resolved = _resolve_call(ref, mod_name, info, all_modules)
            if resolved:
                referenced_symbols.add(resolved)

    registered_names = {m["name"] for m in modules}

    for mod_name, info in modules_info.items():
        public = _public_symbols(info)
        if not public:
            continue

        is_reg = _is_registered(mod_name, registered_names)

        for sym_name, node in public.items():
            full_sym = f"{mod_name}.{sym_name}"

            if _has_inert_by_design(node):
                continue
            if sym_name in info.all_names:
                continue
            if full_sym in referenced_symbols:
                continue
            if full_sym in exported_symbols:
                continue
            if _is_entrypoint_callable(mod_name, sym_name, repo_root):
                continue

            if not is_reg:
                gaps.append("inert-code")
                messages.append(
                    f"inert-code: {full_sym} unreachable (0 callers) and not registered"
                )

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
