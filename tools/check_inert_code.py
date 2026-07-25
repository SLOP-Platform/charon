#!/usr/bin/env python3
# @covers: inert
"""Inert-code gate — dead/unwired code detector, wired into the merge gate.

Adapter around KSF's ``inert_code`` detector (vendored verbatim in
``tools/_vendor/ksf_inert_code.py`` — see that module's docstring and
``tools/_vendor/README.md`` for provenance). KSF's detector builds a stdlib
``ast`` call graph of the target tree, computes reachability from real
entrypoints (``pyproject.toml`` ``[project.scripts]`` + ``__main__`` guards),
and flags any public top-level function/class with ZERO production callers
that isn't otherwise registered or annotated ``@inert_by_design`` — exactly
the "built but never wired in" bug class a hand-rolled audit previously found
(``tool_repair.py``, ``pricing_limits_checker.py``, ``engine/reconcile.py`` +
``board.set_cert()``, and the per-tier ``charon.cache.format_stats`` /
``charon.engine.reconcile.FindingKind`` symbols the gate now tracks as
detector false positives) before this gate existed.

**Instance-inert detection** (added INERT-INSTANCE-DETECT): KSF's detector
treats construction (``ClassName(...)``) as reachability, so a class that is
constructed and stored but whose instance methods are NEVER invoked goes
undetected. This adapter adds a second pass (``find_instance_inert_classes``)
that checks for the "constructed-but-never-invoked" pattern by comparing
every constructed class's method names against all instance-variable method
calls across the production tree. False negatives are tolerated over false
positives: a method-name collision with an unrelated call prevents flagging.

Scope: Charon's product source (``src/charon``). Charon has no KSF
``module.toml`` module registrations, so the detector's "registered module"
escape hatch is deliberately never exercised here (``modules=[]``) — every
symbol must earn reachability from a real entrypoint or an explicit
``@inert_by_design`` decorator.

**Green-without-hiding**: a 0-caller symbol is not automatically a gate
failure. It must be tracked in ``tools/inert-code-disposition.json`` with a
``{reason, disposition}`` entry (``disposition`` one of ``wire``, ``delete``,
``retire``, or ``keep-<why>``). Any 0-caller symbol found that is NOT in the
disposition file fails the gate immediately — so newly introduced dead code
is caught on the same push that introduces it, while already-known dead code
stays tracked with an explicit plan instead of silently accumulating between
audits.

Exit 0 on clean (or fully disposed), 1 on any undisposed dead symbol or a
malformed disposition entry.
"""
from __future__ import annotations

import ast
import json
import re
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_inert_code import (  # noqa: E402
    _gather_source_files,
    _module_dotted_name,
    _parse_file,
    check_inert_code,
)
from tools.gate_contract import emit_work_units  # noqa: E402

DISPOSITION_PATH = REPO_ROOT / "tools" / "inert-code-disposition.json"
_VALID_DISPOSITIONS = re.compile(r"^(wire|delete|retire|keep-.+)$")
_MESSAGE_RE = re.compile(r"^inert-code: (\S+) unreachable")


def _strip_src_prefix(sym: str) -> str:
    """KSF computes dotted module names relative to the repo root, which
    yields an ``src.charon.*`` prefix for this layout. Strip it so tracked
    symbol names read as ``charon.module.Symbol``, matching how the rest of
    the codebase refers to its own modules."""
    return sym[4:] if sym.startswith("src.") else sym


def find_dead_symbols(repo_root: Path = REPO_ROOT) -> list[str]:
    """Run the vendored KSF inert_code detector and return the sorted list of
    dead (0-caller, unregistered) symbols scoped to Charon's product source
    (``src/charon``), with the ``src.`` path prefix stripped for readability.
    """
    # check_inert_code() derives repo_root as db_path.parent.parent (KSF's
    # native shape is <repo_root>/.ksf/<db file>). Charon has no .ksf/
    # directory, so we hand it a synthetic two-levels-deep path purely for
    # that arithmetic — nothing is ever created or read at this path.
    shim_db_path = repo_root / "_ksf_shim" / "state.db"
    result = check_inert_code(db_path=shim_db_path, manifest={}, modules=[])

    dead: set[str] = set()
    for message in result.messages:
        m = _MESSAGE_RE.match(message)
        if not m:
            continue
        sym = _strip_src_prefix(m.group(1))
        if sym.startswith("charon."):
            dead.add(sym)
    return sorted(dead)


def _is_callable_method(item: ast.AST) -> bool:
    """True if *item* is a callable method (not a ``@property``)."""
    if not isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
        return False
    for deco in item.decorator_list:
        if isinstance(deco, ast.Name) and deco.id == "property":
            return False
        if isinstance(deco, ast.Attribute) and deco.attr == "property":
            return False
    return True


def find_instance_inert_classes(repo_root: Path = REPO_ROOT) -> list[str]:
    """Find module-level classes that are constructed but whose instance methods
    are never invoked from any production code (the instance-inert pattern).

    Detection approach:
    1. Parse every production source file and collect all module-level class
       definitions and their callable (non-``@property``) method names.
    2. Find which classes are constructed (``ClassName(...)`` appears as a call
       target in production code), and collect every dotted method call
       ``something.method(...)`` whose receiver is NOT a module-level import
       name (i.e., is plausibly an instance-variable call).
    3. A class is instance-inert iff it IS constructed somewhere in the
       codebase AND none of its public callable method names appear in the set
       of instance-variable method calls.

    This intentionally tolerates false negatives over false positives: if a
    method-name happens to collide with a call on an unrelated class, the
    constructed class appears "invoked" and is not flagged — safer than
    crying wolf.
    """
    prod_files = _gather_source_files(repo_root)

    class_methods: dict[str, set[str]] = {}
    module_imports: dict[str, set[str]] = {}

    for pyfile in prod_files:
        mod_name = _module_dotted_name(repo_root, pyfile)
        tree = _parse_file(pyfile)
        if tree is None:
            continue
        imports: set[str] = set()
        for child in ast.iter_child_nodes(tree):
            if isinstance(child, ast.Import):
                for alias in child.names:
                    imports.add(alias.asname if alias.asname else alias.name)
            elif isinstance(child, ast.ImportFrom):
                for alias in child.names:
                    imports.add(alias.asname if alias.asname else alias.name)
        module_imports[mod_name] = imports
        for node in ast.walk(tree):
            if isinstance(node, ast.ClassDef) and not node.name.startswith("_"):
                full_class = _strip_src_prefix(f"{mod_name}.{node.name}")
                methods: set[str] = set()
                for item in node.body:
                    if _is_callable_method(item) and isinstance(item, (ast.FunctionDef, ast.AsyncFunctionDef)):
                        methods.add(item.name)
                if methods:
                    class_methods[full_class] = methods

    constructed_classes: set[str] = set()
    instance_method_calls: set[str] = set()

    for pyfile in prod_files:
        mod_name = _module_dotted_name(repo_root, pyfile)
        tree = _parse_file(pyfile)
        if tree is None:
            continue
        imports = module_imports.get(mod_name, set())
        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue
            if isinstance(node.func, ast.Name):
                name = node.func.id
                for full_class in class_methods:
                    if full_class.rsplit(".", 1)[-1] == name:
                        constructed_classes.add(full_class)
            elif isinstance(node.func, ast.Attribute):
                receiver = node.func.value
                method_name = node.func.attr
                if isinstance(receiver, ast.Name) and receiver.id not in imports:
                    instance_method_calls.add(method_name)
                elif isinstance(receiver, (ast.Attribute, ast.Subscript)):
                    instance_method_calls.add(method_name)

    instance_inert: list[str] = []
    for full_class in sorted(constructed_classes):
        methods = class_methods.get(full_class, set())
        public_methods = {
            m for m in methods
            if not m.startswith("__") and not m.startswith("_")
        }
        if not public_methods:
            continue
        if not (public_methods & instance_method_calls):
            instance_inert.append(full_class)

    return instance_inert


def load_dispositions() -> dict[str, dict]:
    if not DISPOSITION_PATH.exists():
        return {}
    return json.loads(DISPOSITION_PATH.read_text(encoding="utf-8"))


def validate_dispositions(dispositions: dict[str, dict]) -> list[str]:
    """Return a list of schema-violation messages (empty if all entries are
    well-formed: a non-empty 'reason' string and a 'disposition' matching
    wire|delete|keep-<why>)."""
    issues: list[str] = []
    for sym, entry in dispositions.items():
        if not isinstance(entry, dict):
            issues.append(f"{sym}: entry is not an object")
            continue
        reason = entry.get("reason")
        disposition = entry.get("disposition")
        if not isinstance(reason, str) or not reason.strip():
            issues.append(f"{sym}: missing/empty 'reason'")
        if not isinstance(disposition, str) or not _VALID_DISPOSITIONS.match(disposition):
            issues.append(
                f"{sym}: 'disposition' must be wire|delete|keep-<why>, got {disposition!r}"
            )
    return issues


def check(repo_root: Path = REPO_ROOT) -> tuple[bool, list[str], list[str], list[str]]:
    """Return (passed, undisposed_dead_symbols, all_dead_symbols, schema_issues).

    ``all_dead_symbols`` is the union of KSF-detected dead module-level symbols
    and instance-inert classes (constructed but never invoked).
    """
    dead = find_dead_symbols(repo_root)
    instance_inert = find_instance_inert_classes(repo_root)
    all_dead = sorted(set(dead) | set(instance_inert))
    dispositions = load_dispositions()
    schema_issues = validate_dispositions(dispositions)
    undisposed = [s for s in all_dead if s not in dispositions]
    passed = not undisposed and not schema_issues
    return passed, undisposed, all_dead, schema_issues


def main() -> int:
    passed, undisposed, dead, schema_issues = check()
    dispositions = load_dispositions()
    instance_inert = set(find_instance_inert_classes())
    # Work units = source files walked for public symbols, not dead symbols
    # found. A clean tree legitimately has zero dead symbols; a gate pointed at
    # the wrong tree also has zero. Counting the INPUT distinguishes them.
    emit_work_units(len(sorted((REPO_ROOT / "src").rglob("*.py"))))

    n_inert = sum(1 for s in dead if s in instance_inert)
    print(
        f"inert-code: {len(dead)} dead symbol(s) found "
        f"({n_inert} instance-inert), "
        f"{len(dead) - len(undisposed)} tracked in {DISPOSITION_PATH.name}"
    )
    for sym in dead:
        tag = dispositions.get(sym, {}).get("disposition", "UNDISPOSED")
        suffix = " [instance-inert]" if sym in instance_inert else ""
        print(f"  [{tag}] {sym}{suffix}")

    stale = sorted(set(dispositions) - set(dead))
    # Instance-inert entries in the disposition are not stale — they're
    # tracking classes that are constructed-but-never-invoked, which is a
    # separate classification from KSF-detected dead symbols. Filter them
    # out of the stale warning.
    stale = [s for s in stale if not dispositions.get(s, {}).get("inert_class")]
    if stale:
        print(
            f"  (info) {len(stale)} disposition entr{'y is' if len(stale) == 1 else 'ies are'} "
            f"stale (symbol no longer dead — safe to remove from "
            f"{DISPOSITION_PATH.name}): {stale}",
            file=sys.stderr,
        )

    if schema_issues:
        print(f"\nFAIL: {DISPOSITION_PATH.name} has malformed entries:", file=sys.stderr)
        for issue in schema_issues:
            print(f"  - {issue}", file=sys.stderr)

    if undisposed:
        print(
            f"\nFAIL: {len(undisposed)} dead symbol(s) not present in "
            f"{DISPOSITION_PATH.name} — every 0-caller symbol must be tracked "
            f"with a {{reason, disposition}} entry:",
            file=sys.stderr,
        )
        for sym in undisposed:
            print(f"  - {sym}", file=sys.stderr)

    if not passed:
        return 1

    print("check_inert_code: OK")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
