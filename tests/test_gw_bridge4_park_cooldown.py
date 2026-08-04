"""FAIL-ON-REVERT tests for GW-BRIDGE-4 park<->cooldown unification.

Three invariants (operator, non-negotiable):
  1. PARKED EXCLUDED — a parked provider is absent from the Router's resolved
     selectable set; park == not-selected.
  2. PARK-AWARE SOLE-LEG GUARD (D-018) — the never-strand guard applies ONLY
     to a chain excluded purely by transient cooldown. A chain with any
     parked leg is NOT restored: park is the stronger signal, so a
     fully-parked chain yields empty and the caller answers with the D-012
     503, never a money-leak 200.
  3. RE-ARM — a provider re-armed on top-up returns to the selectable set.

Reverting the corresponding guard in ``park_cooldown.py`` turns the test red.
"""
from __future__ import annotations

import time
from collections.abc import Callable

import pytest

from charon.balance import BalanceTracker
from charon.litellm_plane.park_cooldown import (
    _provider_id,
    count_viable_legs,
    excluded_provider_ids,
    park_cooldown_filter_chain,
    parked_providers,
    sole_leg_guard,
)


class _R:
    """A duck-typed route with .provider and .label (like UpstreamRoute)."""

    def __init__(self, provider: str | None = None, label: str | None = None):
        self.provider = provider
        self.label = label


# ── helper: build a BalanceTracker with class-3 fixed providers ──────────────


def _bt(
    *,
    providers: dict[str, float],
    parked: set[str] | None = None,
    spend_fn: Callable[[str], float] | None = None,
) -> BalanceTracker:
    """Create a BalanceTracker with fixed-mode class-3 providers."""
    cfg: dict[str, dict] = {}
    for pid, bal in providers.items():
        cfg[pid] = {"mode": "fixed", "starting_balance": bal, "funding_class": 3}
    bt = BalanceTracker(config=cfg)
    if spend_fn is not None:
        bt.set_spend_provider_fn(spend_fn)
    if parked:
        for pid in parked:
            bt.park(pid)
    return bt


# ── INVARIANT 1: PARKED EXCLUDED ─────────────────────────────────────────────


def test_parked_provider_excluded_from_filtered_chain():
    """A parked provider is removed from the chain by park_cooldown_filter_chain.

    FAIL-ON-REVERT: dropping the is_parked check in the filter re-admits
    a parked provider into the selectable set."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    result = park_cooldown_filter_chain(chain, bt=bt)
    assert all(_provider_id(r) != "acme" for r in result)
    assert any(_provider_id(r) == "beta" for r in result)


def test_parked_provider_excluded_set():
    """excluded_provider_ids returns parked provider IDs.

    FAIL-ON-REVERT: removing the park read makes the exclusion set
    incomplete."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    excluded = excluded_provider_ids(bt=bt)
    assert "acme" in excluded


def test_parked_providers_snapshot():
    """parked_providers returns the parked set from a BalanceTracker.

    FAIL-ON-REVERT: if parked_providers returns empty, the bridge
    cannot see park state."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    ps = parked_providers(bt)
    assert ps == {"acme"}


def test_parked_providers_none_bt_is_empty():
    """parked_providers(None) returns an empty set (graceful degradation)."""
    assert parked_providers(None) == set()


def test_no_park_exclusion_without_bt():
    """park_cooldown_filter_chain with bt=None returns chain unchanged."""
    chain = [_R("acme"), _R("beta")]
    result = park_cooldown_filter_chain(chain, bt=None)
    assert result == chain


def test_non_parked_providers_survive():
    """A non-parked provider survives the filter unchanged.

    FAIL-ON-REVERT: if the filter incorrectly removes a provider, the
    set becomes under-populated."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0, "gamma": 1.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta"), _R("gamma")]
    result = park_cooldown_filter_chain(chain, bt=bt)
    ids = [_provider_id(r) for r in result]
    assert "acme" not in ids
    assert "beta" in ids
    assert "gamma" in ids


# ── INVARIANT 2: PARK-AWARE SOLE-LEG GUARD (D-018) ───────────────────────────


def test_parked_sole_leg_is_not_restored():
    """A chain whose ONLY leg is parked is NOT restored — it yields empty.

    FAIL-ON-REVERT: the pre-D-018 guard returned the ORIGINAL chain (parked
    leg re-admitted) whenever ``live`` was empty — the exact money leak
    D-012 outlawed in forwarder.py. D-018 inverts it: park is the stronger
    signal, so the fully-parked chain returns empty and the caller answers
    with the D-012 503 (``no_provider_reason == "all_legs_parked"``).
    """
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt)
    assert result == []


def test_sole_leg_guard_with_two_legs_one_parked():
    """With two legs, one parked, the live leg alone survives — guard not needed.

    FAIL-ON-REVERT: removing the guard cannot break this case (live
    is non-empty), but verifying it keeps working prevents regression."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    result = park_cooldown_filter_chain(chain, bt=bt)
    ids = [_provider_id(r) for r in result]
    assert "acme" not in ids
    assert "beta" in ids
    assert len(result) == 1


def test_parked_sole_legs_not_restored_per_chain():
    """Parked sole legs return empty per-chain — each model is independent.

    FAIL-ON-REVERT: the pre-D-018 guard kept a parked sole leg per-chain
    (m1 and m3 below were restored). D-018 inverts it: a chain whose only
    remaining legs are parked yields empty, while a chain with another live
    option still drops the parked leg and keeps the live one."""
    bt = _bt(
        providers={"acme": 5.0, "beta": 3.0, "gamma": 1.0},
        parked={"acme", "gamma"},
    )
    chains = {
        "m1": [_R("acme")],        # sole leg parked → NOT restored (empty)
        "m2": [_R("acme"), _R("beta")],  # have another option → acme excluded
        "m3": [_R("gamma")],        # sole leg parked → NOT restored (empty)
    }
    assert park_cooldown_filter_chain(chains["m1"], bt=bt) == []
    m2_result = park_cooldown_filter_chain(chains["m2"], bt=bt)
    ids2 = [_provider_id(r) for r in m2_result]
    assert "acme" not in ids2
    assert "beta" in ids2
    assert park_cooldown_filter_chain(chains["m3"], bt=bt) == []


def test_sole_leg_guard_function_unit():
    """sole_leg_guard returns live when non-empty, original when empty.

    The guard function itself is the COOLDOWN-ONLY half (D-018): it still
    never-strands when called, but park_cooldown_filter_chain only calls it
    after establishing no leg is parked."""
    live = [_R("acme")]
    original = [_R("acme"), _R("beta")]
    assert sole_leg_guard(live, original) is live
    assert sole_leg_guard([], original) is not original
    assert [r for r in sole_leg_guard([], original)] == original


def test_cooled_only_sole_leg_is_restored():
    """A chain whose only leg is COOLED (not parked) IS restored.

    FAIL-ON-REVERT: dropping the cooldown side of the split (or treating a
    cooled sole leg like a parked one) strands a request on a transient
    upstream blip. D-018 KEEPS the never-strand guard for cooldown-only
    chains — the original chain is returned so the request can still route."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
    ]
    router = litellm.Router(model_list=ml)
    router.cooldown_cache.add_deployment_to_cooldown(
        model_id="dep_acme",
        original_exception=Exception("test cooldown"),
        exception_status=429,
        cooldown_time=60.0,
    )

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=router)
    assert len(result) == 1
    assert _provider_id(result[0]) == "acme"


def test_mixed_parked_and_cooled_none_live_is_not_restored():
    """Mixed park+cooldown with no live leg: park wins, result is empty.

    FAIL-ON-REVERT: a merged guard would restore BOTH legs (re-admitting the
    parked one) to satisfy the cooldown-shaped never-strand rule. D-018
    states park is the stronger signal — parked legs are never restored, so
    the mixed chain yields empty and the caller answers the D-012 503."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.beta.test/v1"},
            "model_info": {"id": "dep_beta", "provider": "beta"},
        },
    ]
    router = litellm.Router(model_list=ml)
    router.cooldown_cache.add_deployment_to_cooldown(
        model_id="dep_beta",
        original_exception=Exception("test cooldown"),
        exception_status=429,
        cooldown_time=60.0,
    )

    # acme parked (operator), beta cooled (transient), none live
    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=router)
    assert result == []


# ── INVARIANT 3: RE-ARM (top-up → unpark → returns to set) ───────────────────


def test_rearmed_provider_returns_to_selectable_set():
    """A provider re-armed (unparked after top-up) re-appears in the chain.

    FAIL-ON-REVERT: if unpark does not restore a provider to the
    selectable set, the provider stays excluded indefinitely and
    cannot rejoin the pool."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]

    # Initially parked — excluded
    result = park_cooldown_filter_chain(chain, bt=bt)
    assert all(_provider_id(r) != "acme" for r in result)

    # Re-arm: top-up + unpark
    bt.top_up("acme", 10.0)
    bt.unpark("acme")

    # Now re-armed — included
    result2 = park_cooldown_filter_chain(chain, bt=bt)
    ids2 = [_provider_id(r) for r in result2]
    assert "acme" in ids2
    assert "beta" in ids2


def test_rearmed_restores_count():
    """count_viable_legs reflects re-arm."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    assert count_viable_legs(chain, bt=bt) == 1
    bt.unpark("acme")
    assert count_viable_legs(chain, bt=bt) == 2


# ── count_viable_legs ────────────────────────────────────────────────────────


def test_count_viable_all_alive():
    """count_viable_legs returns full length when nothing is parked."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0})
    chain = [_R("acme"), _R("beta")]
    assert count_viable_legs(chain, bt=bt) == 2


def test_count_viable_some_parked():
    """count_viable_legs excludes parked providers."""
    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    assert count_viable_legs(chain, bt=bt) == 1


def test_count_viable_all_parked():
    """count_viable_legs returns 0 for a fully-parked chain — agrees with the
    filter, which yields empty (D-012 503, never a money-leak restore)."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    chain = [_R("acme")]
    assert count_viable_legs(chain, bt=bt) == 0


def test_count_viable_agrees_with_filter_cooled_only():
    """count_viable_legs AGREES with the filter for a cooldown-only chain.

    FAIL-ON-REVERT: a raw "not excluded" count would return 0 for a
    fully-cooled chain while the filter RESTORES it — a caller would 503 a
    pool the dispatcher can still serve. count_viable_legs delegates to the
    filter so the two can never disagree (D-018 req. 4)."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.beta.test/v1"},
            "model_info": {"id": "dep_beta", "provider": "beta"},
        },
    ]
    router = litellm.Router(model_list=ml)
    for dep_id in ("dep_acme", "dep_beta"):
        router.cooldown_cache.add_deployment_to_cooldown(
            model_id=dep_id,
            original_exception=Exception("test cooldown"),
            exception_status=429,
            cooldown_time=60.0,
        )

    bt = _bt(providers={"acme": 5.0, "beta": 3.0})
    chain = [_R("acme"), _R("beta")]
    assert count_viable_legs(chain, bt=bt, router=router) == 2
    assert len(park_cooldown_filter_chain(chain, bt=bt, router=router)) == 2


def test_count_viable_agrees_with_filter_mixed():
    """count_viable_legs AGREES with the filter for a mixed park+cooldown
    chain — parked legs are never counted as viable (D-018 req. 4)."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.beta.test/v1"},
            "model_info": {"id": "dep_beta", "provider": "beta"},
        },
    ]
    router = litellm.Router(model_list=ml)
    router.cooldown_cache.add_deployment_to_cooldown(
        model_id="dep_beta",
        original_exception=Exception("test cooldown"),
        exception_status=429,
        cooldown_time=60.0,
    )

    bt = _bt(providers={"acme": 5.0, "beta": 3.0}, parked={"acme"})
    chain = [_R("acme"), _R("beta")]
    assert count_viable_legs(chain, bt=bt, router=router) == 0
    assert park_cooldown_filter_chain(chain, bt=bt, router=router) == []


def test_count_viable_none_bt():
    """count_viable_legs with bt=None returns original length."""
    chain = [_R("acme")]
    assert count_viable_legs(chain, bt=None) == 1


# ── _provider_id helper ──────────────────────────────────────────────────────


def test_provider_id_from_provider():
    """_provider_id prefers .provider over .label."""
    r = _R(provider="acme", label="backup")
    assert _provider_id(r) == "acme"


class _LabelOnly:
    """A route-like object with only .label."""

    def __init__(self, label: str):
        self.label = label


def test_provider_id_from_label():
    """_provider_id falls back to .label when .provider is None."""
    r = _LabelOnly("fallback-node")
    assert _provider_id(r) == "fallback-node"


# ── Router cooldown integration (REAL litellm.Router) ───────────────────────


def test_router_cooled_provider_is_excluded():
    """A provider whose deployment is in the Router's cooldown_cache is
    excluded alongside parked providers.

    FAIL-ON-REVERT: if cooldown state is not read from the public
    ``router.cooldown_cache.get_active_cooldowns()``, a cooled deployment
    stays selectable — the two exclusion sets disagree."""
    litellm = pytest.importorskip("litellm")
    bt = _bt(providers={"acme": 5.0, "beta": 3.0})

    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.beta.test/v1"},
            "model_info": {"id": "dep_beta", "provider": "beta"},
        },
    ]
    router = litellm.Router(model_list=ml)

    # Cool down acme via the real CooldownCache
    router.cooldown_cache.add_deployment_to_cooldown(
        model_id="dep_acme",
        original_exception=Exception("test cooldown"),
        exception_status=429,
        cooldown_time=60.0,
    )

    chain = [_R("acme"), _R("beta")]

    # Without Router — both should be present
    result_no_router = park_cooldown_filter_chain(chain, bt=bt, router=None)
    assert len(result_no_router) == 2

    # With Router where acme is cooled — acme should be excluded
    result_with_router = park_cooldown_filter_chain(chain, bt=bt, router=router)
    ids = [_provider_id(r) for r in result_with_router]
    assert "acme" not in ids, "cooled acme should be excluded"
    assert "beta" in ids


def test_router_cooldown_expired_does_not_exclude():
    """A deployment whose cooldown has expired (TTL=0) is NOT excluded.

    FAIL-ON-REVERT: if expired cooldowns are still excluded, a recovered
    provider never re-enters the set."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
    ]
    router = litellm.Router(model_list=ml)

    # Cool with TTL=0 — entry expires immediately
    router.cooldown_cache.add_deployment_to_cooldown(
        model_id="dep_acme",
        original_exception=Exception("test"),
        exception_status=429,
        cooldown_time=0.0,
    )
    time.sleep(0.01)

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=router)
    assert len(result) == 1
    assert _provider_id(result[0]) == "acme"


def test_router_not_cooled_provider_ignored():
    """A deployment never added to the cooldown cache is NOT excluded."""
    litellm = pytest.importorskip("litellm")
    ml = [
        {
            "model_name": "m1",
            "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
            "model_info": {"id": "dep_acme", "provider": "acme"},
        },
    ]
    router = litellm.Router(model_list=ml)

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=router)
    assert len(result) == 1
    assert _provider_id(result[0]) == "acme"


def test_router_missing_attributes_fallback():
    """When Router lacks ``get_model_ids`` or ``cooldown_cache``, no
    cooldown-based exclusion is applied — the code gracefully degrades."""
    class _BareRouter:
        pass

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=_BareRouter())
    assert len(result) == 1


def test_router_none_does_not_crash():
    """router=None is handled gracefully (no cooldown exclusion)."""
    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt, router=None)
    assert len(result) == 1
