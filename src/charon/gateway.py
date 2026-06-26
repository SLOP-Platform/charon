"""Standalone gateway mode — ``charon gateway`` (ADR-0005 P1).

A long-lived, loopback OpenAI-compatible gateway any client points at
(``http://127.0.0.1:<port>/v1``). It reuses the existing ``GatewayProxyServer``
(pure stdlib → Windows-native): server-side key holding, SSE pass-through, and
the response observer. P1 forwards each model to its configured upstream and
serves an aggregated ``/v1/models``; **transparent in-request failover is P2**.

Config is one schema over two surfaces (ADR-0005 D6/R5):
- ``charon.toml`` — a ``[gateway]`` table + ``[models."<id>"]`` tables, OR
- the existing ``.charon/models.json`` registry (same field names).

Each model entry needs an ``upstream_base`` (OpenAI-compatible) and optionally a
``key_env`` (the env var holding that upstream's key — injected by the proxy,
never sent to the client) and an ``upstream_model`` (real id if it differs from
the agent-facing id). Entries without an ``upstream_base`` (e.g. pure-ACP
profiles) are skipped — the gateway can only serve HTTP upstreams.
"""
from __future__ import annotations

import json
import os
import sys
import tomllib
from dataclasses import dataclass, field
from pathlib import Path

from .netutil import is_loopback
from .proxy_server import GatewayProxyServer, UpstreamRoute

_DEFAULT_HOST = "127.0.0.1"
_DEFAULT_PORT = 8080
_TOKEN_ENV = "CHARON_GATEWAY_TOKEN"


class GatewayBindRefused(Exception):
    """Raised when a non-loopback bind is requested without a token (D5/R8)."""


@dataclass(frozen=True)
class GatewayConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    token: str | None = None
    routes: dict[str, UpstreamRoute] = field(default_factory=dict)
    pools: dict[str, list[UpstreamRoute]] = field(default_factory=dict)
    model_ids: list[str] = field(default_factory=list)


def _route_from_spec(spec: dict) -> UpstreamRoute | None:
    """One registry entry → UpstreamRoute, resolving ``key_env`` against the env.
    Returns None for entries without an ``upstream_base`` (not HTTP-serveable)."""
    base = spec.get("upstream_base")
    if not base:
        return None
    key_env = spec.get("key_env")
    return UpstreamRoute(
        upstream_base=str(base),
        api_key=os.environ.get(key_env) if key_env else None,
        upstream_model=spec.get("upstream_model"),
    )


def _build_routes_and_pools(
    registry: dict, pool_map: dict,
) -> tuple[dict[str, UpstreamRoute], dict[str, list[UpstreamRoute]], list[str]]:
    """Compile a model registry + ``pool_map`` (virtual id → [model id]) into
    single routes (concrete models) and failover chains (virtual ids). Each chain
    is ordered **free-first then cheapest-first** from the registry's cost metadata
    (stable → the listed order breaks ties), matching `pools.load_pools` (D4)."""
    routes: dict[str, UpstreamRoute] = {}
    for mid, spec in registry.items():
        if isinstance(spec, dict):
            r = _route_from_spec(spec)
            if r is not None:
                routes[mid] = r

    def _rank(mid: str) -> tuple[bool, int]:
        spec = registry.get(mid, {})
        return (not bool(spec.get("free", False)), int(spec.get("cost_rank", 1000)))

    pools: dict[str, list[UpstreamRoute]] = {}
    for vid, members in pool_map.items():
        if not isinstance(members, list):
            continue
        ordered = sorted([m for m in members if m in routes], key=_rank)
        if ordered:
            pools[vid] = [routes[m] for m in ordered]

    return routes, pools, sorted(set(routes) | set(pools))


def load_config(
    *,
    toml_path: str | Path | None = None,
    state_dir: str | Path | None = None,
    host: str | None = None,
    port: int | None = None,
    token: str | None = None,
) -> GatewayConfig:
    """Resolve gateway config. ``toml_path`` wins; else ``state_dir/models.json``.
    Explicit ``host``/``port``/``token`` args override file values; ``token`` also
    falls back to ``$CHARON_GATEWAY_TOKEN``."""
    cfg_host: str = _DEFAULT_HOST
    cfg_port: int = _DEFAULT_PORT
    cfg_token: str | None = None
    registry: dict = {}
    pool_map: dict = {}

    if toml_path is not None:
        data = tomllib.loads(Path(toml_path).read_text())
        gw = data.get("gateway") or {}
        cfg_host = str(gw.get("host", cfg_host))
        cfg_port = int(gw.get("port", cfg_port))
        cfg_token = gw.get("token")
        registry = data.get("models") or {}
        pool_map = data.get("pools") or {}  # virtual id → ordered [model id]
    elif state_dir is not None:
        models_path = Path(state_dir) / "models.json"
        pools_path = Path(state_dir) / "pools.json"
        if models_path.exists():
            registry = json.loads(models_path.read_text())
        if pools_path.exists():
            pool_map = json.loads(pools_path.read_text())  # role → [model id]

    routes, pools, model_ids = _build_routes_and_pools(registry, pool_map)
    return GatewayConfig(
        host=host or cfg_host,
        port=port if port is not None else cfg_port,
        token=token or cfg_token or os.environ.get(_TOKEN_ENV) or None,
        routes=routes,
        pools=pools,
        model_ids=model_ids,
    )


def build_server(cfg: GatewayConfig) -> GatewayProxyServer:
    """Construct the gateway server. Enforces the loopback/token invariant HERE —
    at bind time — so it holds for ANY caller, not just ``run`` (security review
    MED: ``__init__`` binds the socket, so the guard must precede construction)."""
    if not is_loopback(cfg.host) and not cfg.token:
        raise GatewayBindRefused(
            f"refusing to bind a non-loopback host ({cfg.host}) without a token — "
            f"the gateway holds your provider keys. Set CHARON_GATEWAY_TOKEN / "
            f"--token, or bind 127.0.0.1 for local use (ADR-0005 D5/R8)."
        )
    return GatewayProxyServer(
        routes=cfg.routes, pools=cfg.pools, host=cfg.host, port=cfg.port,
        token=cfg.token, model_ids=cfg.model_ids,
    )


def run(cfg: GatewayConfig) -> int:
    """Start the gateway and serve until interrupted."""
    if cfg.token is None and os.environ.get(_TOKEN_ENV) == "":
        print(f"warning: {_TOKEN_ENV} is set but EMPTY — running UNGATED on loopback",
              file=sys.stderr)
    try:
        server = build_server(cfg)
    except GatewayBindRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not cfg.routes and not cfg.pools:
        print("warning: no models configured (need a charon.toml or "
              ".charon/models.json with upstream_base entries)", file=sys.stderr)
    gate = "token-gated" if cfg.token else "loopback, UNGATED"
    print(f"charon gateway ({gate}) on {server.url}/v1 — "
          f"{len(cfg.model_ids)} model(s), {len(cfg.pools)} pool(s)", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.shutdown()
    return 0
