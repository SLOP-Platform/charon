"""routing_policy package integrity tests + FAIL-ON-REVERT gate.

Wave 1 extracted the routing / provider-selection logic out of ``gateway.py``
into the ``routing_policy`` package. These tests:
- assert ``routing_policy`` IS a package with the required sub-modules
- assert gateway routing DELEGATES to the package
- assert the FAIL-ON-REVERT contract: if the package is collapsed back into
  gateway.py these tests go RED.
"""
from __future__ import annotations

import importlib


def test_routing_policy_is_package():
    """FAIL-ON-REVERT: ``charon.routing_policy`` MUST be a package (directory
    with __init__.py), not a single file — else Wave-2 cannot parallelize."""
    spec = importlib.util.find_spec("charon.routing_policy")
    assert spec is not None, "charon.routing_policy not found"
    assert spec.submodule_search_locations is not None, \
        "routing_policy is NOT a package (it's a single file)"


def test_routing_policy_has_required_submodules():
    """FAIL-ON-REVERT: every required sub-module MUST exist as an importable
    member of the package."""
    required = [
        "charon.routing_policy.base",
        "charon.routing_policy.matrix",
        "charon.routing_policy.cost_rank",
        "charon.routing_policy.drain",
        "charon.routing_policy.pools",
        "charon.routing_policy.spill",
    ]
    for mod_name in required:
        mod = importlib.import_module(mod_name)
        assert mod is not None, f"module {mod_name} not importable"


def test_gateway_delegates_to_routing_policy():
    """FAIL-ON-REVERT: gateway.py's routing logic MUST delegate to the
    routing_policy package — the functions are NOT defined locally."""
    import charon.gateway as gateway_mod
    from charon import routing_policy

    # core routing functions must point to routing_policy (the re-exports)
    assert gateway_mod._build_routes_and_pools is routing_policy.build_routes_and_pools, \
        "gateway._build_routes_and_pools does NOT delegate to routing_policy"
    assert gateway_mod._route_from_spec is routing_policy.route_from_spec, \
        "gateway._route_from_spec does NOT delegate to routing_policy"
    assert gateway_mod._tier_pools is routing_policy.tier_pools, \
        "gateway._tier_pools does NOT delegate to routing_policy"


def test_routing_policy_exports_public_api():
    """The package's __all__ exposes the public surface Wave-2 authors need."""
    from charon import routing_policy

    assert hasattr(routing_policy, "Policy")
    assert hasattr(routing_policy, "DefaultPolicy")
    assert hasattr(routing_policy, "derived_cost_rank")
    assert hasattr(routing_policy, "route_from_spec")
    assert hasattr(routing_policy, "build_routes_and_pools")
    assert hasattr(routing_policy, "tier_pools")
    assert hasattr(routing_policy, "build_fallback_chain")


def test_routing_policy_all_names_importable_and_nonnone():
    """FAIL-ON-REVERT: EVERY name in ``routing_policy.__all__`` MUST be
    importable via ``from charon.routing_policy import <name>`` AND must not be
    ``None``. Goes RED if ``__all__`` again lists a non-exported symbol (the
    exact F1 defect from the adversarial review)."""
    import importlib

    from charon import routing_policy

    assert routing_policy.__all__, "routing_policy.__all__ is empty/missing"
    mod = importlib.import_module("charon.routing_policy")
    for name in routing_policy.__all__:
        # importlib.import_module doesn't do from-import of attributes; use getattr
        # which exercises the same binding a real `from ... import name` would.
        assert hasattr(mod, name), (
            f"{name!r} is in routing_policy.__all__ but NOT importable "
            f"as a package attribute (F1 regression)"
        )
        value = getattr(mod, name)
        assert value is not None, (
            f"{name!r} is in routing_policy.__all__ but binds to None "
            f"(missing re-export — F1 regression)"
        )


def test_derived_cost_rank_moved_to_routing_policy():
    """FAIL-ON-REVERT: ``derived_cost_rank`` MUST live in
    ``routing_policy.cost_rank``, not as a local definition in ``pools.py``.
    The ``charon.pools`` module re-imports it for backward compatibility."""
    from charon.pools import derived_cost_rank as pools_derived
    from charon.routing_policy.cost_rank import derived_cost_rank
    assert derived_cost_rank is pools_derived, \
        "pools.derived_cost_rank does not re-export from routing_policy.cost_rank"


def test_routing_policy_rejects_single_file_import():
    """FAIL-ON-REVERT: if the package is collapsed to a single routing_policy.py
    file, the sub-modules won't be importable — this test goes RED."""
    sub_modules = ("base", "matrix", "cost_rank", "drain", "pools", "spill")
    for name in sub_modules:
        mod = importlib.import_module(f"charon.routing_policy.{name}")
        assert mod.__file__ is not None, f"routing_policy.{name} has no __file__"


def test_gateway_load_config_calls_routing_policy():
    """The ``load_config`` path exercises ``build_routes_and_pools`` and
    ``tier_pools`` through the routing_policy package (integration smoke test)."""
    import pathlib
    import tempfile

    from charon.gateway import load_config

    d = pathlib.Path(tempfile.mkdtemp())
    (d / "models.json").write_text('{"m1": {"upstream_base": "http://x/v1"}}')
    cfg = load_config(state_dir=d)
    assert "m1" in cfg.routes
    assert cfg.routes["m1"].upstream_base == "http://x/v1"
