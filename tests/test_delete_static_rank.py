"""DELETE-STATIC-RANK (ADR-0016 step #6) — FAIL-ON-REVERT tests.

The hand-typed ``cost_rank`` integer is REMOVED as a config INPUT.  Ordering
is ALWAYS derived from live/sourced/meter price — a magnitude a hand-typed
scalar could never be trusted to keep in sync with the meter.  ``cost_class``
(an operator-set CATEGORY axis) is RETAINED: it is the ADR's honest floor for
funding-class ordering, not a decaying magnitude.

These tests are the deliverable per the ticket's `accept:` block.  They MUST:

(1) prove a config that sets ``cost_rank: N`` no longer produces a PoolEntry
    whose order depends on N — ordering is identical to the same config WITHOUT
    cost_rank (derived from price only), AND the validator emits the deprecation
    warning.

(2) prove ``cost_class`` STILL orders pools by funding class (a prepaid provider
    still sorts ahead of a metered one) — the CATEGORY axis is intact.

Revert the deletion (re-honor explicit ``cost_rank``) → assertion (1) RED.
Accidentally drop ``cost_class`` → assertion (2) RED.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon import config as _config
from charon.gateway import load_config
from charon.pools import load_pools
from charon.routing_policy import build_routes_and_pools
from charon.routing_policy.cost_rank import derived_cost_rank

# ─────────────────────────────────────────────────────────────────────────────
# (1) hand-typed cost_rank is IGNORED for ordering
# ─────────────────────────────────────────────────────────────────────────────


def test_explicit_cost_rank_is_ignored_for_derived_rank():
    """FAIL-ON-REVERT (1a): a hand-typed ``cost_rank`` in the spec dict MUST NOT
    influence the derived rank.  Same input with and without the override yields
    the same ``derived_cost_rank`` value."""
    with_pricing = {"cost_input": 0.000001, "cost_output": 0.000003,
                    "cost_rank": 1}                       # would have been rank=1 pre-delete
    without_pricing = {"cost_input": 0.000001, "cost_output": 0.000003}
    assert derived_cost_rank(with_pricing) == derived_cost_rank(without_pricing), (
        "hand-typed cost_rank leaked into the derived rank — DELETE-STATIC-RANK "
        "is reverted; ADR-0016 step #6 contract broken"
    )


def test_explicit_cost_rank_does_not_change_pool_order(tmp_path: Path, monkeypatch):
    """FAIL-ON-REVERT (1b): a config that sets ``cost_rank: 9999`` on the
    *naturally* cheaper model must NOT force it to sort last.  Two configs
    differ ONLY in the operator's hand-typed integer; their pool order is
    identical.  A deprecation warning is emitted on the override input."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # Config A: operator hands the cheap model rank 9999 (would have forced last)
    _config.add_model("cheap", upstream_base="http://cheap/v1",
                      cost_input=0.0000005, cost_output=0.0000015,
                      cost_rank=9999)
    _config.add_model("dear", upstream_base="http://dear/v1",
                      cost_input=0.000005, cost_output=0.000015)
    _config.set_pool("auto", ["cheap", "dear"])
    cfg_a = load_config(state_dir=tmp_path)
    order_a = [r.upstream_base for r in cfg_a.pools["auto"]]

    # Reset and build the same shape WITHOUT the hand-typed override
    (tmp_path / "models.json").unlink()
    (tmp_path / "pools.json").unlink()

    _config.add_model("cheap", upstream_base="http://cheap/v1",
                      cost_input=0.0000005, cost_output=0.0000015)
    _config.add_model("dear", upstream_base="http://dear/v1",
                      cost_input=0.000005, cost_output=0.000015)
    _config.set_pool("auto", ["cheap", "dear"])
    cfg_b = load_config(state_dir=tmp_path)
    order_b = [r.upstream_base for r in cfg_b.pools["auto"]]

    assert order_a == order_b, (
        f"pool order diverges when a hand-typed cost_rank is set: "
        f"with-override={order_a} vs without-override={order_b} "
        f"— DELETE-STATIC-RANK is reverted; ADR-0016 step #6 contract broken"
    )
    # And in both, the natural cheap/dear ordering is preserved (cheap first)
    assert order_a == ["http://cheap/v1", "http://dear/v1"]


def test_derived_cost_rank_emits_deprecation_warning_on_explicit_override():
    """FAIL-ON-REVERT (1c): an external config that still stamps ``cost_rank``
    MUST trigger a ``DeprecationWarning`` from the validator.  This is the
    one-release migration signal operators see while the .60 deploy purges
    the field from ``models.json`` (ADR-0016 Consequences)."""
    spec = {"cost_input": 0.000001, "cost_output": 0.000003, "cost_rank": 42}
    with pytest.warns(DeprecationWarning, match=r"cost_rank=42.*ADR-0016"):
        derived_cost_rank(spec)


def test_add_model_emits_deprecation_warning_on_explicit_cost_rank(tmp_path, monkeypatch):
    """FAIL-ON-REVERT (1d): the config-layer ``add_model`` validator emits the
    deprecation warning when an external caller still passes a hand-typed
    ``cost_rank``.  The field is silently DROPPED (not persisted to models.json)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.warns(DeprecationWarning, match=r"cost_rank=77.*ADR-0016"):
        _config.add_model("m", upstream_base="http://x/v1", cost_rank=77)
    persisted = _config.load_models()
    assert "cost_rank" not in persisted["m"], (
        f"cost_rank leaked into models.json: {persisted['m']!r} — "
        f"DELETE-STATIC-RANK is reverted; ADR-0016 step #6 contract broken"
    )


def test_add_models_bulk_drops_explicit_cost_rank_with_warning(tmp_path, monkeypatch):
    """FAIL-ON-REVERT (1e): the bulk-import path (``charon models import``)
    also drops ``cost_rank`` with a deprecation warning.  This is the
    discoverability path — if a hand-typed rank sneaks in via the import
    feed, it must NOT influence ordering."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    entries = [
        {"id": "m1", "free": False, "cost_input": 0.000001, "cost_output": 0.000003,
         "cost_rank": 1},
        {"id": "m2", "free": False, "cost_input": 0.00001, "cost_output": 0.00003,
         "cost_rank": 9999},
    ]
    with pytest.warns(DeprecationWarning, match=r"cost_rank=1.*ADR-0016"):
        added, _ = _config.add_models_bulk(entries, provider="openrouter")
    assert sorted(added) == ["m1", "m2"]
    persisted = _config.load_models()
    assert "cost_rank" not in persisted["m1"]
    assert "cost_rank" not in persisted["m2"]


def test_hand_typed_rank_does_not_force_dear_first_when_cheap_by_price():
    """FAIL-ON-REVERT (1f): the EXACT scenario the ticket calls out — operator
    force-ranks the naturally cheap model as 9999; the deletion means it
    still sorts cheap-first because the rank is derived, not read."""
    registry = {
        "force-dear": {"upstream_base": "http://a/v1",
                       "cost_input": 0.0000001, "cost_output": 0.0000001,
                       "cost_rank": 9999},               # ignored
        "natural":    {"upstream_base": "http://b/v1",
                       "cost_input": 0.000002, "cost_output": 0.000002},
    }
    pool_map = {"auto": ["force-dear", "natural"]}
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg={})
    assert [r.upstream_base for r in pools["auto"]] == ["http://a/v1", "http://b/v1"], (
        "force-dear is cheaper by price and must sort first; the hand-typed "
        "rank=9999 must NOT influence ordering"
    )


# ─────────────────────────────────────────────────────────────────────────────
# (2) cost_class is RETAINED — the funding-class CATEGORY axis is intact
# ─────────────────────────────────────────────────────────────────────────────


def test_cost_class_prepaid_still_orders_ahead_of_metered():
    """FAIL-ON-REVERT (2a): a prepaid provider (cost_class=prepaid) STILL sorts
    ahead of a metered provider (cost_class=metered) at equal pricing — the
    CATEGORY axis is the ADR's honest floor and must be intact after the
    magnitude (``cost_rank``) is removed."""
    registry = {
        "metered-cheap": {"upstream_base": "http://met/v1",
                          "cost_input": 0.000001, "cost_output": 0.000003,
                          "cost_class": "metered"},
        "prepaid-dear":   {"upstream_base": "http://pre/v1",
                           "cost_input": 0.000001, "cost_output": 0.000003,
                           "cost_class": "prepaid"},
    }
    pool_map = {"auto": ["metered-cheap", "prepaid-dear"]}
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg={})
    chain = pools["auto"]
    assert [r.upstream_base for r in chain] == ["http://pre/v1", "http://met/v1"], (
        "prepaid must sort ahead of metered at equal pricing — "
        "cost_class (the CATEGORY axis) is broken; DELETE-STATIC-RANK "
        "accidentally removed it"
    )


def test_cost_class_still_orders_via_load_pools(tmp_path: Path):
    """FAIL-ON-REVERT (2b): the same CATEGORY ordering holds via the pools
    loader path (``pools.load_pools``) that the ACP router and the legacy
    pools.json path read from — the CATEGORY axis is not just a gateway
    compiler artifact, it is the data structure's sort key."""
    (tmp_path / "models.json").write_text(json.dumps({
        "metered": {"agent": "opencode", "upstream_base": "http://met/v1",
                    "cost_input": 0.000001, "cost_output": 0.000003,
                    "cost_class": "metered", "free": False},
        "prepaid": {"agent": "opencode", "upstream_base": "http://pre/v1",
                    "cost_input": 0.000001, "cost_output": 0.000003,
                    "cost_class": "prepaid", "free": False},
    }))
    (tmp_path / "pools.json").write_text(json.dumps({
        "auto": ["metered", "prepaid"],
    }))
    pools = load_pools(tmp_path)
    chain = pools["auto"]
    assert [e.upstream_base for e in chain] == ["http://pre/v1", "http://met/v1"], (
        "pools.load_pools no longer orders by cost_class — "
        "CATEGORY axis is broken at the data layer"
    )


def test_free_first_sort_key_still_works_without_cost_rank():
    """FAIL-ON-REVERT (2c): the free-first half of the sort key
    ``(not free, cost_class_priority, cost_rank)`` is intact when no model
    has a hand-typed cost_rank — the free model sorts first regardless of
    its (now-ignored) cost metadata, because cost_class_priority for the
    default class still sorts it ahead of metered."""
    registry = {
        "free":   {"upstream_base": "http://free/v1", "free": True,
                   "cost_input": 0.1, "cost_output": 0.1,
                   "cost_class": "metered"},   # even with metered class, free wins
        "metered": {"upstream_base": "http://met/v1", "free": False,
                    "cost_input": 0.000001, "cost_output": 0.000003,
                    "cost_class": "metered"},
    }
    pool_map = {"auto": ["metered", "free"]}   # listed metered-first
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg={})
    assert [r.upstream_base for r in pools["auto"]] == ["http://free/v1", "http://met/v1"]


# ─────────────────────────────────────────────────────────────────────────────
# Negative-assertion guard: a hand-typed cost_rank is NEVER persisted
# ─────────────────────────────────────────────────────────────────────────────


def test_models_json_never_contains_cost_rank_after_add_model(tmp_path, monkeypatch):
    """FAIL-ON-REVERT (negative): the on-disk ``models.json`` MUST NOT contain
    a ``cost_rank`` key after ``add_model`` is called with the kwarg.  The
    validator drops the field; a regression that re-persists it goes RED."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore", DeprecationWarning)
        _config.add_model("m", upstream_base="http://x/v1", cost_rank=12)
    raw = json.loads((tmp_path / "models.json").read_text())
    assert "cost_rank" not in raw["m"], (
        f"models.json still has a cost_rank key: {raw['m']!r} — "
        f"DELETE-STATIC-RANK is reverted; ADR-0016 step #6 contract broken"
    )
