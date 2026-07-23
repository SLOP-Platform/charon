"""FAIL-ON-REVERT tests for GW-BRIDGE-4 park<->cooldown unification.

Three invariants (operator, non-negotiable):
  1. PARKED EXCLUDED — a parked provider is absent from the Router's resolved
     selectable set; park == not-selected.
  2. SOLE-LEG GUARD — with one viable leg left, park/cooldown does NOT remove
     it; request still routes.
  3. RE-ARM — a provider re-armed on top-up returns to the selectable set.

Reverting the corresponding guard in ``park_cooldown.py`` turns the test red.
"""
from __future__ import annotations

from collections.abc import Callable

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


# ── INVARIANT 2: SOLE-LEG GUARD ──────────────────────────────────────────────


def test_sole_leg_guard_keeps_last_leg():
    """When every leg would be excluded, the original chain is returned.

    FAIL-ON-REVERT: removing the sole_leg_guard check (or returning
    empty) would strand a model with no routable provider."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    chain = [_R("acme")]
    result = park_cooldown_filter_chain(chain, bt=bt)
    assert len(result) == 1
    assert _provider_id(result[0]) == "acme"


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


def test_sole_leg_guard_multi_model():
    """Sole-leg guard works per-chain — each model is independent."""
    bt = _bt(
        providers={"acme": 5.0, "beta": 3.0, "gamma": 1.0},
        parked={"acme", "gamma"},
    )
    chains = {
        "m1": [_R("acme")],        # sole leg → guard keeps it
        "m2": [_R("acme"), _R("beta")],  # have another option → acme excluded
        "m3": [_R("gamma")],        # sole leg → guard keeps it
    }
    for model_id, chain in chains.items():
        result = park_cooldown_filter_chain(chain, bt=bt)
        assert len(result) >= 1, f"{model_id} stranded"
    # m1 keeps acme, m2 drops acme, m3 keeps gamma
    assert _provider_id(chains["m1"][0]) == "acme"
    m2_result = park_cooldown_filter_chain(chains["m2"], bt=bt)
    assert all(_provider_id(r) != "acme" for r in m2_result)
    assert _provider_id(chains["m3"][0]) == "gamma"


def test_sole_leg_guard_function_unit():
    """sole_leg_guard returns live when non-empty, original when empty."""
    live = [_R("acme")]
    original = [_R("acme"), _R("beta")]
    assert sole_leg_guard(live, original) is live
    assert sole_leg_guard([], original) is not original
    assert [r for r in sole_leg_guard([], original)] == original


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
    """count_viable_legs returns 0 even with sole-leg guard — this is raw
    count, not a filter decision."""
    bt = _bt(providers={"acme": 5.0}, parked={"acme"})
    chain = [_R("acme")]
    assert count_viable_legs(chain, bt=bt) == 0


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


# ── Router cooldown integration (mock Router) ────────────────────────────────


def test_router_cooled_provider_is_excluded():
    """A provider whose deployment is cooled (Router cooldown state) is
    excluded alongside parked providers.

    FAIL-ON-REVERT: if cooldown state is not read, a cooled deployment
    stays selectable — the two exclusion sets disagree."""
    now = 1_000_000.0
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

    class _MockRouter:
        _failed_calls = {
            "dep_acme": [now - 5, now - 10, now - 15],
        }
        cooldown_time = 60.0
        allowed_fails = 3
        model_list = ml

    chain = [_R("acme"), _R("beta")]

    # Without Router — both should be present
    result_no_router = park_cooldown_filter_chain(chain, bt=bt, router=None)
    assert len(result_no_router) == 2

    # With Router where acme is cooled — acme should be excluded
    with _patch_monotonic(now):
        result_with_router = park_cooldown_filter_chain(
            chain, bt=bt, router=_MockRouter())
    ids = [_provider_id(r) for r in result_with_router]
    assert "acme" not in ids, "cooled acme should be excluded"
    assert "beta" in ids


def test_router_cooldown_expired_does_not_exclude():
    """A deployment whose cooldown has expired is NOT excluded.

    FAIL-ON-REVERT: if expired cooldowns are still excluded, a recovered
    provider never re-enters the set."""
    class _MockRouterExpired:
        _failed_calls = {
            "dep_acme": [100.0, 200.0, 300.0],  # all 300s old, cooldown=60
        }
        cooldown_time = 60.0
        allowed_fails = 3
        model_list = [
            {
                "model_name": "m1",
                "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
                "model_info": {"id": "dep_acme", "provider": "acme"},
            },
        ]

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    with _patch_monotonic(1_000_000.0):  # 1M >> (300 + 60), all failures expired
        result = park_cooldown_filter_chain(chain, bt=bt, router=_MockRouterExpired())
    assert len(result) == 1
    assert _provider_id(result[0]) == "acme"


def test_router_not_enough_fails_does_not_exclude():
    """Fewer than allowed_fails failures does NOT cool the deployment."""
    class _MockRouterWarm:
        _failed_calls = {
            "dep_acme": [100.0],  # only 1 failure, allowed_fails=3
        }
        cooldown_time = 60.0
        allowed_fails = 3
        model_list = [
            {
                "model_name": "m1",
                "litellm_params": {"model": "openai/gpt", "api_base": "https://api.acme.test/v1"},
                "model_info": {"id": "dep_acme", "provider": "acme"},
            },
        ]

    bt = _bt(providers={"acme": 5.0})
    chain = [_R("acme")]
    with _patch_monotonic(1_000_000.0):
        result = park_cooldown_filter_chain(chain, bt=bt, router=_MockRouterWarm())
    assert len(result) == 1


def test_router_missing_attributes_fallback():
    """When Router lacks _failed_calls or model_list, no cooldown-based
    exclusion is applied — the code gracefully degrades."""
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


# ── monkey-patch helper for _monotonic ───────────────────────────────────────


def _patch_monotonic(fake_time: float):
    """Context manager that replaces park_cooldown._monotonic with a
    constant-returning stub."""
    import contextlib

    @contextlib.contextmanager
    def _ctx():
        old = None
        import charon.litellm_plane.park_cooldown as pc
        old = pc._monotonic
        pc._monotonic = lambda: fake_time
        try:
            yield
        finally:
            if old is not None:
                pc._monotonic = old

    return _ctx()
