"""PROVIDER-CATALOG-REFRESH — scheduled, off-hot-path auto-mapping of
models → providers for the gateway router.

Today a model only becomes routable after an operator HAND-MAPS it into the
config (Phi-4/GLM-4.7/Gemini-2.5 this session). This module removes that step:
a BACKGROUND job polls every configured provider's OpenAI-compatible
``GET /models`` on a TTL, writes a LOCAL catalog cache
(normalized model-id → [providers serving it] + per-(provider,model) price), and
BRIDGES that cache straight into the live router via
``GatewayProxyServer.apply_routes`` — the exact ``routes``/``pools``/
``model_pricing`` that ``chain_for`` and ``order_pool_by_live_cost`` read. A
freshly-discovered ``(provider, model)`` therefore routes with **zero manual
mapping** on the next refresh.

Hard constraints (why PRICE-REFRESHER was rejected — do NOT repeat):
  * WIRED, not a library: registered in ``gateway._MODULE_SPECS`` and its cache
    bridged onto ``srv.routes``/``srv.pools``/``srv.model_pricing`` via
    ``apply_routes`` (see :meth:`CatalogRefresher.bridge` — the bridge site).
  * OFF THE HOT PATH: the poll runs only on the TTL background thread / an
    explicit call. ``forward_with_failover`` NEVER calls it; routing reads the
    already-bridged cache only.
  * STALE-BUT-USABLE: a provider poll that fails logs a red and keeps that
    provider's last-good entries — a refresh error never empties the catalog and
    never blocks routing.

Precedence: the meter-observed per-(model,provider) cost still SUPERSEDES the
quoted price once traffic exists — this module only feeds the *quote* into
``model_pricing``; ``order_pool_by_live_cost`` overrides it with live metered
cost via ``derived_cost_rank(..., metered_cost=...)``.
"""
from __future__ import annotations

import json
import logging
import os
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from charon import providers as _providers_mod

if TYPE_CHECKING:  # annotation-only — avoid importing the server at module load
    from charon.proxy_server import GatewayProxyServer

log = logging.getLogger("charon.catalog_refresh")

# A provider poller: (provider_name, overrides) -> [{"id", "free", "cost_input"?, ...}].
# Injectable so tests drive an honest mock provider without real network.
ListModelsFn = Callable[[str, "dict | None"], list[dict]]

# Fields carried from a /models entry into the routing registry.
_PRICE_KEYS = ("cost_input", "cost_output", "free")
_META_KEYS = ("context_window", "max_tokens", "reasoning", "vision", "audio",
              "cost_class")

_DEFAULT_TTL_S = 3600.0


def _normalize(raw: str) -> str:
    """Cross-provider model identity: reuse the router's own id normalization
    (final path segment, lower-cased, quant-suffix stripped) so
    ``openai/gpt-4o`` (OpenRouter) and bare ``gpt-4o`` (a direct provider) pool
    under one routable id — the same folding the downgrade-detector uses, so the
    catalog and the router never disagree on what "the same model" is."""
    from charon.proxy import _normalize_model_id
    return _normalize_model_id(raw)


def _default_list_models(name: str, overrides: dict | None) -> list[dict]:
    """Poll one provider's ``GET /models`` using the shared, SSRF-guarded
    ``providers.list_models`` (never a bespoke fetcher). The provider key is read
    from its resolved ``key_env`` in the process env (populated by
    ``secrets.apply_to_env`` in the running gateway)."""
    preset = _providers_mod.resolve(name, overrides)
    key_env = (overrides or {}).get("key_env") or preset.key_env
    api_key = os.environ.get(key_env) if key_env else None
    return _providers_mod.list_models(name, overrides, api_key=api_key)


@dataclass
class ProviderEntry:
    """One provider's offer of one model, as discovered from its /models."""
    provider: str
    upstream_model: str          # the raw id the provider advertises
    price: dict[str, Any] = field(default_factory=dict)   # cost_input/cost_output/free
    meta: dict[str, Any] = field(default_factory=dict)    # context_window, ...


@dataclass
class CatalogCache:
    """Last-good discovered catalog, keyed per provider so a single provider's
    failed poll degrades to STALE-BUT-USABLE (its prior entries are retained).

    ``per_provider[provider]`` maps a unique member id (``"<provider>/<raw>"``)
    to its :class:`ProviderEntry`."""
    per_provider: dict[str, dict[str, ProviderEntry]] = field(default_factory=dict)
    updated: dict[str, float] = field(default_factory=dict)  # provider -> last-success ts

    def put(self, provider: str, entries: dict[str, ProviderEntry]) -> None:
        self.per_provider[provider] = entries
        self.updated[provider] = time.time()

    def registry_and_pool_map(self) -> tuple[dict[str, dict], dict[str, list[str]]]:
        """Compile the cache into the ``(registry, pool_map)`` pair that
        ``build_routes_and_pools`` consumes.

        * registry: member id → spec (provider + upstream_model + price + meta).
        * pool_map: routable id → [member ids]. Each member is exposed under BOTH
          its normalized id (cross-provider pool) and its raw advertised id (so an
          exact-id request also routes); when they coincide the keys merge."""
        registry: dict[str, dict] = {}
        pool_map: dict[str, list[str]] = {}
        for provider, members in sorted(self.per_provider.items()):
            for member_id, e in members.items():
                spec: dict[str, Any] = {"provider": provider,
                                        "upstream_model": e.upstream_model}
                spec.update(e.price)
                spec.update(e.meta)
                registry[member_id] = spec
                for key in {_normalize(e.upstream_model), e.upstream_model}:
                    bucket = pool_map.setdefault(key, [])
                    if member_id not in bucket:
                        bucket.append(member_id)
        return registry, pool_map


class CatalogRefresher:
    """Background model→provider catalog refresher (see module docstring).

    Construction is side-effect-free (no network, no thread). Discovery happens
    only in :meth:`refresh_now` / the :meth:`start` TTL loop; the router reads the
    result only after :meth:`bridge` has merged it via ``apply_routes``.
    """

    def __init__(
        self,
        *,
        providers_cfg: dict | None = None,
        state_dir: str | Path | None = None,
        ttl_s: float = _DEFAULT_TTL_S,
        list_models_fn: ListModelsFn | None = None,
    ) -> None:
        self._providers_cfg: dict = (
            providers_cfg if providers_cfg is not None
            else _load_providers(state_dir))
        self.ttl_s = float(ttl_s)
        self._list_models: ListModelsFn = list_models_fn or _default_list_models
        self.cache = CatalogCache()
        # Number of provider polls attempted — a test asserts this stays 0 across
        # a forward_with_failover call (the off-hot-path guard).
        self.poll_count = 0
        self._lock = threading.Lock()
        self._server: GatewayProxyServer | None = None
        # Static config snapshot captured at bind(): discovered entries are always
        # layered ON TOP of this baseline so a refresh never clobbers hand config.
        self._base: tuple[dict, dict, dict, dict] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()

    # ── discovery (background / on-demand only — NEVER on the hot path) ──────
    def refresh_now(self) -> None:
        """Poll every configured provider's ``/models`` and update the cache.

        A provider whose poll raises is logged as a red and SKIPPED — its
        last-good entries stay in the cache (stale-but-usable). Never raises."""
        for name, cfg in self._providers_cfg.items():
            overrides = cfg if isinstance(cfg, dict) else None
            self.poll_count += 1
            try:
                found = self._list_models(name, overrides)
            except Exception as exc:  # noqa: BLE001 — degrade, never block routing
                log.error(
                    "catalog refresh: provider %r /models poll failed "
                    "(%s: %s) — keeping last-good entries (stale-but-usable)",
                    name, type(exc).__name__, exc)
                continue
            entries: dict[str, ProviderEntry] = {}
            for m in found:
                raw = m.get("id") if isinstance(m, dict) else None
                if not isinstance(raw, str) or not raw:
                    continue
                member_id = f"{name}/{raw}"
                price = {k: m[k] for k in _PRICE_KEYS if k in m}
                meta = {k: m[k] for k in _META_KEYS if k in m}
                entries[member_id] = ProviderEntry(name, raw, price, meta)
            with self._lock:
                self.cache.put(name, entries)

    # ── the WIRE: cache → live router ───────────────────────────────────────
    def bind(self, server: GatewayProxyServer) -> None:
        """Attach the live server and snapshot its static config as the baseline
        the discovered catalog is layered onto."""
        self._server = server
        self._base = (
            dict(server.routes),
            {k: list(v) for k, v in server.pools.items()},
            dict(getattr(server, "model_pricing", {}) or {}),
            dict(getattr(server, "model_meta", {}) or {}),
        )

    def bridge(self) -> None:
        """Merge the discovered catalog onto the static baseline and push it into
        the live router via ``apply_routes`` — THE bridge that makes a discovered
        model routable with no hand edit.

        Static config WINS on every id collision (``setdefault``), so a
        hand-authored route/pool/price is never overwritten by discovery."""
        if self._server is None or self._base is None:
            return
        base_routes, base_pools, base_pricing, base_meta = self._base
        with self._lock:
            registry, pool_map = self.cache.registry_and_pool_map()

        # Compile discovered specs through the SAME router compiler the gateway
        # uses for hand config — no bespoke routing logic here.
        from charon.routing_policy import build_routes_and_pools
        disc_routes, disc_pools, _ = build_routes_and_pools(
            registry, pool_map, self._providers_cfg)

        routes = dict(base_routes)
        for mid, r in disc_routes.items():
            routes.setdefault(mid, r)
        pools = {k: list(v) for k, v in base_pools.items()}
        for vid, chain in disc_pools.items():
            pools.setdefault(vid, chain)   # a static pool of the same id wins

        pricing = dict(base_pricing)
        meta = dict(base_meta)
        for mid, spec in registry.items():
            if mid not in routes:
                continue  # dropped by the compiler (no resolvable base) — skip
            price = {k: spec[k] for k in _PRICE_KEYS if k in spec}
            if price:
                pricing.setdefault(mid, price)
            mm = {k: spec[k] for k in _META_KEYS if k in spec}
            if mm:
                meta.setdefault(mid, mm)

        model_ids = sorted(set(routes) | set(pools))
        # ── BRIDGE SITE: discovered catalog → the live routing tables that
        #    chain_for() and order_pool_by_live_cost() read. Revert this call and
        #    a discovered model is unroutable (chain_for returns []).
        self._server.apply_routes(routes, pools, model_ids, meta, pricing)

    def refresh_and_bridge(self) -> None:
        """One full cycle: poll all providers, then bridge the cache into the
        router. This is what the TTL loop and on-demand callers invoke."""
        self.refresh_now()
        self.bridge()

    # ── scheduling (daemon TTL loop — off the request path) ─────────────────
    def start(self) -> threading.Thread:
        """Launch the background TTL refresh loop (idempotent). The first cycle
        runs immediately, then every ``ttl_s`` seconds until :meth:`stop`."""
        if self._thread is not None and self._thread.is_alive():
            return self._thread
        self._stop.clear()

        def _loop() -> None:
            while not self._stop.is_set():
                try:
                    self.refresh_and_bridge()
                except Exception as exc:  # noqa: BLE001 — a bad cycle never kills the loop
                    log.error("catalog refresh cycle failed (%s: %s)",
                              type(exc).__name__, exc)
                if self._stop.wait(self.ttl_s):
                    break

        self._thread = threading.Thread(
            target=_loop, daemon=True, name="charon-catalog-refresh")
        self._thread.start()
        return self._thread

    def maybe_start(self) -> None:
        """Start the loop only when there are providers to poll (the module is
        already opt-in via its ModuleSpec, so mere presence means enabled)."""
        if self._providers_cfg:
            self.start()

    def stop(self) -> None:
        self._stop.set()
        t = self._thread
        if t is not None and t.is_alive() and t is not threading.current_thread():
            t.join(timeout=1.0)


def _load_providers(state_dir: str | Path | None) -> dict:
    """Load the configured providers (``base_url`` + ``key_env`` per provider)
    from ``<state_dir>/providers.json`` (or the default config dir). Missing /
    unreadable → ``{}`` (no providers to poll; the module stays idle)."""
    if state_dir is not None:
        base = Path(state_dir)
    else:
        try:
            from charon import secrets
            base = secrets.config_dir()
        except Exception:  # noqa: BLE001
            return {}
    path = base / "providers.json"
    if not path.exists():
        return {}
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}
