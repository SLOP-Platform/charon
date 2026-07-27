"""Startup inert-check: classify gateway modules as ACTIVE vs INERT.

At startup, emit an explicit ACTIVE vs INERT inventory of optional components
so that constructed-but-unwired modules are visible rather than silent.

The six INERT_ATTRS modules are constructed at startup (registered in
_MODULE_SPECS) but have ZERO invocation sites on the request path. The
existing tools/check_inert_code.py clears them because they ARE reachable
via the registry, but registry-reachability is NOT the same as being on
the request path — a module that is registered, constructed, and never
called is indistinguishable from a working one until someone audits by hand.

ACTIVE_ATTRS modules ARE on the request path (forwarder.py, proxy_server.py).

## gateway.py wiring snippet (do NOT apply — gateway.py has 4 concurrent owners)
Insert into ``gateway.run()`` after the egress self-test block (after line 800)
and before the Smart Routing status section (before line 806):

    # ── Startup inert check ──────────────────────────────────
    from . import startup_check
    print(startup_check.run_startup_inert_check(cfg), file=sys.stderr)

This prints an inventory line like:
    startup inert check: INERT (6): consensus_router, observability, ...; ACTIVE (6): ...
"""

INERT_ATTRS = frozenset({
    "request_inspector",
    "session_affinity",
    "observability",
    "speculative_executor",
    "consensus_router",
    "virtual_key_manager",
})

ACTIVE_ATTRS = frozenset({
    "spend_limiter",
    "guardrails",
    "semantic_cache",
    "quality_scorer",
    "response_normalizer",
    "policy_router",
})


def classify_modules(modules: dict) -> dict[str, str]:
    """Classify each module attr as ACTIVE or INERT.

    Returns ``{attr: "ACTIVE" | "INERT"}`` for each entry in ``modules``.
    Only opt-in modules (speculative, consensus) that returned None from
    _module_inst are absent — they are correctly not present.
    """
    result = {}
    for attr in modules:
        if attr in INERT_ATTRS:
            result[attr] = "INERT"
        else:
            result[attr] = "ACTIVE"
    return result


def count_inert(modules: dict) -> int:
    """Count modules in ``modules`` that are classified as INERT."""
    return sum(1 for attr in modules if attr in INERT_ATTRS)


def count_active(modules: dict) -> int:
    """Count modules in ``modules`` that are classified as ACTIVE."""
    return sum(1 for attr in modules if attr not in INERT_ATTRS)


def run_startup_inert_check(cfg) -> str:
    """Run the startup inert check, return a diagnostic string.

    Inspects ``cfg.modules``, classifies each module attr, and builds a
    human-readable inventory line. Does NOT raise or exit — this is a
    diagnostic, not a gate. (The gate is the test suite.)
    """
    classification = classify_modules(cfg.modules)
    inert = [a for a, s in classification.items() if s == "INERT"]
    active = [a for a, s in classification.items() if s == "ACTIVE"]
    parts = []
    if inert:
        parts.append(f"INERT ({len(inert)}): {', '.join(sorted(inert))}")
    if active:
        parts.append(f"ACTIVE ({len(active)}): {', '.join(sorted(active))}")
    return "startup inert check: " + "; ".join(parts)
