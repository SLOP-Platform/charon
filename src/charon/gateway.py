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


@dataclass(frozen=True)
class GatewayConfig:
    host: str = _DEFAULT_HOST
    port: int = _DEFAULT_PORT
    token: str | None = None
    routes: dict[str, UpstreamRoute] = field(default_factory=dict)
    model_ids: list[str] = field(default_factory=list)


def _routes_from_registry(registry: dict) -> tuple[dict[str, UpstreamRoute], list[str]]:
    """Build agent-facing-id → UpstreamRoute from a model registry, resolving each
    ``key_env`` against the environment. Models without an ``upstream_base`` are
    skipped (not HTTP-serveable). The same shape backs both config surfaces."""
    routes: dict[str, UpstreamRoute] = {}
    for mid, spec in registry.items():
        if not isinstance(spec, dict):
            continue
        base = spec.get("upstream_base")
        if not base:
            continue
        key_env = spec.get("key_env")
        routes[mid] = UpstreamRoute(
            upstream_base=str(base),
            api_key=os.environ.get(key_env) if key_env else None,
            upstream_model=spec.get("upstream_model"),
        )
    return routes, sorted(routes)


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

    if toml_path is not None:
        data = tomllib.loads(Path(toml_path).read_text())
        gw = data.get("gateway") or {}
        cfg_host = str(gw.get("host", cfg_host))
        cfg_port = int(gw.get("port", cfg_port))
        cfg_token = gw.get("token")
        registry = data.get("models") or {}
    elif state_dir is not None:
        models_path = Path(state_dir) / "models.json"
        if models_path.exists():
            registry = json.loads(models_path.read_text())

    routes, model_ids = _routes_from_registry(registry)
    return GatewayConfig(
        host=host or cfg_host,
        port=port if port is not None else cfg_port,
        token=token or cfg_token or os.environ.get(_TOKEN_ENV) or None,
        routes=routes,
        model_ids=model_ids,
    )


def build_server(cfg: GatewayConfig) -> GatewayProxyServer:
    """Construct (do not start) the gateway server from config."""
    return GatewayProxyServer(
        routes=cfg.routes, host=cfg.host, port=cfg.port,
        token=cfg.token, model_ids=cfg.model_ids,
    )


def run(cfg: GatewayConfig) -> int:
    """Start the gateway and serve until interrupted. Refuses a non-loopback bind
    without a token (the gateway holds provider keys — an exposed untokened bind
    is open credit; ADR-0005 D5/R8)."""
    if not is_loopback(cfg.host) and not cfg.token:
        print(
            f"refusing to bind a non-loopback host ({cfg.host}) without a token — "
            f"the gateway holds your provider keys. Set CHARON_GATEWAY_TOKEN / "
            f"--token, or bind 127.0.0.1 for local use (ADR-0005 D5/R8).",
            file=sys.stderr,
        )
        return 2
    if not cfg.routes:
        print("warning: no models configured (need a charon.toml or "
              ".charon/models.json with upstream_base entries)", file=sys.stderr)
    server = build_server(cfg)
    gate = "token-gated" if cfg.token else "loopback, UNGATED"
    print(f"charon gateway ({gate}) on {server.url}/v1 — {len(cfg.routes)} model(s)",
          file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.shutdown()
    return 0
