"""§5.1 semantic-independence proof engine (DSGN-WCI-5-1-PROOF).

Four deterministic signals certify whether two work units are semantically
independent — strictly stronger than owns-disjointness.  The certificate, when
positive, permits ``merge_after`` concurrency in ``board.claimable`` (F1
condition i).  Without a certificate (or with a failed one), ``merge_after`` is
conservatively demoted to a normal ``depends_on`` (F1 third branch).

All signals are pure functions of source files + config files — no LLM,
no clock, no RNG, no network.  Stdlib-only (ADR-0010 D2).
"""
from __future__ import annotations

import ast
import json
import pathlib
from dataclasses import dataclass, field


@dataclass
class IndependenceCertificate:
    unit_a: str
    unit_b: str
    proven: bool
    signal_results: dict[str, bool] = field(default_factory=dict)


# ------------------------------------------------------------------ public API

def compute_certificate(
    owns_a: list[str],
    owns_b: list[str],
    id_a: str,
    id_b: str,
    repo_root: str | None = None,
    config_dir: str | None = None,
) -> IndependenceCertificate:
    """Compute the semantic-independence certificate for a merge_after(A,B) pair.

    ``owns_a`` / ``owns_b`` are the owned file paths of each unit.
    ``id_a`` / ``id_b`` label the certificate (for audit, not computation).
    ``repo_root`` is the repo directory (defaults to cwd).
    ``config_dir`` is the Charon config dir (defaults to ``~/.charon``).
    """
    root = pathlib.Path(repo_root or ".")
    cfg_dir = pathlib.Path(config_dir or pathlib.Path.home() / ".charon")

    s1 = _signal1_import_reachability(owns_a, owns_b, root)
    s2 = _signal2_shared_symbols(owns_a, owns_b, root)
    s3 = _signal3_shared_config(owns_a, owns_b, root, cfg_dir)
    s4 = _signal4_test_cofailure(owns_a, owns_b, root)

    cert = IndependenceCertificate(
        unit_a=id_a,
        unit_b=id_b,
        proven=s1 and s2 and s3 and s4,
        signal_results={"s1_import": s1, "s2_symbol": s2, "s3_config": s3, "s4_test": s4},
    )
    return cert


# --------------------------------------------------- signal 1: import reachability

def _signal1_import_reachability(
    owns_a: list[str], owns_b: list[str], root: pathlib.Path
) -> bool:
    graph = _build_import_graph(root)
    reachable_a = _transitive_reachability(owns_a, graph)
    reachable_b = _transitive_reachability(owns_b, graph)
    files_a = _module_to_files(reachable_a)
    files_b = _module_to_files(reachable_b)
    owns_a_set = set(owns_a)
    owns_b_set = set(owns_b)
    # A reaches B: any file reachable from A is owned by B
    # B reaches A: any file reachable from B is owned by A
    if files_b & owns_a_set or files_a & owns_b_set:
        return False
    return True


def _build_import_graph(root: pathlib.Path) -> dict[str, set[str]]:
    """Parse the import graph of all ``src/charon/`` modules.

    Returns mapping of canonical module → set of imported canonical module names.
    Follows re-export chains via ``__init__.py``.
    """
    graph: dict[str, set[str]] = {}
    src_root = root / "src" / "charon"
    if not src_root.is_dir():
        return graph

    for py_path in sorted(src_root.rglob("*.py")):
        rel = py_path.relative_to(src_root)
        module = _path_to_module(rel)
        graph[module] = set()
        try:
            tree = ast.parse(py_path.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    graph[module].add(_resolve_module(alias.name, module, graph))
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    resolved = _resolve_module(node.module, module, graph)
                    graph[module].add(resolved)

    # Follow re-export chains: if __init__.py imports from submodule, add
    # indirect edges so ``from pkg import X`` reaches submodule.X transitively.
    expanded: dict[str, set[str]] = {m: set(imports) for m, imports in graph.items()}
    changed = True
    while changed:
        changed = False
        for _module, imports in expanded.items():
            for imp in list(imports):
                if imp in expanded:
                    for indirect in expanded[imp]:
                        if indirect not in imports:
                            imports.add(indirect)
                            changed = True
    return expanded


def _path_to_module(rel: pathlib.Path) -> str:
    parts = list(rel.parts)
    if parts[-1] == "__init__.py":
        parts = parts[:-1]
    else:
        parts[-1] = parts[-1].replace(".py", "")
    return ".".join(parts)


def _resolve_module(
    name: str, from_module: str, graph: dict[str, set[str]]
) -> str:
    """Resolve a relative or absolute import to a canonical module name
    (relative to src/charon/)."""
    if name.startswith("."):
        parts = from_module.split(".")
        depth = len(name) - len(name.lstrip("."))
        base = parts[:-depth] if depth <= len(parts) else []
        remainder = name.lstrip(".")
        if remainder:
            return ".".join(base + [remainder])
        return ".".join(base)
    # Absolute import starting with charon. → strip prefix
    if name.startswith("charon."):
        return name[len("charon."):]
    return name


def _transitive_reachability(
    files: list[str], graph: dict[str, set[str]]
) -> set[str]:
    """All module names transitively reachable from the given files."""
    start_modules: set[str] = set()
    for f in files:
        mod = _file_to_module(f)
        if mod in graph:
            start_modules.add(mod)

    reachable: set[str] = set()
    stack = list(start_modules)
    while stack:
        cur = stack.pop()
        if cur in reachable:
            continue
        reachable.add(cur)
        for imp in graph.get(cur, ()):
            if imp not in reachable:
                stack.append(imp)
    return reachable


def _module_to_files(modules: set[str]) -> set[str]:
    """Convert module names to repo-relative file paths."""
    files: set[str] = set()
    for m in modules:
        parts = m.split(".")
        files.add("src/charon/" + "/".join(parts) + ".py")
        files.add("src/charon/" + "/".join(parts) + "/__init__.py")
    return files


def _file_to_module(f: str) -> str:
    """Convert an owns file path to a module name (relative to src/charon/)."""
    if f.startswith("src/charon/"):
        rel = f[len("src/charon/"):]
    else:
        return ""
    if rel.endswith("/__init__.py"):
        rel = rel.replace("/__init__.py", "")
    elif rel.endswith(".py"):
        rel = rel.removesuffix(".py")
    return rel.replace("/", ".")


# --------------------------------------------------------- signal 2: shared symbols

def _signal2_shared_symbols(
    owns_a: list[str], owns_b: list[str], root: pathlib.Path
) -> bool:
    writes_a, reads_a = _extract_symbols(owns_a, root)
    writes_b, reads_b = _extract_symbols(owns_b, root)
    if (writes_a & reads_b) or (writes_b & reads_a):
        return False
    return True


def _extract_symbols(
    files: list[str], root: pathlib.Path
) -> tuple[set[str], set[str]]:
    """Extract module-level write-set and read-set from a set of files."""
    writes: set[str] = set()
    reads: set[str] = set()

    for f in files:
        path = root / f
        if not path.is_file():
            continue
        try:
            tree = ast.parse(path.read_text())
        except SyntaxError:
            continue

        for node in ast.iter_child_nodes(tree):
            if isinstance(node, ast.ImportFrom):
                for alias in node.names:
                    name = alias.asname or alias.name
                    reads.add(name)
            elif isinstance(node, ast.Import):
                for alias in node.names:
                    name = alias.asname or (
                        alias.name.split(".")[-1] if "." in alias.name else alias.name
                    )
                    reads.add(name)
            writes.update(_collect_writes(node))

        # Walk all nodes for read detection (not just top-level children).
        for node in ast.walk(tree):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Load):
                reads.add(node.id)

    return writes, reads


def _collect_writes(node: ast.AST) -> set[str]:
    """Collect names that are written at module scope."""
    names: set[str] = set()
    if isinstance(node, ast.Assign):
        for target in node.targets:
            names.update(_target_names(target))
    elif isinstance(node, ast.AugAssign):
        names.update(_target_names(node.target))
    elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
        # Check decorators for mutating calls (e.g. @registry.register)
        for dec in node.decorator_list:
            if isinstance(dec, ast.Call):
                if isinstance(dec.func, ast.Attribute):
                    names.update(_target_names(dec.func.value))
                elif isinstance(dec.func, ast.Name):
                    names.add(dec.func.id)
    return names


def _collect_reads(node: ast.AST) -> set[str]:
    """Collect names that are read at module scope."""
    names: set[str] = set()
    for child in ast.walk(node):
        if isinstance(child, ast.Name) and isinstance(child.ctx, ast.Load):
            names.add(child.id)
    return names


def _target_names(node: ast.AST) -> set[str]:
    """Flatten assignment targets to name set."""
    names: set[str] = set()
    if isinstance(node, ast.Name):
        names.add(node.id)
    elif isinstance(node, (ast.Tuple, ast.List)):
        for elt in node.elts:
            names.update(_target_names(elt))
    elif isinstance(node, ast.Attribute):
        names.update(_target_names(node.value))
    elif isinstance(node, ast.Starred):
        names.update(_target_names(node.value))
    return names


# --------------------------------------------------------- signal 3: shared config

def _signal3_shared_config(
    owns_a: list[str], owns_b: list[str],
    root: pathlib.Path, config_dir: pathlib.Path,
) -> bool:
    config_keys = _extract_config_keys(config_dir)
    keys_a = _find_config_refs(owns_a, root, config_keys)
    keys_b = _find_config_refs(owns_b, root, config_keys)
    if keys_a & keys_b:
        return False
    return True


def _extract_config_keys(config_dir: pathlib.Path) -> set[tuple[str, str]]:
    """Extract (filename, top_level_key) pairs from all config files."""
    keys: set[tuple[str, str]] = set()
    if not config_dir.is_dir():
        return keys
    for cf in sorted(config_dir.glob("*.json")):
        try:
            data = json.loads(cf.read_text())
        except (json.JSONDecodeError, OSError):
            continue
        if isinstance(data, dict):
            for k in data:
                keys.add((cf.name, k))
    return keys


def _find_config_refs(
    files: list[str], root: pathlib.Path, config_keys: set[tuple[str, str]]
) -> set[tuple[str, str]]:
    """Find config key references in owned source files."""
    refs: set[tuple[str, str]] = set()
    for f in files:
        path = root / f
        if not path.is_file():
            continue
        try:
            text = path.read_text()
        except OSError:
            continue
        for cfile, key in config_keys:
            if key in text:
                refs.add((cfile, key))
    return refs


# --------------------------------------------------------- signal 4: test co-failure

_MAP_SUFFIXES = ("_test.py", "/test_", "/tests/")


def _signal4_test_cofailure(
    owns_a: list[str], owns_b: list[str], root: pathlib.Path
) -> bool:
    tests_a = _find_test_files(owns_a, root)
    tests_b = _find_test_files(owns_b, root)
    if not tests_a or not tests_b:
        return False
    if tests_a & tests_b:
        return False
    if _test_imports_from(tests_a, owns_b, root) or _test_imports_from(tests_b, owns_a, root):
        return False
    if _conftest_coupling(tests_a, tests_b, root):
        return False
    return True


def _find_test_files(
    owns: list[str], root: pathlib.Path
) -> set[pathlib.Path]:
    """Map owned source files to test files."""
    tests: set[pathlib.Path] = set()
    for f in owns:
        if not f.startswith("src/"):
            continue
        rel = pathlib.Path(f.replace("src/", "", 1))
        test_path = root / "tests" / ("test_" + rel.name)
        if test_path.is_file():
            tests.add(test_path)
        test_dir = root / "tests" / rel.parent / ("test_" + rel.name.replace(".py", ""))
        if test_dir.is_dir():
            for tf in test_dir.iterdir():
                if tf.suffix == ".py":
                    tests.add(tf)
    return tests


def _test_imports_from(
    test_files: set[pathlib.Path],
    source_files: list[str],
    root: pathlib.Path,
) -> bool:
    """Check if any test file imports from a source file owned by the other unit."""
    src_modules: set[str] = set()
    for sf in source_files:
        mod = _file_to_module(sf)
        if mod:
            src_modules.add(mod)
    for tf in test_files:
        if not tf.is_file():
            continue
        try:
            tree = ast.parse(tf.read_text())
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imp_name = _strip_charon_prefix(alias.name)
                    if imp_name in src_modules or any(
                        imp_name.startswith(m + ".") for m in src_modules
                    ):
                        return True
            elif isinstance(node, ast.ImportFrom):
                if node.module is not None:
                    imp_name = _strip_charon_prefix(node.module)
                    if imp_name in src_modules or any(
                        imp_name.startswith(m + ".") for m in src_modules
                    ):
                        return True
    return False


def _strip_charon_prefix(name: str) -> str:
    if name.startswith("charon."):
        return name[len("charon."):]
    return name


def _conftest_coupling(
    tests_a: set[pathlib.Path],
    tests_b: set[pathlib.Path],
    root: pathlib.Path,
) -> bool:
    """Check if an autouse conftest fixture couples both test sets."""
    all_tests = tests_a | tests_b
    conftest_dirs: set[pathlib.Path] = set()
    for t in all_tests:
        d = t.parent
        while d >= root / "tests":
            if (d / "conftest.py").is_file():
                conftest_dirs.add(d)
            d = d.parent

    for cd in conftest_dirs:
        cf = cd / "conftest.py"
        try:
            tree = ast.parse(cf.read_text())
        except SyntaxError:
            continue
        for node in ast.iter_child_nodes(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            autouse = False
            for dec in node.decorator_list:
                if isinstance(dec, ast.Call):
                    for kw in dec.keywords:
                        if kw.arg == "autouse" and _is_true(kw.value):
                            autouse = True
                            break
            if not autouse:
                continue
            scope = _get_cellist_region(cd)
            if any(t.is_relative_to(scope) or scope in t.parents for t in tests_a) and any(
                t.is_relative_to(scope) or scope in t.parents for t in tests_b
            ):
                return True
    return False


def _is_true(node: ast.expr | None) -> bool:
    if isinstance(node, ast.Constant):
        return bool(node.value)
    return False


def _get_cellist_region(d: pathlib.Path) -> pathlib.Path:
    return d
