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
from collections.abc import Callable as _Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from . import providers, routing_policy
from .api import _invocation_name
from .cache import SemanticCache
from .consensus import ConsensusRouter
from .guardrails import Guardrails
from .netutil import is_loopback
from .observability import Observability
from .policy_router import PolicyRouter
from .proxy_server import GatewayProxyServer, UpstreamRoute
from .quality_scorer import QualityScorer
from .request_inspector import RequestInspector
from .response_normalizer import ResponseNormalizer
from .routing_policy.catalog_refresh import CatalogRefresher
from .session_affinity import SessionAffinity
from .speculative_execution import SpeculativeExecutor
from .spend_limits import SpendLimiter
from .virtual_keys import VirtualKeyManager

# ── module registry (F29) ─────────────────────────────────────────────────────
# Single source of truth for every Smart-Routing module.  Adding a new module is
# one spec row here + one module file — editing ZERO god-files in gateway.py /
# proxy_server.py bodies.  The loop in _module_inst picks it up automatically.


@dataclass(frozen=True)
class ModuleSpec:
    """One row in the module registry — declarative wiring for a Smart-Routing
    module.  ``name`` is the short id used by ``_module_inst`` and the config-file
    stem; ``attr`` is the backward-compatible public attribute name on
    GatewayConfig / GatewayProxyServer.  ``opt_in`` modules return None unless
    their config file carries ``"enabled": true``."""
    name: str
    attr: str
    factory: _Callable[[dict, Path], Any]
    opt_in: bool = False

    @property
    def config_file(self) -> str:
        return f"{self.name}.json"


_MODULE_SPECS: list[ModuleSpec] = [
    ModuleSpec("cache", "semantic_cache",
               lambda d, sd: SemanticCache(max_size=d.get("max_size", 1000))),
    ModuleSpec("normalizer", "response_normalizer",
               lambda d, sd: ResponseNormalizer()),
    ModuleSpec("guardrails", "guardrails",
               lambda d, sd: Guardrails(config=d if d else {"keywords": []})),
    ModuleSpec("observability", "observability",
               lambda d, sd: Observability(config=d if d else {})),
    ModuleSpec("quality", "quality_scorer",
               lambda d, sd: QualityScorer(state_dir=sd)),
    ModuleSpec("spend", "spend_limiter",
               lambda d, sd: SpendLimiter(
                   monthly_limit_usd=float(d.get("monthly_limit_usd", 0)),
                   state_dir=sd)),
    ModuleSpec("inspector", "request_inspector",
               lambda d, sd: RequestInspector()),
    ModuleSpec("session_affinity", "session_affinity",
               lambda d, sd: SessionAffinity(ttl=float(d.get("ttl", 300)))),
    ModuleSpec("speculative", "speculative_executor",
               lambda d, sd: SpeculativeExecutor(
                   enabled=True, max_providers=int(d.get("max_providers", 3))),
               opt_in=True),
    ModuleSpec("consensus", "consensus_router",
               lambda d, sd: ConsensusRouter(
                   enabled=True, default_count=int(d.get("default_count", 3)),
                   similarity=float(d.get("similarity", 0.8))),
               opt_in=True),
    ModuleSpec("vkeys", "virtual_key_manager",
               lambda d, sd: VirtualKeyManager(state_dir=sd)),
    ModuleSpec("policy", "policy_router",
               lambda d, sd: PolicyRouter(state_dir=sd)),
    # PROVIDER-CATALOG-REFRESH: background model→provider auto-mapping. opt_in
    # (needs catalog_refresh.json {"enabled": true}) — build_server bind()s it to
    # the live server and starts its TTL poll loop (never on the request path).
    ModuleSpec("catalog_refresh", "catalog_refresh",
               lambda d, sd: CatalogRefresher(
                   state_dir=sd,
                   ttl_s=float(d.get("ttl_s", 3600.0))),
               opt_in=True),
]

# ── backward-compatible re-exports (tests import these from gateway) ──────────
_build_routes_and_pools = routing_policy.build_routes_and_pools
_route_from_spec = routing_policy.route_from_spec
_tier_pools = routing_policy.tier_pools

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
    # Per-model per-token pricing (cost_input, cost_output, free) used to compute
    # cost_usd when the provider doesn't self-report it (SR-5b). Never a secret.
    model_pricing: dict[str, dict] = field(default_factory=dict)
    # Operator toggle (SR-2): fail over on a genuine silent downgrade (recording the
    # discarded attempt visibly, count_usage=True) instead of serving it once. Default
    # False keeps the double-bill leak fixed (serve the downgrade, billed once).
    failover_on_downgrade: bool = False
    # Operator toggle (SR-6, default ON): inject one Anthropic prompt-cache breakpoint
    # into the outbound body for Anthropic-wire upstreams (a quality-free input-cost
    # saving). OFF → the body is forwarded byte-identical; OpenAI-wire routes are never
    # touched either way. Plumbed identically to failover_on_downgrade.
    anthropic_prompt_cache: bool = True
    # ── Smart-Routing module instances, keyed by ModuleSpec.attr ─────
    # F29: replaced the ~15 optional module fields with ONE registry-driven dict.
    # Backward-compat attribute access (cfg.guardrails, etc.) → __getattr__ below.
    modules: dict[str, Any] = field(default_factory=dict)
    balance_tracker: Any = None  # BalanceTracker | None (typed as Any to avoid import cycle)

    def __getattr__(self, name: str) -> Any:
        """Backward-compat: cfg.guardrails → self.modules["guardrails"] etc."""
        # Only intercept names that were formerly dataclass fields (module attrs).
        # The ModuleSpec.attr for every row in _MODULE_SPECS is the contract.
        for spec in _MODULE_SPECS:
            if spec.attr == name:
                return self.modules.get(name)
        raise AttributeError(
            f"'{type(self).__name__}' object has no attribute {name!r}")


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
    cfg_failover_on_downgrade: bool = False
    cfg_anthropic_prompt_cache: bool = True
    registry: dict = {}
    pool_map: dict = {}
    providers_cfg: dict = {}

    if toml_path is not None:
        data = tomllib.loads(Path(toml_path).read_text())
        gw = data.get("gateway") or {}
        cfg_host = str(gw.get("host", cfg_host))
        cfg_port = int(gw.get("port", cfg_port))
        cfg_token = gw.get("token")
        cfg_failover_on_downgrade = bool(gw.get("failover_on_downgrade", False))
        cfg_anthropic_prompt_cache = bool(
            gw.get(providers.ANTHROPIC_PROMPT_CACHE_KEY, True))
        registry = data.get("models") or {}
        pool_map = data.get("pools") or {}  # virtual id → ordered [model id]
        providers_cfg = data.get("providers") or {}  # preset overrides (P3)
    elif state_dir is not None:
        models_path = Path(state_dir) / "models.json"
        pools_path = Path(state_dir) / "pools.json"
        providers_path = Path(state_dir) / "providers.json"
        gateway_path = Path(state_dir) / "gateway.json"
        if models_path.exists():
            registry = json.loads(models_path.read_text())
        if pools_path.exists():
            pool_map = json.loads(pools_path.read_text())  # role → [model id]
        if providers_path.exists():
            providers_cfg = json.loads(providers_path.read_text())
        if gateway_path.exists():  # gateway-level flags (SR-2 toggle et al.)
            try:
                gw_file = json.loads(gateway_path.read_text())
                if isinstance(gw_file, dict):
                    cfg_failover_on_downgrade = bool(
                        gw_file.get("failover_on_downgrade", False))
                    cfg_anthropic_prompt_cache = bool(
                        gw_file.get(providers.ANTHROPIC_PROMPT_CACHE_KEY, True))
            except (OSError, json.JSONDecodeError):
                pass

    routes, pools, _ = routing_policy.build_routes_and_pools(registry, pool_map, providers_cfg)
    for vid, chain in routing_policy.tier_pools(registry, providers_cfg).items():
        pools.setdefault(vid, chain)  # explicit pools.json vid WINS on name collision

    # ---- Global fallback providers (Wave 2) ----
    from . import config as _cfg
    fallback_names = _cfg.load_fallback_providers()
    routes, pools = routing_policy.build_fallback_chain(
        routes=routes, pools=pools,
        providers_cfg=providers_cfg, fallback_names=fallback_names)

    _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
                  "cost_class")
    model_meta: dict[str, dict] = {}
    for mid, spec in registry.items():
        if not isinstance(spec, dict) or mid not in routes:
            continue
        meta = {k: spec[k] for k in _META_KEYS if k in spec}
        if meta:
            model_meta[mid] = meta

    # Per-token pricing surfaced to the proxy so it can compute cost_usd when a
    # provider returns a 200 with no cost (SR-5b). Keyed by registry model id;
    # the proxy's lookup also matches on the normalized final segment.
    model_pricing: dict[str, dict] = {}
    for mid, spec in registry.items():
        if not isinstance(spec, dict):
            continue
        price = {k: spec[k] for k in ("cost_input", "cost_output", "free")
                 if k in spec}
        if price:
            model_pricing[mid] = price

    # DRAIN-AND-PARK: construct BalanceTracker from provider configs when any
    # provider carries a balance field (funding_class / mode / starting_balance).
    # AUTO-PARK persistence: same state_dir resolution as every other module
    # (``_module_inst`` below) — explicit state_dir, else secrets.config_dir()
    # (CHARON_HOME) — so the parked set survives a gateway restart. CRITICAL in
    # a container deploy: config_dir() must resolve to the mounted volume, not
    # the ephemeral image FS (charon-deploy-drift-lessons).
    balance_tracker = _build_balance_tracker(providers_cfg, state_dir)

    # F29: instantiate every module via the registry — no per-module wiring needed.
    modules: dict[str, Any] = {}
    for spec in _MODULE_SPECS:
        modules[spec.attr] = _module_inst(spec.name, state_dir)

    return GatewayConfig(
        host=host or cfg_host,
        port=port if port is not None else cfg_port,
        token=token or cfg_token or os.environ.get(_TOKEN_ENV) or None,
        routes=routes,
        pools=pools,
        model_ids=sorted(set(routes) | set(pools)),
        model_meta=model_meta,
        model_pricing=model_pricing,
        failover_on_downgrade=cfg_failover_on_downgrade,
        anthropic_prompt_cache=cfg_anthropic_prompt_cache,
        modules=modules,
        balance_tracker=balance_tracker,
    )


def _build_balance_tracker(
    providers_cfg: dict, state_dir: str | Path | None = None,
) -> Any:
    """Construct a BalanceTracker from provider configs when any provider carries
    balance fields (funding_class, mode, starting_balance).

    Returns None when no provider has balance config — backward-compatible.
    ``state_dir`` resolves exactly like ``_module_inst``: the caller's explicit
    dir, else ``secrets.config_dir()`` (CHARON_HOME) — so the parked-provider
    set is persisted and reloaded across a gateway restart."""
    if not providers_cfg:
        return None
    has_balance = any(
        v.get("funding_class") is not None or v.get("mode") is not None
        for v in providers_cfg.values())
    if not has_balance:
        return None
    from . import secrets
    from .balance import BalanceTracker
    resolved_dir = Path(state_dir) if state_dir is not None else secrets.config_dir()
    return BalanceTracker(config=providers_cfg, state_dir=resolved_dir)


def _module_inst(name: str, state_dir: str | Path | None = None) -> Any:
    """Return a Smart Routing module instance — always active with defaults.

    Reads ``<name>.json`` for operator overrides. Only returns None for
    cost-multiplying features (speculative, consensus) that need explicit opt-in.

    F29: the body is a loop over ``_MODULE_SPECS`` — the single source of truth.
    Adding a new module = one spec row + one module file, editing ZERO god-files.
    """
    from . import secrets
    d = Path(state_dir) if state_dir is not None else secrets.config_dir()

    for spec in _MODULE_SPECS:
        if spec.name != name:
            continue
        cfg_file = d / spec.config_file
        data: dict = {}
        if cfg_file.exists():
            try:
                loaded = json.loads(cfg_file.read_text())
                if isinstance(loaded, dict):
                    data = loaded
            except (OSError, json.JSONDecodeError):
                pass
        if spec.opt_in and not data.get("enabled"):
            return None
        return spec.factory(data, d)
    return None


def _check_failover_safety(cfg: GatewayConfig) -> None:
    """Emit a strong warning when no failover chain is configured — the gateway will
    serve but a single provider exhaustion halts ALL traffic. Common pitfall: models
    are imported but no pools/fallback exist."""
    if cfg.pools:
        return  # at least one pool → failover is wired
    from . import config as _cfg
    has_fallback = bool(_cfg.load_fallback_providers())
    has_pools_file = bool(_cfg.load_pools())
    if has_fallback or has_pools_file:
        return  # configured but no pool chains compiled (e.g., empty members)
    print("warning: NO FAILOVER CHAIN — no pools or global fallback configured. "
          "A single provider exhaustion will stop ALL traffic.",
          file=sys.stderr)
    print(f"  fix: `{_invocation_name()} pools add auto <model,ids,...>` "
          f"or `{_invocation_name()} fallback set <provider-name>` "
          "or open http://127.0.0.1:8080/charon/setup", file=sys.stderr)


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
        model_pricing=cfg.model_pricing,
        failover_on_downgrade=cfg.failover_on_downgrade,
        anthropic_prompt_cache=cfg.anthropic_prompt_cache,
        modules=cfg.modules,
        balance_tracker=cfg.balance_tracker,
    )
    # DRAIN-AND-PARK: wire the observer meter as the spend source for class-3
    # drain-then-park providers (anti-sprawl: one spend source, not two).
    if server.balance_tracker is not None:
        def _observer_spend(provider: str) -> float:
            costs = server.observer.all_model_provider_costs()
            return sum(c for (m, pr), c in costs.items() if pr == provider)

        server.balance_tracker.set_spend_provider_fn(_observer_spend)
    # R3 capability-matrix injection: default deny table (openrouter/novita
    # reasoning-incapable). Optional attribute — forwarder.py reads it via
    # getattr with None fallback so direct-server tests are unaffected.
    server.capability_matrix = routing_policy.CapabilityMatrix()
    # PROVIDER-CATALOG-REFRESH: bind the (opt-in) catalog refresher to the live
    # server and start its background TTL poll. bind() snapshots the static config
    # as the baseline; each refresh BRIDGES discovered models into srv.routes /
    # srv.pools / srv.model_pricing via apply_routes, so a newly-advertised model
    # routes with no hand edit. The poll runs on a daemon thread only — the
    # request path (forward_with_failover) never calls it.
    refresher = cfg.modules.get("catalog_refresh")
    if refresher is not None:
        refresher.bind(server)
        refresher.maybe_start()
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
        server.apply_routes(new.routes, new.pools, new.model_ids, new.model_meta,
                            new.model_pricing)

    def handler(action: str, payload: dict):
        if action == "summary":
            s = config.summary()
            s["presets"] = sorted(P.PRESETS)
            s["fallback"] = config.load_fallback_providers()
            return 200, s
        if action == "providers":
            name = str(payload.get("name") or "").strip()
            base_url = payload.get("base_url") or None
            preset = P.resolve(name, {"base_url": base_url} if base_url else None)  # validates
            key_env = (payload.get("key_env") or preset.key_env) or None
            key = (payload.get("key") or None)
            # Validate the key BEFORE persisting (probe a real completion)
            probe = None
            if key_env and key:
                effective_base = base_url or preset.base_url
                probe = config.validate_provider_key(name, effective_base, str(key))
                if not probe["valid"]:
                    return 400, {"error": {"message": probe["message"]}, "probe": probe}
            config.add_provider(name, base_url=base_url, key_env=key_env,
                                strip_v1=(preset.strip_v1 if base_url else None))
            if key_env and key:
                secrets.set_secret(str(key_env), str(key))
            _reload()
            return 200, {"ok": True, "provider": name, "probe": probe}
        if action == "models":
            mid = str(payload.get("id") or "")
            # Preserve existing metadata (context_window, etc.) across re-adds
            # so a web-edit never silently strips model capabilities (MODEL-DISCOVERY).
            existing = config.load_models().get(mid) or {}
            _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
                          "cost_input", "cost_output", "cost_class")
            meta = {k: existing[k] for k in _META_KEYS if k in existing}
            config.add_model(
                mid,
                provider=(payload.get("provider") or None),
                upstream_base=(payload.get("upstream_base") or None),
                upstream_model=(payload.get("upstream_model") or None),
                free=bool(payload.get("free")),
                cost_rank=payload.get("cost_rank"),
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
            _META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
                          "cost_input", "cost_output", "cost_class")
            entries = []
            for m in found:
                entry: dict[str, object] = {"id": m["id"], "free": m["free"]}
                if m.get("cost_rank") is not None:
                    entry["cost_rank"] = int(m["cost_rank"])
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
        if action == "fallback":
            names = [str(n).strip() for n in (payload.get("providers") or [])
                     if isinstance(n, str) and n.strip()]
            config.set_fallback_providers(names)
            _reload()
            return 200, {"ok": True}
        if action in ("enable", "disable"):
            mid = str(payload.get("id") or "")
            ok = config.set_model_enabled(mid, action == "enable")
            _reload()
            return 200, {"ok": ok}
        if action == "remove":
            ok = config.remove(str(payload.get("kind")), str(payload.get("name")))
            _reload()
            return 200, {"ok": ok}
        if action == "balance":
            prov = str(payload.get("provider") or "").strip()
            op = str(payload.get("op") or "").strip()
            if not prov:
                return 400, {"error": {"message": "provider name required"}}
            bt = getattr(server, "balance_tracker", None)
            if bt is None:
                return 400, {"error": {"message": "balance tracking not configured"}}
            if op == "rearm":
                # Re-arm a parked provider: unpark it. Optionally top up.
                top = payload.get("top_up_usd")
                if top is not None:
                    bt.top_up(prov, float(top))
                bt.unpark(prov)
                return 200, {"ok": True, "provider": prov, "rearmed": True,
                           "remaining": bt.remaining(prov)}
            if op == "park":
                bt.park(prov)
                return 200, {"ok": True, "provider": prov, "parked": True}
            if op == "top_up":
                top = payload.get("amount_usd")
                if top is None:
                    return 400, {"error": {"message": "amount_usd required"}}
                bt.top_up(prov, float(top))
                bt.unpark(prov)
                return 200, {"ok": True, "provider": prov, "top_up_usd": float(top),
                           "remaining": bt.remaining(prov)}
            return 400, {"error": {"message": f"unknown balance op {op!r}"}}
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
    # ── Smart Routing status ─────────────────────────────────────────
    parts: list[str] = []
    if cfg.spend_limiter is not None:
        parts.append(f"spend limit: ${cfg.spend_limiter.remaining():.2f} remaining")
        if cfg.spend_limiter._limit_usd <= 0:
            parts.append("no cap set")
    if cfg.semantic_cache is not None:
        parts.append("cache")
    if cfg.guardrails is not None:
        parts.append("guardrails")
    if cfg.quality_scorer is not None:
        parts.append("quality")
    if cfg.request_inspector is not None:
        parts.append("inspector")
    if parts:
        print(f"Smart Routing: {', '.join(parts)}", file=sys.stderr)
        if cfg.spend_limiter is not None and cfg.spend_limiter._limit_usd <= 0:
            print("  hint: set a spend cap with 'charon limits set --monthly N'",
                  file=sys.stderr)
    if not cfg.routes and not cfg.pools:
        print(f"warning: no models configured — run `{_invocation_name()} setup` or "
              f"`{_invocation_name()} models import <provider>`",
              file=sys.stderr)
    _check_failover_safety(cfg)
    gate = "token-gated" if cfg.token else "loopback, UNGATED"
    print(f"charon gateway ({gate}) on {server.url}/v1 — "
          f"{len(cfg.model_ids)} model(s), {len(cfg.pools)} pool(s)", file=sys.stderr)
    tq = f"?token={cfg.token}" if cfg.token else ""
    if cfg.host in ("127.0.0.1", "localhost", "::1"):
        print(f"  console: {server.url}/{tq} (local only)", file=sys.stderr)
    elif cfg.host == "0.0.0.0":
        import socket
        try:
            lan = socket.gethostbyname(socket.gethostname())
        except OSError:
            lan = "localhost"
        print(f"  console: http://{lan}:{cfg.port}/{tq} (LAN)", file=sys.stderr)
    else:
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
