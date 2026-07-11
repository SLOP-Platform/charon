"""R5 cost-rank-auto — derive cost ordering from live metered cost with
fallback to configured pricing, and wire cost_class priority into sort.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.balance import BalanceTracker
from charon.pools import PoolEntry, PoolConfigError, choose_from_pool, load_pools
from charon.proxy import GatewayProxy
from charon.routing_policy import build_routes_and_pools
from charon.routing_policy.cost_rank import (
    cost_class_priority,
    derived_cost_rank,
)


# ---------------------------------------------------------------------------
# 1) cost_rank derivation: metered overrides configured
# ---------------------------------------------------------------------------

def test_metered_cost_overrides_configured_pricing() -> None:
    """When live metered cost is present, it DIRECTLY sets the rank — cheaper
    metered routes sort before dearer ones even if their configured pricing says
    the opposite."""
    spec = {"cost_input": 0.000010, "cost_output": 0.000010}  # expensive config
    # metered cost is cheap → rank should be low (0.000001 * 1M * 100 = 100)
    assert derived_cost_rank(spec, metered_cost=0.000001) <= 100
    # and cheaper than the configured blend (~2500)
    assert derived_cost_rank(spec, metered_cost=0.000001) < derived_cost_rank(spec)


def test_metered_cost_ranked_cheapest_first_in_pool() -> None:
    """A pool where model A has expensive configured pricing but cheap metered
    cost sorts BEFORE model B with cheap configured but expensive metered."""
    tmp = Path("/tmp/test_r5_meter_override")
    tmp.mkdir(parents=True, exist_ok=True)
    models = {
        "prov-a/m": {
            "agent": "opencode",
            "provider": "prov-a",
            "cost_input": 0.000010, "cost_output": 0.000010,  # dear config
        },
        "prov-b/m": {
            "agent": "opencode",
            "provider": "prov-b",
            "cost_input": 0.000001, "cost_output": 0.000001,  # cheap config
        },
    }
    pools = {"coder": ["prov-a/m", "prov-b/m"]}
    (tmp / "models.json").write_text(json.dumps(models))
    (tmp / "pools.json").write_text(json.dumps(pools))

    # Without metered costs → prov-b (cheap config) sorts first
    plain = load_pools(tmp)
    assert [e.model for e in plain["coder"]] == ["prov-b/m", "prov-a/m"]

    # With metered costs prov-a=cheap, prov-b=dear → prov-a sorts first
    metered = {("prov-a/m", "prov-a"): 0.000001, ("prov-b/m", "prov-b"): 0.000010}
    overridden = load_pools(tmp, metered_costs=metered)
    assert [e.model for e in overridden["coder"]] == ["prov-a/m", "prov-b/m"]


# ---------------------------------------------------------------------------
# 2) fallback to configured pricing when meter is empty
# ---------------------------------------------------------------------------

def test_fallback_to_configured_when_meter_empty() -> None:
    """When metered_cost is None (no traffic yet), derived_cost_rank falls back
    to the configured cost_input / cost_output blend."""
    spec = {"cost_input": 0.000002, "cost_output": 0.000006}
    rank = derived_cost_rank(spec, metered_cost=None)
    expected = round((3 * 0.000002 + 0.000006) / 4 * 1_000_000 * 100)
    assert rank == expected


def test_fallback_used_in_pool_when_no_metered_map() -> None:
    """``load_pools`` with no metered_costs argument derives from configured pricing."""
    tmp = Path("/tmp/test_r5_fallback")
    tmp.mkdir(parents=True, exist_ok=True)
    models = {
        "cheap": {"agent": "opencode", "cost_input": 0.000001, "cost_output": 0.000001},
        "dear": {"agent": "opencode", "cost_input": 0.000010, "cost_output": 0.000010},
    }
    pools = {"coder": ["dear", "cheap"]}
    (tmp / "models.json").write_text(json.dumps(models))
    (tmp / "pools.json").write_text(json.dumps(pools))

    loaded = load_pools(tmp)
    assert [e.model for e in loaded["coder"]] == ["cheap", "dear"]


# ---------------------------------------------------------------------------
# 3) cost_class priority ordering
# ---------------------------------------------------------------------------

def test_cost_class_priority_encoding() -> None:
    """Priority ordering: free-daily < expiring < prepaid < metered < premium."""
    assert cost_class_priority({"cost_class": "free-daily"}) == 0
    assert cost_class_priority({"cost_class": "expiring"}) == 1
    assert cost_class_priority({"cost_class": "prepaid"}) == 2
    assert cost_class_priority({"cost_class": "metered"}) == 3
    assert cost_class_priority({"cost_class": "premium"}) == 4


def test_cost_class_priority_unknown_defaults_to_last() -> None:
    """An unknown cost_class gets the max priority so it sorts last."""
    assert cost_class_priority({"cost_class": "bogus"}) == 4
    assert cost_class_priority({}) == 4


def test_pool_sorts_by_cost_class_priority() -> None:
    """Within the non-free bucket, cheaper funding classes sort first."""
    tmp = Path("/tmp/test_r5_class_priority")
    tmp.mkdir(parents=True, exist_ok=True)
    models = {
        "premium-m": {
            "agent": "opencode",
            "cost_rank": 10,
            "cost_class": "premium",
        },
        "prepaid-m": {
            "agent": "opencode",
            "cost_rank": 50,
            "cost_class": "prepaid",
        },
        "metered-m": {
            "agent": "opencode",
            "cost_rank": 20,
            "cost_class": "metered",
        },
        "expiring-m": {
            "agent": "opencode",
            "cost_rank": 100,
            "cost_class": "expiring",
        },
    }
    pools = {"coder": ["premium-m", "metered-m", "prepaid-m", "expiring-m"]}
    (tmp / "models.json").write_text(json.dumps(models))
    (tmp / "pools.json").write_text(json.dumps(pools))

    loaded = load_pools(tmp)
    order = [e.model for e in loaded["coder"]]
    # Expected: expiring (1) -> prepaid (2) -> metered (3) -> premium (4)
    assert order == ["expiring-m", "prepaid-m", "metered-m", "premium-m"]


def test_build_routes_and_pools_applies_cost_class_priority() -> None:
    """``build_routes_and_pools`` uses the same (free-first, cost_class_priority,
    cost_rank) sort key."""
    registry = {
        "free-m": {"upstream_base": "http://free/v1", "free": True, "cost_rank": 0},
        "prepaid-m": {"upstream_base": "http://pre/v1", "cost_class": "prepaid", "cost_rank": 10},
        "metered-m": {"upstream_base": "http://met/v1", "cost_class": "metered", "cost_rank": 5},
        "premium-m": {"upstream_base": "http://prm/v1", "cost_class": "premium", "cost_rank": 1},
    }
    pool_map = {"coder": ["premium-m", "metered-m", "prepaid-m", "free-m"]}
    _, pools, _ = build_routes_and_pools(registry, pool_map)
    order = [r.upstream_base for r in pools["coder"]]
    # premium gated out, then free first, then prepaid, then metered
    assert order == ["http://free/v1", "http://pre/v1", "http://met/v1"]


# ---------------------------------------------------------------------------
# 4) explicit cost_rank still wins over metered/configured
# ---------------------------------------------------------------------------

def test_explicit_cost_rank_wins_over_metered() -> None:
    """An operator-set cost_rank is the escape hatch — it beats live metered cost."""
    spec = {"cost_rank": 9999, "cost_input": 0.000001, "cost_output": 0.000001}
    assert derived_cost_rank(spec, metered_cost=0.000001) == 9999


# ---------------------------------------------------------------------------
# 5) integration: GatewayProxy metered -> pool sorting
# ---------------------------------------------------------------------------

def test_end_to_end_metered_cost_through_gateway_proxy() -> None:
    """GatewayProxy accumulates per-(model,provider) costs; load_pools reads them
    to reorder routes cheapest-first.  Costs here are synthetic marginal rates
    (per-request average) so they share the same scale as configured per-token
    pricing for a meaningful sort comparison."""
    p = GatewayProxy()
    # Two observations: prov-a cheap ($0.00001 per request), prov-b dear ($0.00050)
    p.observe(
        "m", 200,
        body={"model": "m",
              "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00001}},
        provider="prov-a",
    )
    p.observe(
        "m", 200,
        body={"model": "m",
              "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.00050}},
        provider="prov-b",
    )

    metered = p.all_model_provider_costs()
    assert metered[("m", "prov-a")] == 0.00001
    assert metered[("m", "prov-b")] == 0.00050

    # build_routes_and_pools with provider set so meter key matches
    registry = {
        "m": {"provider": "prov-a", "cost_input": 0.0001, "cost_output": 0.0001},
        "m-b": {"provider": "prov-b", "cost_input": 0.0001, "cost_output": 0.0001},
    }
    pool_map = {"coder": ["m-b", "m"]}
    providers_cfg = {
        "prov-a": {"base_url": "http://a/v1"},
        "prov-b": {"base_url": "http://b/v1"},
    }
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg, metered_costs=metered)
    order = [r.provider for r in pools["coder"]]
    assert order == ["prov-a", "prov-b"]


# ---------------------------------------------------------------------------
# 6) BalanceTracker model_spend wired similarly
# ---------------------------------------------------------------------------

def test_balance_tracker_spend_used_for_rank() -> None:
    """BalanceTracker.model_spend returns the same kind of per-model burn figure
    that can be fed into derived_cost_rank."""
    bt = BalanceTracker()
    bt.record_spend("deepseek", 0.03, model="v")
    assert bt.model_spend("v", "deepseek") == 0.03
    rank = derived_cost_rank({}, metered_cost=bt.model_spend("v", "deepseek"))
    assert rank == max(0, round(0.03 * 1_000_000 * 100))
