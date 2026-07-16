"""PRICED-COMPLETENESS preflight guard (ADR0016-DEPLOY-PRICED-COMPLETENESS).

Adversarial-review finding (adversarial-delete-static-rank.md): DELETE-STATIC-RANK
(ADR-0016 step #6) removed the operator's hand-typed ``cost_rank`` escape hatch.
A model lacking ``cost_input`` / ``cost_output`` silently collapses to the fixed
``1000`` fallback (cost_rank.py:88-89, pools.py:136), tie-broken by config-insert
order → can route to a PRICIER provider.  The operator override that could correct
a bad derived order was removed (routing_policy/__init__.py), and nothing
guaranteed priced-completeness.

This guard closes that gap: ``assert_priced_completeness`` raises LOUD before the
``cost_rank`` purge goes live, naming every offender.

Acceptance criteria (ticket accept: block):
  - A model missing pricing -> guard FAILS (fail-on-revert)
  - Fully-priced catalog -> passes
  - Prove a missing-price model does NOT get selected over a cheaper priced one

These tests MUST go RED if:
  - An unpriced model does NOT trigger PricedCompletenessError (guard reverted)
  - A fully-priced catalog DOES trigger PricedCompletenessError (false positive)
  - A missing-price model gets selected over a cheaper priced one (selection
    path bypasses the rank ordering, or the guard is removed and the 1000
    fallback lets the unpriced model win)
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.pools import choose_from_pool, load_pools
from charon.routing_policy import build_routes_and_pools
from charon.routing_policy.cost_rank import (
    PricedCompletenessError,
    _is_unpriced,
    assert_priced_completeness,
    derived_cost_rank,
    find_unpriced_models,
)

# ─────────────────────────────────────────────────────────────────────────────
# Section 1 — Unit: _is_unpriced / find_unpriced_models
# ─────────────────────────────────────────────────────────────────────────────


def test_is_unpriced_identifies_missing_pricing() -> None:
    """A spec with no cost_input, no cost_output, not free, not disabled is
    unpriced."""
    assert _is_unpriced({}) is True


def test_is_unpriced_exempts_disabled_model() -> None:
    """FAIL-ON-REVERT: a model with enabled: false is NOT unpriced — operators
    explicitly staged it out of the routing table."""
    assert _is_unpriced({"enabled": False}) is False
    assert _is_unpriced({"enabled": False, "cost_input": None}) is False


def test_is_unpriced_exempts_free_model() -> None:
    """FAIL-ON-REVERT: a model with free: true is NOT unpriced — the router
    sorts it first regardless of cost."""
    assert _is_unpriced({"free": True}) is False
    assert _is_unpriced({"free": True, "cost_input": None}) is False


def test_is_unpriced_passes_when_priced() -> None:
    """A model with cost_input + cost_output is NOT unpriced."""
    assert _is_unpriced({"cost_input": 0.000001, "cost_output": 0.000003}) is False


def test_is_unpriced_passes_with_only_cost_input() -> None:
    """A model with only cost_input is NOT unpriced — the missing cost_output
    side is priced from zero."""
    assert _is_unpriced({"cost_input": 0.000001}) is False


def test_is_unpriced_passes_with_only_cost_output() -> None:
    """A model with only cost_output is NOT unpriced — the missing cost_input
    side is priced from zero."""
    assert _is_unpriced({"cost_output": 0.000003}) is False


def test_is_unpriced_rejects_non_dict() -> None:
    """A non-dict spec is not unpriced (defensive — can't introspect it)."""
    assert _is_unpriced("not-a-dict") is False  # type: ignore[arg-type]
    assert _is_unpriced(None) is False  # type: ignore[arg-type]


def test_find_unpriced_models_returns_empty_when_all_priced() -> None:
    """A registry where every entry has cost_input + cost_output returns []."""
    registry = {
        "model-a": {"cost_input": 0.000001, "cost_output": 0.000003},
        "model-b": {"cost_input": 0.000002, "cost_output": 0.000006},
    }
    assert find_unpriced_models(registry) == []


def test_find_unpriced_models_identifies_missing_pricing() -> None:
    """A model without cost_input or cost_output is identified as unpriced."""
    registry = {
        "priced": {"cost_input": 0.000001, "cost_output": 0.000003},
        "unpriced": {},
    }
    assert find_unpriced_models(registry) == ["unpriced"]


def test_find_unpriced_models_exempts_disabled_model() -> None:
    """FAIL-ON-REVERT: a disabled model is NOT unpriced."""
    registry = {"disabled": {"enabled": False}}
    assert find_unpriced_models(registry) == []


def test_find_unpriced_models_exempts_free_model() -> None:
    """FAIL-ON-REVERT: a free model is NOT unpriced."""
    registry = {"freebie": {"free": True}}
    assert find_unpriced_models(registry) == []


def test_find_unpriced_models_mixed() -> None:
    """A registry with a mix of priced, unpriced, disabled, and free models
    correctly identifies only the enabled, non-free, unpriced ones."""
    registry = {
        "priced": {"cost_input": 0.000001, "cost_output": 0.000003},
        "unpriced": {},
        "disabled": {"enabled": False},
        "freebie": {"free": True, "cost_input": 0.01},
        "free-bare": {"free": True},
    }
    assert find_unpriced_models(registry) == ["unpriced"]


def test_find_unpriced_models_empty_registry() -> None:
    """An empty registry returns an empty list."""
    assert find_unpriced_models({}) == []
    assert find_unpriced_models(None) == []  # type: ignore[arg-type]
    assert find_unpriced_models([]) == []  # type: ignore[arg-type]


def test_find_unpriced_models_preserves_registry_order() -> None:
    """The returned list preserves the registry's iteration order so the error
    message is reproducible across runs."""
    registry: dict[str, dict] = {
        "zeta": {},
        "alpha": {},
        "mid": {},
    }
    assert find_unpriced_models(registry) == ["zeta", "alpha", "mid"]


# ─────────────────────────────────────────────────────────────────────────────
# Section 2 — Unit: assert_priced_completeness (the preflight guard)
# ─────────────────────────────────────────────────────────────────────────────


def test_assert_priced_completeness_raises_on_unpriced() -> None:
    """FAIL-ON-REVERT: an enabled, non-free model missing both cost_input and
    cost_output MUST cause assert_priced_completeness to raise."""
    registry: dict[str, dict] = {"bad": {}}
    with pytest.raises(PricedCompletenessError) as exc:
        assert_priced_completeness(registry)
    assert "bad" in str(exc.value)
    assert "PRICED-COMPLETENESS preflight FAILED" in str(exc.value)


def test_assert_priced_completeness_names_multiple_offenders() -> None:
    """The error message lists ALL unpriced model ids (sorted for stability)."""
    registry: dict[str, dict] = {
        "m1": {},
        "m2": {},
    }
    with pytest.raises(PricedCompletenessError) as exc:
        assert_priced_completeness(registry)
    msg = str(exc.value)
    assert "m1" in msg
    assert "m2" in msg
    assert "2 live model(s)" in msg


def test_assert_priced_completeness_passes_when_all_priced() -> None:
    """FAIL-ON-REVERT: a fully-priced catalog MUST pass without raising."""
    registry = {
        "m1": {"cost_input": 0.000001, "cost_output": 0.000003},
        "m2": {"cost_input": 0.000002, "cost_output": 0.000006},
    }
    assert_priced_completeness(registry)  # no raise


def test_assert_priced_completeness_passes_disabled() -> None:
    """A disabled model does NOT trigger the guard."""
    registry = {"offline": {"enabled": False}}
    assert_priced_completeness(registry)  # no raise


def test_assert_priced_completeness_passes_free() -> None:
    """A free model does NOT trigger the guard."""
    registry = {"freebie": {"free": True}}
    assert_priced_completeness(registry)  # no raise


def test_assert_priced_completeness_empty_registry() -> None:
    """An empty registry passes."""
    assert_priced_completeness({})


def test_assert_priced_completeness_message_names_remediation() -> None:
    """The error message includes the three deploy-safe remediations so the
    operator knows exactly how to fix the catalog."""
    with pytest.raises(PricedCompletenessError) as exc:
        assert_priced_completeness({"bad": {}})
    msg = str(exc.value)
    assert "cost_input" in msg
    assert "cost_output" in msg
    assert "free: true" in msg
    assert "enabled: false" in msg


# ─────────────────────────────────────────────────────────────────────────────
# Section 3 — Selection safety: a missing-price model does NOT get selected
#             over a cheaper priced one
#
# This is the core acceptance criterion.  We prove it three ways:
#   (a) Unit: derived_cost_rank gives unpriced=1000, cheap priced < 1000
#   (b) Integration via build_routes_and_pools (gateway path)
#   (c) Integration via load_pools + choose_from_pool (ACP/data path)
# ─────────────────────────────────────────────────────────────────────────────


def test_unpriced_rank_is_neutral_1000() -> None:
    """An unpriced model gets the fixed 1000 fallback rank.  This is the
    degenerate case the guard prevents — a neutral MIDDLE rank, not a
    'sort-last' sentinel."""
    assert derived_cost_rank({}) == 1000


def test_cheap_priced_rank_is_below_1000() -> None:
    """A cheap priced model's derived rank is BELOW 1000, so it sorts BEFORE
    any unpriced model.  This is the selection-safety invariant: the cheaper
    priced model always wins pool[0]."""
    cheap_rank = derived_cost_rank({"cost_input": 0.000001, "cost_output": 0.000003})
    assert cheap_rank < 1000, (
        f"cheap priced model rank={cheap_rank} must be < 1000 (the unpriced "
        f"fallback) — if not, an unpriced model could tie/win and get selected "
        f"over the cheaper priced one"
    )


def test_selection_safety_via_build_routes_and_pools() -> None:
    """FAIL-ON-REVERT (acceptance criterion): prove a missing-price model does
    NOT get selected over a cheaper priced one via the gateway path.

    ``build_routes_and_pools`` sorts each pool by
    (not free, cost_class_priority, derived_cost_rank).  An unpriced model
    gets rank 1000; a cheap priced model gets rank < 1000.  So the cheaper
    priced model sorts first → becomes pool[0] → gets selected.  The unpriced
    model is NOT selected over it.

    Listed order is reversed (unpriced first) to prove the sort overcomes
    insertion-order bias."""
    registry = {
        "cheap-priced": {
            "upstream_base": "http://cheap/v1",
            "cost_input": 0.000001,
            "cost_output": 0.000003,
        },
        "unpriced": {
            "upstream_base": "http://unpriced/v1",
        },
    }
    pool_map = {"auto": ["unpriced", "cheap-priced"]}  # unpriced listed first
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg={})
    order = [r.upstream_base for r in pools["auto"]]
    assert order == ["http://cheap/v1", "http://unpriced/v1"], (
        f"cheaper priced model must sort first (pool[0]=selected), got {order} "
        f"— if the unpriced model sorts first, it gets selected over the "
        f"cheaper priced one (MONEY EXPOSURE: the unpriced model's upstream "
        f"may be PRICIER)"
    )


def test_selection_safety_via_load_pools_and_choose_from_pool(tmp_path: Path) -> None:
    """FAIL-ON-REVERT (acceptance criterion): prove a missing-price model does
    NOT get selected over a cheaper priced one via the ACP/data path.

    ``load_pools`` sorts each pool by (not free, cost_class_priority, cost_rank),
    then ``choose_from_pool`` returns the first non-excluded entry (pool[0]).
    An unpriced model gets rank 1000; a cheap priced model gets rank < 1000.
    So the cheaper priced model sorts first → gets selected.  The unpriced
    model is NOT selected over it."""
    (tmp_path / "models.json").write_text(json.dumps({
        "cheap-priced": {
            "agent": "opencode",
            "upstream_base": "http://cheap/v1",
            "cost_input": 0.000001,
            "cost_output": 0.000003,
            "free": False,
        },
        "unpriced": {
            "agent": "opencode",
            "upstream_base": "http://unpriced/v1",
            "free": False,
        },
    }))
    (tmp_path / "pools.json").write_text(json.dumps({
        "auto": ["unpriced", "cheap-priced"],  # unpriced listed first
    }))
    pools = load_pools(tmp_path)
    order = [e.model for e in pools["auto"]]
    assert order == ["cheap-priced", "unpriced"], (
        f"cheaper priced model must sort first, got {order} — if the unpriced "
        f"model sorts first, choose_from_pool selects it over the cheaper "
        f"priced one (MONEY EXPOSURE)"
    )
    selected = choose_from_pool(pools["auto"])
    assert selected.model == "cheap-priced", (
        f"choose_from_pool selected {selected.model!r} — the unpriced model "
        f"was selected over the cheaper priced one (MONEY EXPOSURE)"
    )


def test_guard_blocks_before_any_selection_can_happen() -> None:
    """FAIL-ON-REVERT: the guard raises BEFORE any ordering is derived or
    selection happens.  Even if the unpriced model's upstream is PRICIER,
    the deploy is held — the operator never ships a routing table with an
    unpriced model in it.

    This is the preflight contract: run ``assert_priced_completeness``
    on the live registry BEFORE purging cost_rank.  If it raises, the
    purge MUST NOT proceed."""
    registry = {
        "cheap-priced": {"cost_input": 0.000001, "cost_output": 0.000003},
        "unpriced-pricier-upstream": {},
    }
    with pytest.raises(PricedCompletenessError) as exc:
        assert_priced_completeness(registry)
    assert "unpriced-pricier-upstream" in str(exc.value)


def test_fully_priced_catalog_selection_works() -> None:
    """FAIL-ON-REVERT: a fully-priced catalog passes the guard AND selects the
    cheaper model first — proving the guard does not break normal operation."""
    registry = {
        "cheap": {
            "upstream_base": "http://cheap/v1",
            "cost_input": 0.000001,
            "cost_output": 0.000003,
        },
        "dear": {
            "upstream_base": "http://dear/v1",
            "cost_input": 0.000010,
            "cost_output": 0.000030,
        },
    }
    assert_priced_completeness(registry)  # no raise — fully priced
    pool_map = {"auto": ["dear", "cheap"]}  # dear listed first
    _, pools, _ = build_routes_and_pools(registry, pool_map, providers_cfg={})
    order = [r.upstream_base for r in pools["auto"]]
    assert order == ["http://cheap/v1", "http://dear/v1"], (
        f"cheaper model must sort first in a fully-priced catalog, got {order}"
    )


# ─────────────────────────────────────────────────────────────────────────────
# Section 4 — Exemption correctness (disabled / free models don't trip guard)
# ─────────────────────────────────────────────────────────────────────────────


def test_disabled_model_does_not_trip_guard_but_unpriced_does() -> None:
    """A registry with a disabled unpriced model passes, but enabling it
    trips the guard.  This proves the exemption is keyed on ``enabled: false``,
    not on the presence of pricing."""
    unpriced_spec: dict[str, object] = {}  # no cost_input, no cost_output
    # Disabled → exempt
    assert_priced_completeness({"m": {**unpriced_spec, "enabled": False}})
    # Enabled (default) → trips
    with pytest.raises(PricedCompletenessError):
        assert_priced_completeness({"m": unpriced_spec})


def test_free_model_does_not_trip_guard_but_unpriced_does() -> None:
    """A registry with a free unpriced model passes, but removing ``free: true``
    trips the guard.  This proves the exemption is keyed on ``free: true``,
    not on the presence of pricing."""
    unpriced_spec: dict[str, object] = {}  # no cost_input, no cost_output
    # Free → exempt
    assert_priced_completeness({"m": {**unpriced_spec, "free": True}})
    # Not free → trips
    with pytest.raises(PricedCompletenessError):
        assert_priced_completeness({"m": {**unpriced_spec, "free": False}})


# ─────────────────────────────────────────────────────────────────────────────
# Section 5 — Edge cases
# ─────────────────────────────────────────────────────────────────────────────


def test_model_with_only_cost_input_is_not_unpriced() -> None:
    """A model with only cost_input (no cost_output) is NOT unpriced — the
    missing side is priced from zero.  The guard must not trip."""
    registry = {"input-only": {"cost_input": 0.000001}}
    assert find_unpriced_models(registry) == []
    assert_priced_completeness(registry)  # no raise


def test_model_with_only_cost_output_is_not_unpriced() -> None:
    """A model with only cost_output (no cost_input) is NOT unpriced — the
    missing side is priced from zero.  The guard must not trip."""
    registry = {"output-only": {"cost_output": 0.000003}}
    assert find_unpriced_models(registry) == []
    assert_priced_completeness(registry)  # no raise


def test_assert_priced_completeness_does_not_mutate_registry() -> None:
    """The guard must not mutate the registry (no side effects)."""
    registry: dict[str, dict] = {"bad": {}}
    snapshot = json.dumps(registry, sort_keys=True)
    with pytest.raises(PricedCompletenessError):
        assert_priced_completeness(registry)
    assert json.dumps(registry, sort_keys=True) == snapshot
