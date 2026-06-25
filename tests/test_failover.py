"""MVP #3 — router + proxy failover, end-to-end (ADR-0004).

Proves the operator's headline behaviour without a live agent: the primary model
runs until the gateway says 429 (or silently downgrades), then the role
automatically moves to the next cheapest live model in its pool — no waiting,
no reconfiguration.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.failover import next_entry, proxy_excluded_keys, select_live_entry
from charon.pools import PoolEntry
from charon.proxy import GatewayProxy
from charon.router import StaticRouter

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

    def probe(entry: PoolEntry) -> None:  # simulate driving a request through the proxy
        proxy.observe(entry.model, status[entry.model],
                      body={"model": entry.model} if status[entry.model] == 200 else None)

    chosen = select_live_entry(router, "coder", proxy, probe)
    assert chosen is not None and chosen.model == "nano-gpt/kimi-k2"


def test_select_live_entry_returns_none_when_all_dead(tmp_path: Path) -> None:
    router = _router(tmp_path)
    proxy = GatewayProxy()

    def probe(entry: PoolEntry) -> None:
        proxy.observe(entry.model, 429)  # every model rate-limited

    assert select_live_entry(router, "coder", proxy, probe) is None
