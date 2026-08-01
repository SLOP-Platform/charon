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

CATALOG-REFRESH-PERSIST: the discovered catalog is ALSO written back to
``models.json`` (atomically) so it survives a gateway restart. Discovery merges
with existing entries: operator-set ``upstream_base``/``key_env`` signals
hand-ownership and discovery skips those ids entirely; ``enabled: false``
set by the operator (``enabled: false`` without ``refresh_disabled: true``)
is never clobbered. A model that disappears from a provider's ``/models`` is
marked ``enabled: false, refresh_disabled: true`` in the catalog (surfaces
rotations) and its in-memory route is dropped by the bridge.

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
    ``providers.list_models`` (never a bespoke fetcher). The provider key comes
    from the ONE resolver (``secrets.get_provider_key``), so a refresh can never
    send a key to a base that key is not bound to."""
    from charon import secrets as _secrets

    preset = _providers_mod.resolve(name, overrides)
    api_key = _secrets.get_provider_key(
        name, key_env=preset.key_env, base_url=preset.base_url)
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
    updated: dict[str, float] = field(default_factory=dict)
    last_failure: dict[str, str] = field(default_factory=dict)

    def put(self, provider: str, entries: dict[str, ProviderEntry],
            failure: str | None = None) -> None:
        self.per_provider[provider] = entries
        self.updated[provider] = time.time()
        if failure is not None:
            self.last_failure[provider] = failure
        else:
            self.last_failure.pop(provider, None)

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
            else _load_providers(state_dir)[0])
        self.ttl_s = float(ttl_s)
        self._list_models: ListModelsFn = list_models_fn or _default_list_models
        self.cache = CatalogCache()
        self.poll_count = 0
        self._lock = threading.Lock()
        self._server: GatewayProxyServer | None = None
        self._base: tuple[dict, dict, dict, dict] | None = None
        self._thread: threading.Thread | None = None
        self._stop = threading.Event()
        self._state_dir: Path | None
        if state_dir is not None:
            self._state_dir = Path(state_dir)
        elif providers_cfg is not None:
            self._state_dir = None
        else:
            try:
                from charon import secrets
                self._state_dir = secrets.config_dir()
            except Exception:  # noqa: BLE001
                self._state_dir = None

    # ── discovery (background / on-demand only — NEVER on the hot path) ──────
    def refresh_now(self) -> None:
        """Poll every configured provider's ``/models``, update the cache, and
        persist the merged catalog to ``models.json``.

        A provider whose poll raises is logged as a red and SKIPPED — its
        last-good entries stay in the cache (stale-but-usable). Never raises."""
        for name, cfg in self._providers_cfg.items():
            overrides = cfg if isinstance(cfg, dict) else None
            self.poll_count += 1
            failure: str | None = None
            try:
                found = self._list_models(name, overrides)
            except Exception as exc:  # noqa: BLE001 — degrade, never block routing
                failure = f"{type(exc).__name__}: {exc}"
                log.error(
                    "catalog refresh: provider %r /models poll failed "
                    "(%s) — keeping last-good entries (stale-but-usable)",
                    name, failure)
            entries: dict[str, ProviderEntry] = {}
            if failure is None:
                for m in found:
                    raw = m.get("id") if isinstance(m, dict) else None
                    if not isinstance(raw, str) or not raw:
                        continue
                    member_id = f"{name}/{raw}"
                    price = {k: m[k] for k in _PRICE_KEYS if k in m}
                    meta = {k: m[k] for k in _META_KEYS if k in m}
                    entries[member_id] = ProviderEntry(name, raw, price, meta)
                with self._lock:
                    self.cache.put(name, entries, failure=None)
                    self.cache.last_failure.pop(name, None)
            else:
                with self._lock:
                    self.cache.last_failure[name] = failure
                    self.cache.updated.pop(name, None)
        with self._lock:
            self._persist_unlocked()

    def _persist_unlocked(self) -> None:
        """Persist the discovered catalog into ``models.json``, merging with
        existing entries. Caller must hold ``_lock``.

        Merge rules (precedence order, highest first):
          1. ``upstream_base`` or ``key_env`` in existing entry → skip (hand-owned).
          2. ``refresh_disabled: true`` in existing entry → skip (explicitly opted out).
          3. ``enabled: false`` in existing entry → skip (operator intent wins;
             ``refresh_disabled`` is NOT set so the operator can re-enable later).
          4. New model absent from catalog → add entry.
          5. Existing model not in this provider's current /models → mark
             ``enabled: false, refresh_disabled: true`` (rotation surfaced).
          6. Existing discovered entry → update ``free``/``cost_input``/``cost_output``
             and stamp ``refreshed_via: "<provider>"``."""
        if self._state_dir is None:
            return
        models_path = self._state_dir / "models.json"
        try:
            existing = json.loads(models_path.read_text())
        except (OSError, json.JSONDecodeError):
            existing = {}
        if not isinstance(existing, dict):
            existing = {}

        merged = dict(existing)
        now = time.time()

        def _casefold_get(d: dict, key: str) -> dict | None:
            cf = key.casefold()
            for k, v in d.items():
                if isinstance(k, str) and k.casefold() == cf:
                    return v
            return None

        def _find_by_upstream_model(d: dict,
                                    upstream_model: str) -> tuple[str, dict] | None:
            cf = upstream_model.casefold()
            for k, v in d.items():
                if (isinstance(k, str) and isinstance(v, dict)
                        and v.get("upstream_model", "").casefold() == cf):
                    return k, v
            return None

        for provider, members in self.cache.per_provider.items():
            for _member_id, entry in members.items():
                raw = entry.upstream_model
                normalized_id = _normalize(raw)
                existing_entry = _casefold_get(merged, normalized_id)
                if existing_entry is None:
                    existing_entry = {}
                if (existing_entry.get("upstream_base") or existing_entry.get("key_env")):
                    continue
                if existing_entry.get("refresh_disabled"):
                    continue
                if existing_entry.get("enabled") is False:
                    continue
                new_entry: dict[str, Any] = {
                    "provider": provider,
                    "upstream_model": raw,
                    "free": bool(entry.price.get("free", False)),
                }
                if entry.price.get("cost_input") is not None:
                    new_entry["cost_input"] = entry.price["cost_input"]
                if entry.price.get("cost_output") is not None:
                    new_entry["cost_output"] = entry.price["cost_output"]
                for k in _META_KEYS:
                    if k in entry.meta:
                        new_entry[k] = entry.meta[k]
                new_entry["refreshed_via"] = provider
                new_entry["refreshed_at"] = now
                match = _find_by_upstream_model(merged, raw)
                if match is not None:
                    existing_key, existing_val = match
                    existing_val.update(new_entry)
                else:
                    merged[normalized_id] = new_entry

        for model_id in list(merged.keys()):
            entry = merged[model_id]
            if not isinstance(entry, dict):
                continue
            if entry.get("refresh_disabled"):
                continue
            prov = entry.get("provider")
            if prov and entry.get("refreshed_via") == prov:
                current_ids = {
                    _normalize(pe.upstream_model)
                    for pe in self.cache.per_provider.get(prov, {}).values()
                }
                if _normalize(entry.get("upstream_model", "")) not in current_ids:
                    entry["enabled"] = False
                    entry["refresh_disabled"] = True

        self._write_models_json(merged)

    def _write_models_json(self, models: dict) -> None:
        if self._state_dir is None:
            return
        try:
            self._state_dir.mkdir(parents=True, exist_ok=True)
            models_path = self._state_dir / "models.json"
            tmp = models_path.with_name("models.json.tmp")
            tmp.write_text(json.dumps(models, indent=2), encoding="utf-8")
            tmp.replace(models_path)
        except OSError as exc:
            log.error("catalog refresh: failed to write models.json (%s)", exc)

    def status_summary(self) -> dict[str, Any]:
        """Return human-readable status of the last refresh cycle.

        Returns ``{"last_refresh": float|None, "providers": {name: status_dict}}``
        where each status dict has ``ok`` or ``failed: <reason>`` and
        ``models_discovered: int``."""
        with self._lock:
            last = max(
                (ts for ts in self.cache.updated.values()),
                default=None,
            )
            result: dict[str, Any] = {
                "last_refresh": last,
                "providers": {},
            }
            for name in self._providers_cfg:
                info: dict[str, Any] = {}
                if name in self.cache.updated:
                    info["ok"] = True
                    info["models_discovered"] = len(
                        self.cache.per_provider.get(name, {}))
                elif name in self.cache.last_failure:
                    info["failed"] = self.cache.last_failure[name]
                else:
                    info["failed"] = "unknown"
                result["providers"][name] = info
            return result

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

        from charon.routing_policy import build_routes_and_pools
        disc_routes, disc_pools, _ = build_routes_and_pools(
            registry, pool_map, self._providers_cfg)

        routes = dict(base_routes)
        for mid, r in disc_routes.items():
            routes.setdefault(mid, r)
        pools = {k: list(v) for k, v in base_pools.items()}
        for vid, chain in disc_pools.items():
            pools.setdefault(vid, chain)

        pricing = dict(base_pricing)
        meta = dict(base_meta)
        for mid, spec in registry.items():
            if mid not in routes:
                continue
            price = {k: spec[k] for k in _PRICE_KEYS if k in spec}
            if price:
                pricing.setdefault(mid, price)
            mm = {k: spec[k] for k in _META_KEYS if k in spec}
            if mm:
                meta.setdefault(mid, mm)

        model_ids = sorted(set(routes) | set(pools))
        self._server.apply_routes(routes, pools, model_ids, meta, pricing)

    def refresh_and_bridge(self) -> None:
        """One full cycle: poll all providers, persist the catalog, then bridge
        into the router. This is what the TTL loop and on-demand callers invoke."""
        self.refresh_now()
        self.bridge()

    # ── scheduling (daemon TTL loop — off the request path) ─────────────────
    def start(self) -> threading.Thread:
        """Launch the background TTL refresh loop (idempotent). The first cycle
        runs immediately, then every ``ttl_s`` seconds until :meth:`stop``."""
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


def _load_providers(
    state_dir: str | Path | None,
) -> tuple[dict, Path | None]:
    """Load the configured providers (``base_url`` + ``key_env`` per provider)
    from ``<state_dir>/providers.json`` (or the default config dir). Returns
    ``(providers_dict, resolved_state_dir)``. Missing/unreadable → ``({}, None)``."""
    resolved_dir: Path | None = None
    if state_dir is not None:
        resolved_dir = Path(state_dir)
    else:
        try:
            from charon import secrets
            resolved_dir = secrets.config_dir()
        except Exception:  # noqa: BLE001
            return {}, None
    path = resolved_dir / "providers.json"
    if not path.exists():
        return {}, resolved_dir
    try:
        data = json.loads(path.read_text())
    except (OSError, json.JSONDecodeError):
        return {}, resolved_dir
    return (data if isinstance(data, dict) else {}), resolved_dir
