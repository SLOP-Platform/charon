"""Tier-5/MVP — role → model-pool routing (ADR-0004 D4/R2).

Proves the operator's core policy as DATA: free-first, cheapest-first, with
cross-model failover by excluding the exhausted entry (H6), code-safe filtering,
and loud config errors. No live model needed — pure routing logic.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from charon.pools import PoolConfigError, choose_from_pool, load_pools
from charon.router import StaticRouter

_MODELS = {
    # DELETE-STATIC-RANK (ADR-0016 step #6): ordering is derived from
    # cost_input/cost_output (SR-6), not a hand-typed cost_rank integer.  The
    # pricing values below yield the same cheap→dear sort the old hand-typed
    # cost_rank integers did, so the pool contract tests remain valid.
    "openrouter/qwen3-coder": {"agent": "opencode", "cost_tier": "free",
                               "code_safe": False, "free": True},
    "nano-gpt/kimi-k2": {"agent": "opencode", "cost_tier": "flat",
                         "cost_input": 0.0000001, "cost_output": 0.0000001,
                         "code_safe": True, "free": False},
    "opencode-go/glm": {"agent": "opencode", "cost_tier": "flat",
                        "cost_input": 0.0000003, "cost_output": 0.0000003,
                        "code_safe": True, "free": False},
    "zen/claude-opus": {"agent": "claude-code", "cost_tier": "premium",
                        "cost_input": 0.000001, "cost_output": 0.000003,
                        "code_safe": True, "free": False},
}
_POOLS = {"coder": ["zen/claude-opus", "openrouter/qwen3-coder",  # deliberately mis-ordered
                    "opencode-go/glm", "nano-gpt/kimi-k2"]}


def _write_config(state_dir: Path, models=None, pools=None) -> None:
    (state_dir / "models.json").write_text(json.dumps(models if models is not None else _MODELS))
    (state_dir / "pools.json").write_text(json.dumps(pools if pools is not None else _POOLS))


def test_pool_is_sorted_free_first_then_cost(tmp_path: Path) -> None:
    _write_config(tmp_path)
    pools = load_pools(tmp_path)
    order = [e.model for e in pools["coder"]]
    # free (qwen) first despite being authored 2nd; then flat by cost_rank; premium last.
    assert order == ["openrouter/qwen3-coder", "nano-gpt/kimi-k2",
                     "opencode-go/glm", "zen/claude-opus"]


def test_failover_walks_the_pool_excluding_exhausted(tmp_path: Path) -> None:
    _write_config(tmp_path)
    pool = load_pools(tmp_path)["coder"]
    first = choose_from_pool(pool)
    assert first.model == "openrouter/qwen3-coder"  # free wins
    # exhaust the free one → next cheapest (H6)
    second = choose_from_pool(pool, exclude={first.key})
    assert second.model == "nano-gpt/kimi-k2"
    third = choose_from_pool(pool, exclude={first.key, second.key})
    assert third.model == "opencode-go/glm"


def test_pool_exhausted_raises_clean(tmp_path: Path) -> None:
    _write_config(tmp_path)
    pool = load_pools(tmp_path)["coder"]
    allkeys = {e.key for e in pool}
    with pytest.raises(RuntimeError, match="pool exhausted"):
        choose_from_pool(pool, exclude=allkeys)


def test_code_safe_only_skips_unsafe(tmp_path: Path) -> None:
    # the free model is NOT code_safe → with code_safe_only it must be skipped
    _write_config(tmp_path)
    pool = load_pools(tmp_path)["coder"]
    choice = choose_from_pool(pool, code_safe_only=True)
    assert choice.model == "nano-gpt/kimi-k2"  # first code-safe one
    assert choice.code_safe is True


def test_router_route_pool(tmp_path: Path) -> None:
    _write_config(tmp_path)
    router = StaticRouter.from_charon_dir(tmp_path)
    # backends derived from the agents in the pools
    assert set(router.backends) == {"opencode", "claude-code"}
    entry = router.route_pool("coder")
    assert entry.model == "openrouter/qwen3-coder"
    nxt = router.route_pool("coder", exclude={entry.key})
    assert nxt.model == "nano-gpt/kimi-k2"


def test_unknown_role_raises(tmp_path: Path) -> None:
    _write_config(tmp_path)
    router = StaticRouter.from_charon_dir(tmp_path)
    with pytest.raises(RuntimeError, match="no pool configured"):
        router.route_pool("planner")


def test_pool_naming_unknown_model_is_loud(tmp_path: Path) -> None:
    _write_config(tmp_path, pools={"coder": ["nonesuch/model"]})
    with pytest.raises(PoolConfigError, match="not in models.json"):
        load_pools(tmp_path)


def test_no_config_returns_empty(tmp_path: Path) -> None:
    assert load_pools(tmp_path) == {}  # absent config → empty, not error


def test_backward_compat_task_class_route_unaffected() -> None:
    # the legacy task_class route path must be unchanged (66 existing tests).
    r = StaticRouter(backends=["a", "b"])
    assert r.route("codegen").backend == "a"
    assert r.route("codegen", exclude={"a"}).backend == "b"
