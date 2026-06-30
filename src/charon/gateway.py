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

from . import providers
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
    model_meta: dict[str, dict] = field(default_factory=dict)


def _route_from_spec(spec: dict, providers_cfg: dict) -> UpstreamRoute | None:
    """One registry entry → UpstreamRoute. A ``provider`` reference (P3) resolves
    base_url/key_env/quirks from a preset (+ ``[providers.<name>]`` overrides); a
    direct ``upstream_base`` entry (P1/P2) still works. Returns None when neither
    yields a base (not HTTP-serveable)."""
    prov = spec.get("provider")
    if prov:
        preset = providers.resolve(prov, providers_cfg.get(prov))
        base: str | None = preset.base_url
        key_env = spec.get("key_env") or preset.key_env
        strip_v1: bool | None = preset.strip_v1
    else:
        base = spec.get("upstream_base")
        if not base:
            return None
        key_env = spec.get("key_env")
        strip_v1 = spec.get("strip_v1")  # explicit only; else server default
    return UpstreamRoute(
        upstream_base=str(base),
        api_key=os.environ.get(key_env) if key_env else None,
        upstream_model=spec.get("upstream_model"),
        provider=prov,
        strip_v1=strip_v1,
    )


def _build_routes_and_pools(
    registry: dict, pool_map: dict, providers_cfg: dict | None = None,
) -> tuple[dict[str, UpstreamRoute], dict[str, list[UpstreamRoute]], list[str]]:
    """Compile a model registry + ``pool_map`` (virtual id → [model id]) into
    single routes (concrete models) and failover chains (virtual ids). Each chain
    is ordered **free-first then cheapest-first** from the registry's cost metadata
    (stable → the listed order breaks ties), matching `pools.load_pools` (D4)."""
    providers_cfg = providers_cfg or {}
    routes: dict[str, UpstreamRoute] = {}
    for mid, spec in registry.items():
        if isinstance(spec, dict):
            r = _route_from_spec(spec, providers_cfg)
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


def _tier_pools(registry: dict, providers_cfg: dict) -> dict[str, list[UpstreamRoute]]:
    """Compile ``tiers.json`` members into failover chains via the SAME
    ``_build_routes_and_pools`` the gateway uses for ``pools.json`` (DTC HARD REQ #2).

    Tiers are read from the separate ``tiers.json`` store (TIER-1 ``config.load_tiers``),
    NOT ``pools.json`` — the strict ``pools.load_pools`` / ACP-router loader must never see
    web-authored tier data (no ``agent`` field → it would crash that path). Members are model
    ids already in ``registry``; each tier vid is ordered free-first→``cost_rank`` by the shared
    compiler. Absent/empty ``tiers.json`` → no member matches → no tier vids (behavior
    unchanged)."""
    from . import config as _config
    members = _config.load_tiers().get("members") or {}
    _, pools, _ = _build_routes_and_pools(registry, members, providers_cfg)
    return pools


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
    providers_cfg: dict = {}

    if toml_path is not None:
        data = tomllib.loads(Path(toml_path).read_text())
        gw = data.get("gateway") or {}
        cfg_host = str(gw.get("host", cfg_host))
        cfg_port = int(gw.get("port", cfg_port))
        cfg_token = gw.get("token")
        registry = data.get("models") or {}
        pool_map = data.get("pools") or {}  # virtual id → ordered [model id]
        providers_cfg = data.get("providers") or {}  # preset overrides (P3)
    elif state_dir is not None:
        models_path = Path(state_dir) / "models.json"
        pools_path = Path(state_dir) / "pools.json"
        providers_path = Path(state_dir) / "providers.json"
        if models_path.exists():
            registry = json.loads(models_path.read_text())
        if pools_path.exists():
            pool_map = json.loads(pools_path.read_text())  # role → [model id]
        if providers_path.exists():
            providers_cfg = json.loads(providers_path.read_text())

    routes, pools, _ = _build_routes_and_pools(registry, pool_map, providers_cfg)
    for vid, chain in _tier_pools(registry, providers_cfg).items():
        pools.setdefault(vid, chain)  # explicit pools.json vid WINS on name collision

    _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio")
    model_meta: dict[str, dict] = {}
    for mid, spec in registry.items():
        if not isinstance(spec, dict) or mid not in routes:
            continue
        meta = {k: spec[k] for k in _META_KEYS if k in spec}
        if meta:
            model_meta[mid] = meta

    return GatewayConfig(
        host=host or cfg_host,
        port=port if port is not None else cfg_port,
        token=token or cfg_token or os.environ.get(_TOKEN_ENV) or None,
        routes=routes,
        pools=pools,
        model_ids=sorted(set(routes) | set(pools)),
        model_meta=model_meta,
    )


def build_server(cfg: GatewayConfig, *, setup_dir: str | Path | None = None) -> GatewayProxyServer:
    """Construct the gateway server. Enforces the loopback/token invariant HERE —
    at bind time — so it holds for ANY caller, not just ``run`` (security review
    MED: ``__init__`` binds the socket, so the guard must precede construction).

    ``setup_dir`` wires the read-WRITE web setup endpoints (write config there +
    hot-reload routes). None keeps the console read-only."""
    if not is_loopback(cfg.host) and not cfg.token:
        raise GatewayBindRefused(
            f"refusing to bind a non-loopback host ({cfg.host}) without a token — "
            f"the gateway holds your provider keys. Set CHARON_GATEWAY_TOKEN / "
            f"--token, or bind 127.0.0.1 for local use (ADR-0005 D5/R8)."
        )
    server = GatewayProxyServer(
        routes=cfg.routes, pools=cfg.pools, host=cfg.host, port=cfg.port,
        token=cfg.token, model_ids=cfg.model_ids, model_meta=cfg.model_meta,
    )
    if setup_dir is not None:
        server.setup_handler = make_setup_handler(server, setup_dir)
    return server


def make_setup_handler(server: GatewayProxyServer, setup_dir: str | Path):
    """A web-setup write handler: ``(action, payload) -> (status, dict)`` that writes
    config to ``setup_dir`` (+ keys to the 0600 secrets file) and hot-reloads the
    running server's routes. Never returns a key. Bad input raises (→ 400 upstream)."""
    from . import config, secrets
    from . import providers as P

    def _reload() -> None:
        secrets.apply_to_env()  # newly-stored keys → env so routes resolve
        new = load_config(state_dir=setup_dir)
        server.apply_routes(new.routes, new.pools, new.model_ids, new.model_meta)

    def handler(action: str, payload: dict):
        if action == "summary":
            s = config.summary()
            s["presets"] = sorted(P.PRESETS)
            return 200, s
        if action == "providers":
            name = str(payload.get("name") or "").strip()
            base_url = payload.get("base_url") or None
            preset = P.resolve(name, {"base_url": base_url} if base_url else None)  # validates
            key_env = (payload.get("key_env") or preset.key_env) or None
            config.add_provider(name, base_url=base_url, key_env=key_env,
                                strip_v1=(preset.strip_v1 if base_url else None))
            key = payload.get("key")
            if key_env and key:
                secrets.set_secret(str(key_env), str(key))
            _reload()
            return 200, {"ok": True, "provider": name}
        if action == "models":
            mid = str(payload.get("id") or "")
            # Preserve existing metadata (context_window, etc.) across re-adds
            # so a web-edit never silently strips model capabilities (MODEL-DISCOVERY).
            existing = config.load_models().get(mid) or {}
            _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio")
            meta = {k: existing[k] for k in _META_KEYS if k in existing}
            config.add_model(
                mid,
                provider=(payload.get("provider") or None),
                upstream_base=(payload.get("upstream_base") or None),
                upstream_model=(payload.get("upstream_model") or None),
                free=bool(payload.get("free")),
                cost_rank=int(payload.get("cost_rank", 1000)),
                **meta,
            )
            _reload()
            return 200, {"ok": True}
        if action == "models/import":
            name = str(payload.get("provider") or "").strip()
            overrides = config.load_providers().get(name)
            preset = P.resolve(name, overrides)  # validates the provider/base
            key_env = (overrides or {}).get("key_env") or preset.key_env
            secrets.apply_to_env()
            api_key = os.environ.get(key_env) if key_env else None
            try:
                found = P.list_models(name, overrides, api_key=api_key)
            except ValueError:
                raise  # bad base → 400 with the validation message
            except Exception as exc:  # network/HTTP/parse → friendly 400, no leak
                raise ValueError(
                    f"could not reach provider {name!r} ({type(exc).__name__})") from exc
            if payload.get("free_only"):
                found = [m for m in found if m["free"]]
            _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio")
            entries = []
            for m in found:
                entry = {"id": m["id"], "free": m["free"],
                         "cost_rank": 0 if m["free"] else 1000}
                for k in _META_KEYS:
                    if k in m:
                        entry[k] = m[k]
                entries.append(entry)
            added, skipped = config.add_models_bulk(entries, provider=name)
            _reload()
            return 200, {"ok": True, "added": len(added), "skipped": len(skipped)}
        if action == "pools":
            config.set_pool(str(payload.get("id") or ""),
                            [str(m) for m in (payload.get("members") or [])])
            _reload()
            return 200, {"ok": True}
        if action == "tiers":
            config.set_tiers(
                payload.get("order") or [],
                payload.get("members") or {},
                payload.get("aliases") or {},
            )
            _reload()  # recompile tier pools into the live server via apply_routes
            return 200, {"ok": True}
        if action == "remove":
            ok = config.remove(str(payload.get("kind")), str(payload.get("name")))
            _reload()
            return 200, {"ok": ok}
        return 400, {"error": {"message": f"unknown action {action!r}"}}

    return handler


def run(cfg: GatewayConfig, *, setup_dir: str | Path | None = None) -> int:
    """Start the gateway and serve until interrupted. ``setup_dir`` enables the
    read-write web setup page (writing config there)."""
    if cfg.token is None and os.environ.get(_TOKEN_ENV) == "":
        print(f"warning: {_TOKEN_ENV} is set but EMPTY — running UNGATED on loopback",
              file=sys.stderr)
    try:
        server = build_server(cfg, setup_dir=setup_dir)
    except GatewayBindRefused as exc:
        print(str(exc), file=sys.stderr)
        return 2
    if not cfg.routes and not cfg.pools:
        print("warning: no models configured — run `charon setup`, "
              "`charon providers add <name>`, or open the setup page below",
              file=sys.stderr)
    gate = "token-gated" if cfg.token else "loopback, UNGATED"
    print(f"charon gateway ({gate}) on {server.url}/v1 — "
          f"{len(cfg.model_ids)} model(s), {len(cfg.pools)} pool(s)", file=sys.stderr)
    tq = f"?token={cfg.token}" if cfg.token else ""
    print(f"  console: {server.url}/{tq}", file=sys.stderr)
    if setup_dir is not None:
        print(f"  setup:   {server.url}/charon/setup{tq}", file=sys.stderr)
    try:
        server.serve_forever()
    except KeyboardInterrupt:  # pragma: no cover
        pass
    finally:
        server.shutdown()
    return 0
