"""MVP #3 — router + proxy failover, end-to-end (ADR-0004).

Proves the operator's headline behaviour without a live agent: the primary model
runs until the gateway says 429 (or silently downgrades), then the role
automatically moves to the next cheapest live model in its pool — no waiting,
no reconfiguration.

Also covers ReviewerCircuitBreaker state transitions (T8).
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.adapters.review_mock import MockReviewer, ReviewMode
from charon.failover import (
    ReviewerCircuitBreaker,
    next_entry,
    proxy_excluded_keys,
)
from charon.ports.reviewer import ReviewerError
from charon.proxy import GatewayProxy
from charon.router import StaticRouter
from charon.types import Outcome, OutcomeStatus, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _outcome() -> Outcome:
    return Outcome(status=OutcomeStatus.PROGRESSED, provider="mock", commit="abc")

_MODELS = {
    # DELETE-STATIC-RANK (ADR-0016 step #6): ordering is derived from
    # cost_input/cost_output (SR-6), not a hand-typed cost_rank integer.  The
    # pricing below yields the same cheap→dear ordering the old hand-typed
    # cost_rank integers did.
    "openrouter/qwen3-coder": {"agent": "opencode", "cost_tier": "free",
                               "code_safe": False, "free": True},
    "nano-gpt/kimi-k2": {"agent": "opencode", "cost_tier": "flat",
                         "cost_input": 0.0000001, "cost_output": 0.0000001,
                         "code_safe": True, "free": False},
    "zen/claude-opus": {"agent": "claude-code", "cost_tier": "premium",
                        "cost_input": 0.000001, "cost_output": 0.000003,
                        "code_safe": True, "free": False},
}
_POOLS = {"coder": ["openrouter/qwen3-coder", "nano-gpt/kimi-k2", "zen/claude-opus"]}


def _router(tmp_path: Path) -> StaticRouter:
    (tmp_path / "models.json").write_text(json.dumps(_MODELS))
    (tmp_path / "pools.json").write_text(json.dumps(_POOLS))
    return StaticRouter.from_charon_dir(tmp_path)


def test_429_on_primary_fails_over_to_next(tmp_path: Path) -> None:
    router = _router(tmp_path)
    proxy = GatewayProxy()
    # before any exhaustion, the free model is chosen
    assert next_entry(router, "coder", proxy).model == "openrouter/qwen3-coder"
    # the gateway rate-limits the free model...
    proxy.observe("openrouter/qwen3-coder", 429, headers={"Retry-After": "60"})
    # ...so the role now routes to the next cheapest live model — automatically
    assert next_entry(router, "coder", proxy).model == "nano-gpt/kimi-k2"


def test_silent_downgrade_also_fails_over(tmp_path: Path) -> None:
    router = _router(tmp_path)
    proxy = GatewayProxy()
    # a 200 that served a different (free) model than requested = pseudo-success
    proxy.observe("nano-gpt/kimi-k2", 200, body={"model": "some-free-model"})
    excl = proxy_excluded_keys(router.pools["coder"], proxy)
    assert "opencode:nano-gpt/kimi-k2" in excl


def test_failover_chains_until_pool_dry(tmp_path: Path) -> None:
    router = _router(tmp_path)
    proxy = GatewayProxy()
    proxy.observe("openrouter/qwen3-coder", 429)
    proxy.observe("nano-gpt/kimi-k2", 402)
    assert next_entry(router, "coder", proxy).model == "zen/claude-opus"  # premium tail
    proxy.observe("zen/claude-opus", 503)
    with pytest.raises(RuntimeError, match="pool exhausted"):
        next_entry(router, "coder", proxy)


def test_code_safe_only_with_proxy(tmp_path: Path) -> None:
    # free model is not code_safe; with code_safe_only it's skipped from the start
    router = _router(tmp_path)
    proxy = GatewayProxy()
    assert next_entry(router, "coder", proxy, code_safe_only=True).model == "nano-gpt/kimi-k2"


# NOTE (ADR-0014 D6, Phase B): the ``select_live_entry`` pre-flight pool-probe
# tests were retired with the function — tier routing now drives the LIVE gateway
# path (the in-request failover proven by tests/test_gateway_failover.py) instead
# of the engine probing models itself.


# ---------------------------------------------------------------------------
# ReviewerCircuitBreaker tests (T8)
# ---------------------------------------------------------------------------

def test_breaker_passes_through_when_closed() -> None:
    inner = MockReviewer(ReviewMode.PASS)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=60.0)
    result = breaker.review(_unit(), _outcome())
    assert result.passes
    assert breaker.state == "closed"


@pytest.mark.parametrize(
    "num_errors,threshold,expected_state",
    [(3, 3, "open"), (2, 3, "closed")],
)
def test_breaker_opens_at_threshold(
    num_errors: int, threshold: int, expected_state: str
) -> None:
    inner = MockReviewer(ReviewMode.ERROR)
    breaker = ReviewerCircuitBreaker(inner, threshold=threshold, cooldown_s=60.0)
    for _ in range(num_errors):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == expected_state
    if expected_state == "open":
        calls_before = inner.calls
        with pytest.raises(ReviewerError, match="circuit open"):
            breaker.review(_unit(), _outcome())
        assert inner.calls == calls_before


@pytest.mark.parametrize(
    "mode,threshold,probe_passes",
    [(ReviewMode.FLAKY, 3, True), (ReviewMode.ERROR, 2, False)],
)
def test_breaker_half_open_probe(
    mode: ReviewMode, threshold: int, probe_passes: bool
) -> None:
    if mode == ReviewMode.FLAKY:
        inner = MockReviewer(mode, flaky_k=threshold)
    else:
        inner = MockReviewer(mode)
    breaker = ReviewerCircuitBreaker(inner, threshold=threshold, cooldown_s=0.0)
    for _ in range(threshold):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "open"
    if probe_passes:
        result = breaker.review(_unit(), _outcome())
        assert result.passes
        assert breaker.state == "closed"
    else:
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
        assert breaker.state == "open"


def test_breaker_resets_failure_count_on_success() -> None:
    # two errors then a success → count resets; need threshold more errors to open again
    inner = MockReviewer(ReviewMode.FLAKY, flaky_k=2)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=60.0)
    for _ in range(2):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "closed"  # not yet at threshold
    result = breaker.review(_unit(), _outcome())
    assert result.passes
    assert breaker.state == "closed"
    # consecutive_failures reset: one more error doesn't open
    inner.mode = ReviewMode.ERROR
    with pytest.raises(ReviewerError):
        breaker.review(_unit(), _outcome())
    assert breaker.state == "closed"


def test_breaker_block_verdict_does_not_count_as_failure() -> None:
    # a BLOCK is a valid verdict (not an error); consecutive_failures should not increment
    inner = MockReviewer(ReviewMode.BLOCK)
    breaker = ReviewerCircuitBreaker(inner, threshold=2, cooldown_s=60.0)
    for _ in range(5):
        result = breaker.review(_unit(), _outcome())
        assert not result.passes  # blocking findings present
    assert breaker.state == "closed"  # never tripped
