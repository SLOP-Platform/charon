"""Startup inert-check: classify gateway modules as ACTIVE vs INERT.

At startup, emit an explicit ACTIVE vs INERT inventory of optional components
so that constructed-but-unwired modules are visible rather than silent.

The classification is DERIVED (not asserted) from the invocation surface:
  - ``forwarder.py``: the data-plane request path. Every ``srv.<attr>`` access
    (and ``getattr(srv, "literal", ...)``) is statically collected.
  - ``chain_for`` in ``proxy_server.py``: called from the request path. Every
    ``self.<attr>`` access in that method is collected.
  - ``proxy_server.py.__init__._mod_param_names``: the set of module attribute
    names constructed and assigned on the server.

A module attr is ACTIVE if it appears on the invocation surface.
A module attr is INERT if it is constructed/registered but never invoked.
A genuinely unknown attr is INERT when it never appears on the invocation
surface; UNKNOWN (fail-closed RED) when it DOES appear on the invocation
surface but is not in the known module set (stale analysis).

The six known-dead modules (request_inspector, session_affinity, observability,
speculative_executor, consensus_router, virtual_key_manager) are a TEST
FIXTURE — the derivation reproduces them independently and they never appear
as a hardcoded list in this implementation.

## gateway.py wiring snippet (do NOT apply — gateway.py has 4 concurrent owners)
Insert into ``gateway.run()`` after the egress self-test block (after line 800)
and before the Smart Routing status section (before line 806):

    # ── Startup inert check ──────────────────────────────────
    from . import startup_check
    print(startup_check.run_startup_inert_check(cfg), file=sys.stderr)

This prints an inventory line like:
    startup inert check: INERT (6): consensus_router, observability, ...; ACTIVE (6): ...
"""

from __future__ import annotations

import ast
import os

_SRC_DIR = os.path.dirname(os.path.abspath(__file__))
_FORWARDER_PATH = os.path.join(_SRC_DIR, "forwarder.py")
_PROXY_SERVER_PATH = os.path.join(_SRC_DIR, "proxy_server.py")


def _parse_module_attr_names() -> frozenset[str]:
    """Derive the set of module attribute names from proxy_server.py.__init__.

    Collects string literals from the ``_mod_param_names`` tuple — the
    authoritative list of Smart-Routing module names that are assigned as
    ``self.<name> = self.modules.get("<name>")``. This list is the INPUT to
    the classification (the full module inventory), NOT the classification
    result.
    """
    try:
        with open(_PROXY_SERVER_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return frozenset()
    for node in ast.walk(tree):
        if not isinstance(node, (ast.Assign, ast.AnnAssign)):
            continue
        targets = node.targets if hasattr(node, "targets") else (
            [node.target] if getattr(node, "target", None) else [])
        if len(targets) != 1 or not isinstance(targets[0], ast.Name):
            continue
        if targets[0].id != "_mod_param_names":
            continue
        value = node.value
        if not isinstance(value, (ast.Tuple, ast.List)):
            continue
        names: list[str] = []
        for elt in value.elts:
            if isinstance(elt, ast.Constant) and isinstance(elt.value, str):
                names.append(elt.value)
            elif hasattr(ast, "Str") and isinstance(elt, ast.Str) and isinstance(elt.s, str):
                names.append(elt.s)
        return frozenset(names)
    return frozenset()


def _parse_all_srv_attrs_forwarder() -> frozenset[str]:
    """Collect every ``srv.<attr>`` access and ``getattr(srv, "literal", ...)``
    call in forwarder.py. This is the full invocation surface — later
    intersected with the known module set to produce the ACTIVE list."""
    try:
        with open(_FORWARDER_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return frozenset()

    attrs: set[str] = set()

    class V(ast.NodeVisitor):
        def visit_Attribute(self, node):
            if isinstance(node.value, ast.Name) and node.value.id == "srv":
                attrs.add(node.attr)
            self.generic_visit(node)

        def visit_Call(self, node):
            if (isinstance(node.func, ast.Name) and node.func.id == "getattr"
                    and len(node.args) >= 2
                    and isinstance(node.args[0], ast.Name)
                    and node.args[0].id == "srv"):
                arg1 = node.args[1]
                if isinstance(arg1, ast.Constant) and isinstance(arg1.value, str):
                    attrs.add(arg1.value)
                elif hasattr(ast, "Str") and isinstance(arg1, ast.Str):
                    attrs.add(arg1.s)
            self.generic_visit(node)

    V().visit(tree)
    return frozenset(attrs)


def _collect_self_attrs(func_node: ast.FunctionDef) -> frozenset[str]:
    """Collect every ``self.<attr>`` access within a function body node."""
    attrs: set[str] = set()

    class V(ast.NodeVisitor):
        def visit_Attribute(self, inner):
            if isinstance(inner.value, ast.Name) and inner.value.id == "self":
                attrs.add(inner.attr)
            self.generic_visit(inner)

    V().visit(func_node)
    return frozenset(attrs)


def _parse_chain_for_attrs() -> frozenset[str]:
    """Collect every ``self.<attr>`` access in the ``chain_for`` method.
    ``chain_for`` is called directly from ``forward_with_failover`` and is
    part of the request path."""
    try:
        with open(_PROXY_SERVER_PATH, encoding="utf-8") as f:
            tree = ast.parse(f.read())
    except (OSError, SyntaxError):
        return frozenset()

    for node in ast.walk(tree):
        if isinstance(node, ast.FunctionDef) and node.name == "chain_for":
            return _collect_self_attrs(node)
    return frozenset()


_MODULE_ATTRS = _parse_module_attr_names()

_ALL_SRV_ATTRS = _parse_all_srv_attrs_forwarder() | _parse_chain_for_attrs()

_INVOKED_ATTRS = _ALL_SRV_ATTRS & _MODULE_ATTRS


def classify_modules(modules: dict, *,
                     invoked: frozenset[str] | None = None,
                     module_attrs: frozenset[str] | None = None,
                     all_srv_attrs: frozenset[str] | None = None) -> dict[str, str]:
    """Classify each module attr as ACTIVE, INERT, or UNKNOWN.

    Returns ``{attr: "ACTIVE" | "INERT" | "UNKNOWN"}`` for each entry in
    ``modules``. Parameters are injectable for testing (red-proofs).

    ACTIVE   — the attr is constructed AND appears on the invocation surface.
    INERT    — the attr is constructed but never invoked; or is genuinely
               unknown and never appears on the invocation surface.
    UNKNOWN  — the attr appears on the invocation surface but is NOT in the
               known module set. This means the static analysis is stale and
               must be updated — the gate treats UNKNOWN as RED (fail-closed).
    """
    if module_attrs is None:
        module_attrs = _MODULE_ATTRS
    if all_srv_attrs is None:
        all_srv_attrs = _ALL_SRV_ATTRS
    if invoked is None:
        invoked = all_srv_attrs & module_attrs

    result: dict[str, str] = {}
    for attr in modules:
        if attr in invoked:
            result[attr] = "ACTIVE"
        elif attr in module_attrs:
            result[attr] = "INERT"
        elif attr in all_srv_attrs:
            result[attr] = "UNKNOWN"
        else:
            result[attr] = "INERT"
    return result


def count_inert(modules: dict, *, invoked: frozenset[str] | None = None,
                module_attrs: frozenset[str] | None = None,
                all_srv_attrs: frozenset[str] | None = None) -> int:
    """Count modules classified as INERT."""
    return sum(1 for s in classify_modules(
        modules,
        invoked=invoked,
        module_attrs=module_attrs,
        all_srv_attrs=all_srv_attrs,
    ).values() if s == "INERT")


def count_active(modules: dict, *, invoked: frozenset[str] | None = None,
                 module_attrs: frozenset[str] | None = None,
                 all_srv_attrs: frozenset[str] | None = None) -> int:
    """Count modules classified as ACTIVE."""
    return sum(1 for s in classify_modules(
        modules,
        invoked=invoked,
        module_attrs=module_attrs,
        all_srv_attrs=all_srv_attrs,
    ).values() if s == "ACTIVE")


def run_startup_inert_check(cfg) -> str:
    """Run the startup inert check, return a diagnostic string.

    Inspects ``cfg.modules``, classifies each module attr, and builds a
    human-readable inventory line. Does NOT raise or exit — this is a
    diagnostic, not a gate. (The gate is the test suite.)
    """
    classification = classify_modules(cfg.modules)
    inert = [a for a, s in classification.items() if s == "INERT"]
    active = [a for a, s in classification.items() if s == "ACTIVE"]
    unknown = [a for a, s in classification.items() if s == "UNKNOWN"]
    parts: list[str] = []
    if inert:
        parts.append(f"INERT ({len(inert)}): {', '.join(sorted(inert))}")
    if active:
        parts.append(f"ACTIVE ({len(active)}): {', '.join(sorted(active))}")
    if unknown:
        parts.append(f"UNKNOWN ({len(unknown)}): {', '.join(sorted(unknown))}")
    return "startup inert check: " + "; ".join(parts)
