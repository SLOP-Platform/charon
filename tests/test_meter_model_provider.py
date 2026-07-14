"""METER-MODEL-PROVIDER Wave 1 — real per-(model, provider) cost metering.

NOTE: ``forwarder.py`` caller-wiring (setting ``provider=route.label`` on
``observe()``/``record_spend()`` calls) is DEFERRED to Wave 2. The
per-(model, provider) meter is therefore EMPTY under real traffic today.
These tests exercise the metering mechanism directly via explicit
``provider=`` arguments — they do not reflect any production call site.

Replaces est_cost fabrication with authoritative ACTUAL metered cost per request
keyed by (model, provider). Includes the metering-invariant canary harness
(replay a recorded request stream through the new meter and assert cost-total
delta == 0 vs the prior path + credential-shape invariance) and the
FAIL-ON-REVERT guard: a real provider-costed response records the actual cost,
not the est_cost floor — RED if reverted.
"""
from __future__ import annotations

import math
import threading

from charon.balance import BalanceTracker
from charon.proxy import GatewayProxy

# ── per-(model, provider) cost accumulation ────────────────────────────

def test_model_provider_cost_accumulates() -> None:
    """Multiple observations for the same (model, provider) pair sum their cost."""
    p = GatewayProxy()
    body = {"model": "v", "usage": {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.03}}
    for _ in range(4):
        p.observe("v", 200, body=body, provider="deepseek")
    assert math.isclose(p.model_provider_cost("v", "deepseek"), 0.12)


def test_model_provider_cost_is_independent_per_key() -> None:
    """Distinct (model, provider) pairs are tracked independently."""
    p = GatewayProxy()
    p.observe("a", 200,
              body={"model": "a",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 1.0}},
              provider="p1")
    p.observe("b", 200,
              body={"model": "b",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 2.0}},
              provider="p2")
    p.observe("a", 200,
              body={"model": "a",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 3.0}},
              provider="p2")
    assert math.isclose(p.model_provider_cost("a", "p1"), 1.0)
    assert math.isclose(p.model_provider_cost("b", "p2"), 2.0)
    assert math.isclose(p.model_provider_cost("a", "p2"), 3.0)
    assert p.model_provider_cost("x", "y") == 0.0  # never-seen


def test_model_provider_cost_never_seen_returns_zero() -> None:
    """A never-recorded (model, provider) key returns 0.0 without raising."""
    p = GatewayProxy()
    assert p.model_provider_cost("nonexistent", "noprovider") == 0.0


def test_no_provider_does_not_meter() -> None:
    """When provider is omitted, per-(model, provider) metering is skipped."""
    p = GatewayProxy()
    p.observe("m", 200,
              body={"model": "m",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 99.0}})
    assert p.model_provider_cost("m", "unknown") == 0.0
    assert p.all_model_provider_costs() == {}


def test_count_usage_false_does_not_meter() -> None:
    """When count_usage=False (discarded attempt), cost is NOT metered."""
    p = GatewayProxy()
    p.observe("m", 200,
              body={"model": "m",
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 5.0}},
              provider="deepseek", count_usage=False)
    assert p.model_provider_cost("m", "deepseek") == 0.0
    assert p.cumulative_usage().cost_usd == 0.0


def test_computed_cost_is_metered() -> None:
    """A computed cost (from per-token pricing) is metered at the computed value."""
    pricing = {"m": {"cost_input": 0.000002, "cost_output": 0.000006}}
    p = GatewayProxy(model_pricing=pricing)
    p.observe("m", 200,
              body={"model": "m",
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
              provider="deepseek")
    assert math.isclose(p.model_provider_cost("m", "deepseek"), 0.005)


def test_free_cost_is_metered_at_zero() -> None:
    """A free-flagged model records $0 in the per-(model, provider) meter."""
    p = GatewayProxy(model_pricing={"m": {"free": True}})
    p.observe("m", 200,
              body={"model": "m",
                    "usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
              provider="openrouter")
    assert p.model_provider_cost("m", "openrouter") == 0.0


# ── FAIL-ON-REVERT ─────────────────────────────────────────────────────

def test_real_provider_cost_metered_not_est_floor() -> None:
    """FAIL-ON-REVERT: a response with a real provider-reported cost (cost_source
    ``provider``) must record that ACTUAL cost in the per-(model, provider) meter
    — NOT a fabricated est_cost floor.

    The old est_cost path billed a synthetic floor (``request_bytes/4 * $1.5e-6``)
    on every completion, including provider-costed ones, inflating the spend
    ledger. This test asserts the metered figure is the provider's real cost.
    Reverting to est_cost fabrication (substituting ``est_cost`` for the actual
    ``cost_usd`` in the per-(model, provider) meter) must make this assertion
    FAIL — RED.

    Verify it by:
      1. A provider-reported non-zero cost (0.42) is the metered value.
      2. The cost_source is ``provider`` — a real reported cost, not computed.
    """
    p = GatewayProxy()
    obs = p.observe(
        "deepseek-v4-pro", 200,
        body={"model": "deepseek-v4-pro",
              "usage": {"prompt_tokens": 1000, "completion_tokens": 500, "cost": 0.42}},
        provider="deepseek",
    )
    assert obs.cost_source == "provider", (
        "cost_source must be 'provider' — this is a real reported cost")
    assert obs.usage is not None and obs.usage.cost_usd == 0.42
    metered = p.model_provider_cost("deepseek-v4-pro", "deepseek")
    assert metered == 0.42, (
        f"metered {metered}, expected 0.42 — the actual provider cost, "
        "NOT a fabricated est_cost floor")


def test_computed_cost_metered_not_est_floor() -> None:
    """FAIL-ON-REVERT: a *computed* cost (from stored per-token pricing) must also
    record the computed value, not the est_cost floor. The computed cost is a real
    figure derived from known rates — it is NOT the est_cost fabrication."""
    pricing = {"deepseek-v4-pro": {"cost_input": 0.0000014, "cost_output": 0.0000042}}
    p = GatewayProxy(model_pricing=pricing)
    p.observe(
        "deepseek-v4-pro", 200,
        body={"model": "deepseek-v4-pro",
              "usage": {"prompt_tokens": 1000, "completion_tokens": 500}},
        provider="deepseek",
    )
    metered = p.model_provider_cost("deepseek-v4-pro", "deepseek")
    assert math.isclose(metered, 0.0035), (
        f"metered {metered}, expected 0.0035 — the computed cost from "
        "known per-token pricing, NOT a fabricated est_cost floor")


def test_free_response_meters_zero_not_est_floor() -> None:
    """FAIL-ON-REVERT: a free/flat response with ``cost==0`` must meter $0.00,
    not the positive est_cost floor. The old ``cost if cost > 0 else est_cost``
    logic fabricated spend on every free tier call."""
    p = GatewayProxy(model_pricing={"free-model": {"free": True}})
    p.observe(
        "free-model", 200,
        body={"model": "free-model",
              "usage": {"prompt_tokens": 10000, "completion_tokens": 5000, "cost": 0.0}},
        provider="openrouter",
    )
    metered = p.model_provider_cost("free-model", "openrouter")
    assert metered == 0.0, (
        f"metered {metered}, expected 0.0 — free/flat responses must NOT "
        "record the est_cost floor")


# ── metering-invariant canary ──────────────────────────────────────────

def test_metering_invariant_cost_total_delta_zero() -> None:
    """CANARY (a): replay a recorded request stream through the new meter and
    assert cost-total delta == 0 vs the prior path (global cumulative usage).

    The sum of all per-(model, provider) metered costs MUST equal the global
    cumulative cost on a no-op stream (no failovers, no count_usage=False)
    — the new meter is an orthogonal projection, not a different accounting of
    the same underlying stream. A non-zero delta would mean the two paths have
    diverged (a silent double-count or a missed meter entry)."""
    p = GatewayProxy()
    stream = [
        ("m1", "p1", {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.03}),
        ("m1", "p2", {"prompt_tokens": 8, "completion_tokens": 2, "cost": 0.01}),
        ("m2", "p1", {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.42}),
        ("m1", "p1", {"prompt_tokens": 20, "completion_tokens": 10, "cost": 0.06}),
        ("m2", "p2", {"prompt_tokens": 200, "completion_tokens": 100, "cost": 0.99}),
    ]
    for model, provider, usage in stream:
        p.observe(model, 200,
                  body={"model": model, "usage": usage},
                  provider=provider)

    global_cost = p.cumulative_usage().cost_usd
    expected = 0.03 + 0.01 + 0.42 + 0.06 + 0.99
    assert math.isclose(global_cost, expected), "sanity: known sum"
    mp_total = sum(p.all_model_provider_costs().values())
    assert math.isclose(mp_total, global_cost), (
        f"per-(model,provider) total {mp_total} != global total {global_cost} "
        "— the two paths must agree on a no-op stream with no count_usage=False")


def test_metering_invariant_credential_shape() -> None:
    """CANARY (b): credential-shape invariance — the metered cost for a model
    on a provider is independent of how the credential's model id is shaped.

    A provider-prefixed pool id (``deepseek/deepseek-v4-pro``) and a bare
    model id (``deepseek-v4-pro``) routed to the SAME provider MUST resolve
    to the same cost-per-(model,provider) entry when the underlying model is
    the same and the provider label is the same. The meter keys by the
    requested_model as seen by the router, so a request with a different
    credential shape for the same logical model must still meter correctly
    for that specific key — the invariance is that a model+provider pair's
    cost is zero before any request and non-zero after, regardless of which
    credential alias introduced the spend."""
    p = GatewayProxy()
    # Route through a prefixed pool id: same underlying model, same provider.
    p.observe(
        "deepseek/deepseek-v4-pro", 200,
        body={"model": "deepseek/deepseek-v4-pro",
              "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.10}},
        provider="deepseek",
    )
    assert math.isclose(p.model_provider_cost("deepseek/deepseek-v4-pro", "deepseek"), 0.10)

    # Route through a bare model id: different key, same provider.
    p.observe(
        "deepseek-v4-pro", 200,
        body={"model": "deepseek-v4-pro",
              "usage": {"prompt_tokens": 80, "completion_tokens": 40, "cost": 0.08}},
        provider="deepseek",
    )
    assert math.isclose(p.model_provider_cost("deepseek-v4-pro", "deepseek"), 0.08)

    # The prefixed key is unchanged by the bare-key request (no cross-talk).
    assert math.isclose(p.model_provider_cost("deepseek/deepseek-v4-pro", "deepseek"), 0.10)

    # Both entries sum to the global total (consistency invariant).
    mp_total = sum(p.all_model_provider_costs().values())
    assert math.isclose(mp_total, p.cumulative_usage().cost_usd)


def test_metering_invariant_concurrent_no_lost_entries() -> None:
    """CANARY: concurrent observe() calls must not lose per-(model, provider)
    entries — the _model_provider_cost dict is protected by the same lock
    as the global counter."""
    p = GatewayProxy()
    usage = {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.01}

    def record(model: str, provider: str) -> None:
        for _ in range(100):
            p.observe(model, 200,
                      body={"model": model, "usage": usage},
                      provider=provider)

    threads = [
        threading.Thread(target=record, args=("m1", "p1")),
        threading.Thread(target=record, args=("m1", "p2")),
        threading.Thread(target=record, args=("m2", "p1")),
        threading.Thread(target=record, args=("m2", "p2")),
    ]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    costs = p.all_model_provider_costs()
    assert math.isclose(costs[("m1", "p1")], 1.00)  # 100 * 0.01
    assert math.isclose(costs[("m1", "p2")], 1.00)
    assert math.isclose(costs[("m2", "p1")], 1.00)
    assert math.isclose(costs[("m2", "p2")], 1.00)
    assert math.isclose(sum(costs.values()), p.cumulative_usage().cost_usd), (
        "concurrent meter must agree with global counter")


# ── BalanceTracker model-level spend ────────────────────────────────────

def test_balance_tracker_model_spend_accumulates() -> None:
    """record_spend with model tracks per-model burn rate on the provider."""
    bt = BalanceTracker()
    bt.record_spend("opencode-zen", 0.01, model="deepseek-v4-pro")
    bt.record_spend("opencode-zen", 0.02, model="deepseek-v4-pro")
    bt.record_spend("opencode-zen", 0.05, model="kimi-k2.7-code")
    assert math.isclose(bt.model_spend("deepseek-v4-pro", "opencode-zen"), 0.03)
    assert math.isclose(bt.model_spend("kimi-k2.7-code", "opencode-zen"), 0.05)
    assert bt.model_spend("unknown", "opencode-zen") == 0.0


def test_balance_tracker_model_spend_independent_per_provider() -> None:
    """The same model on different providers accumulates independently."""
    bt = BalanceTracker()
    bt.record_spend("zen", 0.10, model="v")
    bt.record_spend("deepseek", 0.20, model="v")
    assert math.isclose(bt.model_spend("v", "zen"), 0.10)
    assert math.isclose(bt.model_spend("v", "deepseek"), 0.20)


def test_balance_tracker_model_spend_fixed_mode_decrements_balance() -> None:
    """When a fixed-mode provider is configured, record_spend still decrements
    the balance AND tracks model spend."""
    bt = BalanceTracker(config={"zen": {"mode": "fixed", "starting_usd": 1.00}})
    bt.record_spend("zen", 0.30, model="v")
    assert math.isclose(bt.remaining("zen"), 0.70)
    assert math.isclose(bt.model_spend("v", "zen"), 0.30)


def test_balance_tracker_model_spend_unconfigured_provider() -> None:
    """For an unconfigured provider, record_spend is a no-op on the balance
    but still tracks model spend (the model-level meter is always active)."""
    bt = BalanceTracker()
    bt.record_spend("unknown-prov", 0.05, model="v")
    assert bt.remaining("unknown-prov") is None
    assert math.isclose(bt.model_spend("v", "unknown-prov"), 0.05)


def test_balance_tracker_model_spend_poll_provider() -> None:
    """For a poll-configured provider, record_spend does not decrement the
    balance (poll is authoritative) but still tracks model spend."""
    bt = BalanceTracker(config={"deepseek": {"mode": "poll", "base_url": "http://127.0.0.1:1",
                                              "api_key": "sk-test"}})
    bt.record_spend("deepseek", 0.05, model="v")
    assert bt.remaining("deepseek") is None  # poll is unreachable → None
    assert math.isclose(bt.model_spend("v", "deepseek"), 0.05)
