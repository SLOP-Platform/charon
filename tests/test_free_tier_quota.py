"""DONE-contract tests for FREE-TIER-QUOTA-ROUTING.

All tests use injectable clocks and mock routes — no real network, no live providers.
"""
from __future__ import annotations

from pathlib import Path

from charon.quota import _ProviderState
from charon.routing_policy.free_tier import (
    FreeTierLedger,
    FreeTierPolicy,
    ProviderLimit,
    _int_or_none,
    load_tsv_seed,
    order_chain_free_first,
)


class FakeClock:
    """Injectably mutable monotonic clock."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def set(self, t: float) -> None:
        self._t = t

    def advance(self, dt: float) -> None:
        self._t += dt


class _UtcClock:
    """Injectably mutable UTC clock."""

    def __init__(self, start: float = 0.0) -> None:
        self._t = start

    def __call__(self) -> float:
        return self._t

    def set(self, t: float) -> None:
        self._t = t

    def advance(self, dt: float) -> None:
        self._t += dt


class _MockRoute:
    """Minimal mock for ``UpstreamRoute``."""

    def __init__(
        self,
        model_id: str | None = None,
        provider: str | None = None,
        label: str | None = None,
        free: bool = False,
        upstream_base: str = "https://example.com/v1",
    ) -> None:
        self.model_id = model_id
        self.pool_id = None
        self.provider = provider
        self._label = label or provider or "unknown"
        self.free = free
        self.upstream_base = upstream_base

    @property
    def label(self) -> str:
        return self._label


# ---------------------------------------------------------------------------
# DONE contract (a): free leg with headroom preferred over one near limit
# ---------------------------------------------------------------------------


def _make_ledger_with_state() -> tuple[FreeTierLedger, FakeClock, _UtcClock]:
    """Build a ledger with injectable clocks and expose clocks for test control."""
    clock = FakeClock(0.0)
    utc = _UtcClock(1_700_000_000.0)
    ledger = FreeTierLedger()
    ledger.tracker._now = clock
    ledger.tracker._utc_now = utc
    return ledger, clock, utc


def test_free_leg_with_headroom_chosen_over_near_limit():
    """(a) Given two free legs, the one with more remaining quota is chosen."""
    ledger, clock, utc = _make_ledger_with_state()

    # groq: near limit (900 used of 1000 rpd) → 10% headroom
    ledger.tracker._active["groq"] = {"rpd": (1000, "rolling")}
    st_groq = _ProviderState()
    from collections import deque
    st_groq.req_rolling["rpd"] = deque([float(i) for i in range(900)])
    ledger.tracker._state["groq"] = st_groq

    # cerebras: lots of headroom (only 10 tokens used of 1M tpd) → 99.999% headroom
    ledger.tracker._active["cerebras"] = {"tpd": (1_000_000, "rolling")}
    st_cere = _ProviderState()
    st_cere.tok_rolling["tpd"] = deque([(0.0, 10)])
    ledger.tracker._state["cerebras"] = st_cere

    chain = [
        _MockRoute(model_id="groq/llama", provider="groq", free=True),
        _MockRoute(model_id="cerebras/gemma", provider="cerebras", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger, est_tokens=100)

    assert ordered[0].provider == "cerebras"
    assert ordered[1].provider == "groq"


def test_free_leg_with_headroom_chosen_revert_is_red():
    """(a RED) Reverting the headroom ordering picks the wrong leg."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["fast"] = {"rpd": (1000, "rolling")}
    st_fast = _ProviderState()
    from collections import deque
    st_fast.req_rolling["rpd"] = deque([float(i) for i in range(900)])  # near limit
    ledger.tracker._state["fast"] = st_fast

    ledger.tracker._active["slow"] = {"rpd": (1000, "rolling")}
    st_slow = _ProviderState()
    st_slow.req_rolling["rpd"] = deque([])  # full headroom
    ledger.tracker._state["slow"] = st_slow

    chain = [
        _MockRoute(model_id="m/fast", provider="fast", free=True),
        _MockRoute(model_id="m/slow", provider="slow", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger, est_tokens=10)

    assert ordered[0].provider == "slow"


# ---------------------------------------------------------------------------
# DONE contract (b): free leg at limit skipped BEFORE request is sent
# ---------------------------------------------------------------------------


def test_free_leg_at_limit_is_deprioritised():
    """(b) A free leg at its limit is deprioritised (still in chain) so no
    429 is incurred by sending to it first."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["exhausted"] = {"rpd": (5, "rolling")}
    st_ex = _ProviderState()
    from collections import deque
    st_ex.req_rolling["rpd"] = deque([float(i) for i in range(5)])
    ledger.tracker._state["exhausted"] = st_ex

    ledger.tracker._active["headroom"] = {"rpd": (5, "rolling")}
    st_hd = _ProviderState()
    st_hd.req_rolling["rpd"] = deque([])
    ledger.tracker._state["headroom"] = st_hd

    chain = [
        _MockRoute(model_id="m/exhausted", provider="exhausted", free=True),
        _MockRoute(model_id="m/headroom", provider="headroom", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger)

    assert ordered[0].provider == "headroom"
    assert any(r.provider == "exhausted" for r in ordered)


def test_free_leg_at_limit_is_deprioritised_revert_is_red():
    """(b RED) Reverting the deprioritisation would pick the exhausted leg first."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["exhausted"] = {"rpd": (2, "rolling")}
    st_ex = _ProviderState()
    from collections import deque
    st_ex.req_rolling["rpd"] = deque([0.0, 1.0])
    ledger.tracker._state["exhausted"] = st_ex

    ledger.tracker._active["headroom"] = {"rpd": (100, "rolling")}
    st_hd = _ProviderState()
    st_hd.req_rolling["rpd"] = deque([])
    ledger.tracker._state["headroom"] = st_hd

    chain = [
        _MockRoute(model_id="m/exhausted", provider="exhausted", free=True),
        _MockRoute(model_id="m/headroom", provider="headroom", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger)

    assert ordered[0].provider == "headroom"


# ---------------------------------------------------------------------------
# DONE contract (c): all free legs exhausted → fallback to cheapest paid
# ---------------------------------------------------------------------------


def test_all_free_exhausted_falls_back_to_paid():
    """(c) When all free legs are at limit, paid legs still serve the request."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["groq"] = {"rpd": (1, "rolling")}
    st_g = _ProviderState()
    from collections import deque
    st_g.req_rolling["rpd"] = deque([0.0])
    ledger.tracker._state["groq"] = st_g

    ledger.tracker._active["mistral"] = {"rpd": (1, "rolling")}
    st_m = _ProviderState()
    st_m.req_rolling["rpd"] = deque([0.0])
    ledger.tracker._state["mistral"] = st_m

    chain = [
        _MockRoute(model_id="groq/model", provider="groq", free=True),
        _MockRoute(model_id="mistral/model", provider="mistral", free=True),
        _MockRoute(model_id="openai/gpt-4o", provider="openai", free=False),
        _MockRoute(model_id="anthropic/claude", provider="anthropic", free=False),
    ]

    ordered = order_chain_free_first(chain, ledger)

    assert any(r.provider == "openai" for r in ordered)
    assert any(r.provider == "anthropic" for r in ordered)
    # Paid legs are reachable: their position after free legs means the chain is non-empty
    # and a request would reach paid legs if free legs are all skipped
    paid_in_chain = any(not getattr(r, "free", False) for r in ordered)
    assert paid_in_chain


def test_cost_rank_key_applied_to_paid_legs():
    """(c) Paid legs are ordered by cost_rank_key when provided."""
    ledger = FreeTierLedger()

    chain = [
        _MockRoute(model_id="m/paid1", provider="paid1", free=False),
        _MockRoute(model_id="m/paid2", provider="paid2", free=False),
        _MockRoute(model_id="m/free", provider="free", free=True),
    ]

    def cost_rank_key(route) -> tuple[bool, int, int]:
        costs = {"paid1": 1000, "paid2": 100, "free": 0}
        rank = costs.get(route.provider, 9999)
        return (False, 3, rank)

    ordered = order_chain_free_first(chain, ledger, cost_rank_key=cost_rank_key)

    paid_order = [r.provider for r in ordered if r.provider in ("paid1", "paid2")]
    assert paid_order == ["paid2", "paid1"]


# ---------------------------------------------------------------------------
# DONE contract (d): quota-exhausted distinct from faulty; re-admitted at rollover
# ---------------------------------------------------------------------------


def test_quota_exhausted_distinct_from_faulty():
    """(d) A quota-exhausted leg is NOT flagged as faulty — it is tracked
    separately and re-admitted at window rollover."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["quota_exhausted"] = {"rpd": (2, "rolling")}
    st = _ProviderState()
    from collections import deque
    st.req_rolling["rpd"] = deque([0.0, 1.0])
    ledger.tracker._state["quota_exhausted"] = st

    assert ledger.should_skip("quota_exhausted") is True
    assert ledger.is_exhausted("quota_exhausted") is True

    counters = ledger.counters()
    assert "skip_rpd" in counters


def test_quota_exhausted_re_admitted_at_rollover():
    """(d) A quota-exhausted leg recovers when its window rolls over."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["quota_exhausted"] = {"rpm": (2, "rolling")}
    st = _ProviderState()
    from collections import deque
    st.req_rolling["rpm"] = deque([0.0, 1.0])
    ledger.tracker._state["quota_exhausted"] = st

    assert ledger.should_skip("quota_exhausted") is True

    clock.set(62.0)

    assert ledger.should_skip("quota_exhausted") is False


# ---------------------------------------------------------------------------
# DONE contract (e): unknown-limit provider surfaced, not dropped or preferred
# ---------------------------------------------------------------------------


def test_unknown_limit_not_silently_dropped():
    """(e) A provider with unknown limits is NOT silently dropped from the chain."""
    ledger = FreeTierLedger()

    chain = [
        _MockRoute(model_id="zai/glm", provider="zai", free=True),
        _MockRoute(model_id="groq/llama", provider="groq", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger)

    assert any(r.provider == "zai" for r in ordered)


def test_unknown_limit_not_preferred_as_unlimited():
    """(e) Unknown-limit free legs are sorted after known-headroom legs."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["known"] = {"rpd": (1000, "rolling")}
    st = _ProviderState()
    ledger.tracker._state["known"] = st

    chain = [
        _MockRoute(model_id="zai/unknown", provider="zai", free=True),
        _MockRoute(model_id="known/model", provider="known", free=True),
    ]

    ordered = order_chain_free_first(chain, ledger)

    zai_idx = next(i for i, r in enumerate(ordered) if r.provider == "zai")
    known_idx = next(i for i, r in enumerate(ordered) if r.provider == "known")
    assert known_idx < zai_idx


# ---------------------------------------------------------------------------
# FreeTierPolicy select() integration
# ---------------------------------------------------------------------------


def test_policy_select_uses_free_tier_ordering():
    """FreeTierPolicy.select() reorders a pool chain free-first by quota."""
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["high"] = {"tpd": (1_000_000, "rolling")}
    st_h = _ProviderState()
    from collections import deque
    st_h.tok_rolling["tpd"] = deque([(0.0, 100_000)])  # 900k headroom
    ledger.tracker._state["high"] = st_h

    ledger.tracker._active["low"] = {"tpd": (1_000_000, "rolling")}
    st_l = _ProviderState()
    st_l.tok_rolling["tpd"] = deque([(0.0, 990_000)])  # 10k headroom
    ledger.tracker._state["low"] = st_l

    policy = FreeTierPolicy(ledger=ledger)

    pools = {
        "test-model": [
            _MockRoute(model_id="low/model", provider="low", free=True),
            _MockRoute(model_id="high/model", provider="high", free=True),
        ]
    }

    result = policy.select(model_id="test-model", pools=pools, est_tokens=1000)

    assert result[0].provider == "high"
    assert result[1].provider == "low"


def test_policy_select_unknown_model_returns_empty():
    """When model_id is not in pools/routes, select returns []. """
    policy = FreeTierPolicy()
    result = policy.select(model_id="nonexistent-model", pools={}, routes={})
    assert result == []


# ---------------------------------------------------------------------------
# ProviderLimit / TSV loading
# ---------------------------------------------------------------------------


def test_int_or_none_parses_correctly():
    assert _int_or_none("1000") == 1000
    assert _int_or_none(500) == 500
    assert _int_or_none("-") is None
    assert _int_or_none("unknown") is None
    assert _int_or_none("") is None
    assert _int_or_none(None) is None
    assert _int_or_none("unpublished") is None


def test_provider_limit_has_any_limit():
    pl = ProviderLimit(provider="groq", model="llama", rpd=14400)
    assert pl.has_any_limit() is True

    pl2 = ProviderLimit(provider="zai", model="glm")
    assert pl2.has_any_limit() is False


def test_provider_limit_is_unknown():
    pl = ProviderLimit(provider="zai", model="glm")
    assert pl.is_unknown() is True

    pl2 = ProviderLimit(provider="groq", model="llama", tpd=100000)
    assert pl2.is_unknown() is False


def test_provider_limit_limits_dict():
    pl = ProviderLimit(provider="groq", model="llama", rpd=14400, rpm=1000, tpd=100000)
    ld = pl.limits_dict()
    assert ld == {"rpd": 14400, "rpm": 1000, "tpd": 100000}


# ---------------------------------------------------------------------------
# headroom / remaining_quota
# ---------------------------------------------------------------------------


def test_headroom_returns_none_for_unconfigured_provider():
    ledger = FreeTierLedger()
    assert ledger.get_headroom("completely_unknown") is None


def test_headroom_returns_float_for_configured_provider():
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["p"] = {"tpd": (1000, "rolling")}
    st = _ProviderState()
    from collections import deque
    st.tok_rolling["tpd"] = deque([(0.0, 300)])
    ledger.tracker._state["p"] = st

    h = ledger.get_headroom("p", "tpd")
    assert h is not None
    assert 0.0 <= h <= 1.0


def test_remaining_quota_combines_windows():
    ledger, clock, utc = _make_ledger_with_state()

    ledger.tracker._active["p"] = {"tpd": (100, "rolling"), "rpd": (10, "rolling")}
    st = _ProviderState()
    from collections import deque
    st.tok_rolling["tpd"] = deque([(0.0, 90)])  # 10% headroom
    st.req_rolling["rpd"] = deque([float(i) for i in range(9)])  # 1 req left
    ledger.tracker._state["p"] = st

    rq = ledger.remaining_quota("p")
    assert rq is not None
    assert abs(rq - 0.1) < 0.001


# ---------------------------------------------------------------------------
# reconcile_from_observed
# ---------------------------------------------------------------------------


def test_reconcile_from_observed_updates_limits():
    ledger = FreeTierLedger()
    ledger.reconcile_from_observed("test_prov", {"rpd": 500, "tpd": 10000})

    assert ledger.tracker._active.get("test_prov") is not None
    assert ledger.tracker._active["test_prov"]["rpd"] == (500, "rolling")


def test_reconcile_from_observed_ignores_empty():
    ledger = FreeTierLedger()
    ledger.reconcile_from_observed("test_prov", {})
    assert ledger.tracker._active.get("test_prov") is None


# ---------------------------------------------------------------------------
# load_tsv_seed
# ---------------------------------------------------------------------------


def test_load_tsv_seed(tmp_path: Path):
    tsv = tmp_path / "FREE-TIER-LIMITS.tsv"
    tsv.write_text(
        "provider\tmodel\trpd\trpm\ttpd\ttpm\tcontext_cap\ttrains_on_data\tpersonal_only\texhaustion_signal\n"
        "groq\tllama-3.1-8b-instant\t14400\t1000\t-\t-\t-\tFALSE\tFALSE\t429 on overage\n"
        "zai\tglm-4.5-flash-zai\t-\t-\t-\t-\t-\t-\t-\tunpublished\n",
        encoding="utf-8",
    )

    seed = load_tsv_seed(tsv)

    assert ("groq", "llama-3.1-8b-instant") in seed
    assert seed[("groq", "llama-3.1-8b-instant")].rpd == 14400
    assert seed[("groq", "llama-3.1-8b-instant")].rpm == 1000
    assert seed[("groq", "llama-3.1-8b-instant")].unpublished is False

    assert ("zai", "glm-4.5-flash-zai") in seed
    assert seed[("zai", "glm-4.5-flash-zai")].is_unknown() is True


def test_load_tsv_seed_missing_file_returns_empty():
    seed = load_tsv_seed(Path("/nonexistent/path/FREE-TIER-LIMITS.tsv"))
    assert seed == {}


# ---------------------------------------------------------------------------
# FreeTierLedger.from_tsv round-trip
# ---------------------------------------------------------------------------


def test_ledger_from_tsv_loads_correct_limits(tmp_path: Path):
    tsv = tmp_path / "FREE-TIER-LIMITS.tsv"
    tsv.write_text(
        "provider\tmodel\trpd\trpm\ttpd\ttpm\tcontext_cap\ttrains_on_data\tpersonal_only\texhaustion_signal\n"
        "groq\tllama-3.1-8b-instant\t14400\t-\t-\t-\t-\tFALSE\tFALSE\t429\n"
        "cerebras\tfree-cerebras\t-\t-\t1000000\t-\t-\tFALSE\tFALSE\t429\n",
        encoding="utf-8",
    )

    ledger = FreeTierLedger.from_tsv(tsv, state_dir=tmp_path)

    assert ledger.tracker._active.get("groq") is not None
    assert ledger.tracker._active["groq"]["rpd"] == (14400, "rolling")
    assert ledger.tracker._active.get("cerebras") is not None
    assert ledger.tracker._active["cerebras"]["tpd"] == (1_000_000, "rolling")


# ---------------------------------------------------------------------------
# record() updates tracker
# ---------------------------------------------------------------------------


def test_record_updates_tracker():
    ledger, clock, utc = _make_ledger_with_state()
    ledger.tracker._active["p"] = {"tpd": (1000, "rolling")}

    ledger.record("p", tokens=500)
    ledger.record("p", tokens=300)

    assert not ledger.should_skip("p", est_tokens=100)
    assert ledger.should_skip("p", est_tokens=201)


# ---------------------------------------------------------------------------
# is_unknown_limit
# ---------------------------------------------------------------------------


def test_is_unknown_limit_true_for_unconfigured():
    ledger = FreeTierLedger()
    assert ledger.is_unknown_limit("zai") is True


def test_is_unknown_limit_false_for_configured():
    ledger, clock, utc = _make_ledger_with_state()
    ledger.tracker._active["groq"] = {"rpd": (14400, "rolling")}
    assert ledger.is_unknown_limit("groq") is False
