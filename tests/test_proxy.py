"""MVP #2 — observing gateway proxy core (ADR-0004 R1).

Proves the linchpin signal: turning a gateway response into exhaustion / silent-
downgrade / cost — the thing Charon can't otherwise see because the agent (not
Charon) talks to the gateway. Pure observation logic; no real network.
"""
from __future__ import annotations

from charon.proxy import GatewayProxy


def test_429_is_exhaustion_with_retry_after() -> None:
    p = GatewayProxy()
    obs = p.observe("openrouter/qwen3-coder", 429,
                    headers={"Retry-After": "30"},
                    body={"error": {"metadata": {"error_type": "rate_limit_exceeded"}}})
    assert obs.exhausted and obs.failover
    assert obs.retry_after == 30
    assert "rate_limit_exceeded" in obs.note
    assert p.is_exhausted("openrouter/qwen3-coder")
    assert p.exhausted_models() == {"openrouter/qwen3-coder"}


def test_402_payment_required_is_exhaustion() -> None:
    p = GatewayProxy()
    obs = p.observe("nano-gpt/kimi-k2", 402, body={"error": {"code": "payment_required"}})
    assert obs.exhausted and obs.failover


def test_200_model_match_records_usage_no_failover() -> None:
    p = GatewayProxy()
    obs = p.observe("openrouter/qwen3-coder", 200,
                    body={"model": "openrouter/qwen3-coder",
                          "usage": {"prompt_tokens": 100, "completion_tokens": 50, "cost": 0.002}})
    assert not obs.failover and not obs.exhausted and not obs.pseudo_success
    assert obs.usage is not None and obs.usage.tokens == 150
    assert p.cumulative_usage().cost_usd == 0.002
    assert p.exhausted_models() == set()


def test_silent_downgrade_is_pseudo_success_failover() -> None:
    # asked for a flat paid model, gateway silently served a free one → must fail over.
    p = GatewayProxy()
    obs = p.observe("opencode-go/glm-5.2", 200,
                    body={"model": "glm-free", "usage": {"prompt_tokens": 10}})
    assert obs.pseudo_success and obs.failover and not obs.exhausted
    assert "silent downgrade" in obs.note
    assert p.is_exhausted("opencode-go/glm-5.2")  # excluded on next route


def test_cumulative_usage_sums_across_calls() -> None:
    p = GatewayProxy()
    usage = {"prompt_tokens": 10, "completion_tokens": 5, "cost": 0.5}
    for _ in range(3):
        p.observe("m", 200, body={"model": "m", "usage": usage})
    u = p.cumulative_usage()
    assert u.tokens_in == 30 and u.tokens_out == 15 and u.cost_usd == 1.5


def test_503_overload_is_exhaustion() -> None:
    p = GatewayProxy()
    assert p.observe("m", 503).failover


def test_404_drops_model_from_pool() -> None:
    # free rosters churn: 404 = "unavailable for free" = drop, not retry (R6).
    p = GatewayProxy()
    obs = p.observe("openrouter/deepseek:free", 404, body={"error": {"message": "unavailable"}})
    assert obs.dropped and obs.failover and not obs.exhausted
    assert p.is_exhausted("openrouter/deepseek:free")
    assert "dropped" in obs.note


def test_take_delta_returns_increment() -> None:
    p = GatewayProxy()
    p.observe("m", 200, body={"model": "m", "usage": {"prompt_tokens": 10, "completion_tokens": 5}})
    d1 = p.take_delta()
    assert d1.tokens == 15
    p.observe("m", 200, body={"model": "m", "usage": {"prompt_tokens": 4, "completion_tokens": 1}})
    d2 = p.take_delta()
    assert d2.tokens == 5  # only the new increment
    assert p.take_delta().tokens == 0  # nothing new


def test_concurrent_observe_loses_no_usage() -> None:
    # the proxy server is threaded; observe() must be atomic (review #1).
    import threading
    p = GatewayProxy()
    usage = {"prompt_tokens": 1, "completion_tokens": 1}

    def hammer() -> None:
        for _ in range(200):
            p.observe("m", 200, body={"model": "m", "usage": usage})

    threads = [threading.Thread(target=hammer) for _ in range(8)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    # 8 threads × 200 calls × 2 tokens = 3200, none lost to a race
    assert p.cumulative_usage().tokens == 3200
