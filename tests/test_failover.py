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
    select_live_entry,
)
from charon.pools import PoolEntry
from charon.ports.reviewer import ReviewerError
from charon.proxy import GatewayProxy
from charon.router import StaticRouter
from charon.types import Outcome, OutcomeStatus, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _outcome() -> Outcome:
    return Outcome(status=OutcomeStatus.PROGRESSED, provider="mock", commit="abc")

_MODELS = {
    "openrouter/qwen3-coder": {"agent": "opencode", "cost_tier": "free",
                               "cost_rank": 10, "code_safe": False, "free": True},
    "nano-gpt/kimi-k2": {"agent": "opencode", "cost_tier": "flat",
                         "cost_rank": 20, "code_safe": True, "free": False},
    "zen/claude-opus": {"agent": "claude-code", "cost_tier": "premium",
                        "cost_rank": 99, "code_safe": True, "free": False},
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


def test_select_live_entry_skips_rate_limited(tmp_path: Path) -> None:
    # the pre-flight failover: free model 429s on probe, kimi 200 → kimi selected.
    router = _router(tmp_path)
    proxy = GatewayProxy()
    status = {"openrouter/qwen3-coder": 429, "nano-gpt/kimi-k2": 200, "zen/claude-opus": 200}

    def probe(entry: PoolEntry) -> bool:  # simulate driving a request through the proxy
        proxy.observe(entry.model, status[entry.model],
                      body={"model": entry.model} if status[entry.model] == 200 else None)
        return status[entry.model] == 200

    chosen = select_live_entry(router, "coder", proxy, probe)
    assert chosen is not None and chosen.model == "nano-gpt/kimi-k2"


def test_select_live_entry_returns_none_when_all_dead(tmp_path: Path) -> None:
    router = _router(tmp_path)
    proxy = GatewayProxy()

    def probe(entry: PoolEntry) -> bool:
        proxy.observe(entry.model, 429)  # every model rate-limited
        return False

    assert select_live_entry(router, "coder", proxy, probe) is None


def test_select_live_entry_skips_timeout_without_flag(tmp_path: Path) -> None:
    # a probe that times out (returns False WITHOUT the proxy flagging the model)
    # must still be skipped — else the agent gets a dead model (the CLI-hang bug).
    router = _router(tmp_path)
    proxy = GatewayProxy()
    seen: list[str] = []

    def probe(entry: PoolEntry) -> bool:
        seen.append(entry.model)
        return entry.model == "nano-gpt/kimi-k2"  # only the 2nd responds; 1st "times out"

    chosen = select_live_entry(router, "coder", proxy, probe)
    assert chosen is not None and chosen.model == "nano-gpt/kimi-k2"
    assert seen[0] == "openrouter/qwen3-coder"  # the timed-out free model was tried + skipped


# ---------------------------------------------------------------------------
# ReviewerCircuitBreaker tests (T8)
# ---------------------------------------------------------------------------

def test_breaker_passes_through_when_closed() -> None:
    inner = MockReviewer(ReviewMode.PASS)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=60.0)
    result = breaker.review(_unit(), _outcome())
    assert result.passes
    assert breaker.state == "closed"


def test_breaker_opens_after_threshold_errors() -> None:
    inner = MockReviewer(ReviewMode.ERROR)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=60.0)
    for _ in range(3):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "open"
    # subsequent calls fail immediately without hitting the inner reviewer
    calls_before = inner.calls
    with pytest.raises(ReviewerError, match="circuit open"):
        breaker.review(_unit(), _outcome())
    assert inner.calls == calls_before  # inner was NOT called


def test_breaker_does_not_open_before_threshold() -> None:
    inner = MockReviewer(ReviewMode.ERROR)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=60.0)
    for _ in range(2):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "closed"  # still closed — threshold not reached


def test_breaker_half_open_probe_closes_on_success() -> None:
    inner = MockReviewer(ReviewMode.FLAKY, flaky_k=3)
    breaker = ReviewerCircuitBreaker(inner, threshold=3, cooldown_s=0.0)  # instant cooldown
    # trip the breaker
    for _ in range(3):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "open"
    # with cooldown_s=0 the next call transitions to half-open and runs the probe
    # (4th call to inner; inner.flaky_k=3 so it now passes)
    result = breaker.review(_unit(), _outcome())
    assert result.passes
    assert breaker.state == "closed"


def test_breaker_half_open_re_opens_on_failure() -> None:
    inner = MockReviewer(ReviewMode.ERROR)
    breaker = ReviewerCircuitBreaker(inner, threshold=2, cooldown_s=0.0)
    for _ in range(2):
        with pytest.raises(ReviewerError):
            breaker.review(_unit(), _outcome())
    assert breaker.state == "open"
    # cooldown expired → half-open probe fails → re-opens
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
