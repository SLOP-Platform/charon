from __future__ import annotations

from pathlib import Path

from charon.policy_router import PolicyRouter, PolicyType
from charon.proxy_server import UpstreamRoute


def _make_route(base: str) -> UpstreamRoute:
    return UpstreamRoute(upstream_base=base, provider=base)


def test_resolve_fallback_policy_returns_chain(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    router = PolicyRouter()
    router.create_policy("cheap-fast", PolicyType.FALLBACK, ["openai", "together"])
    routes = {"openai": _make_route("https://api.openai.com"),
              "together": _make_route("https://api.together.xyz")}
    chain = router.resolve("cheap-fast", routes, {})
    assert len(chain) == 2
    assert chain[0].upstream_base == "https://api.openai.com"
    assert chain[1].upstream_base == "https://api.together.xyz"


def test_resolve_unknown_policy_returns_empty(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    router = PolicyRouter()
    assert router.resolve("nonexistent", {}, {}) == []


def test_list_policies(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    router = PolicyRouter()
    router.create_policy("p1", PolicyType.LOAD_BALANCE, ["a", "b"])
    router.create_policy("p2", PolicyType.LATENCY, ["c"])
    policies = router.list_policies()
    assert "p1" in policies
    assert "p2" in policies
    assert policies["p1"]["type"] == "load_balance"
    assert policies["p2"]["type"] == "latency"


def test_resolve_load_balance_policy(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    router = PolicyRouter()
    router.create_policy("lb", PolicyType.LOAD_BALANCE, ["a", "b", "c"])
    routes = {k: _make_route(f"https://{k}.com") for k in ["a", "b", "c"]}
    chain = router.resolve("lb", routes, {})
    assert len(chain) == 3


def test_resolve_with_pool_members(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    router = PolicyRouter()
    router.create_policy("pooled", PolicyType.FALLBACK, ["auto"])
    routes: dict = {}
    pools = {"auto": [_make_route("https://a.com"), _make_route("https://b.com")]}
    chain = router.resolve("pooled", routes, pools)
    assert len(chain) == 2


def test_persistence_survives_reload(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    r1 = PolicyRouter()
    r1.create_policy("saved", PolicyType.FALLBACK, ["x"])
    r2 = PolicyRouter()
    assert "saved" in r2.list_policies()
