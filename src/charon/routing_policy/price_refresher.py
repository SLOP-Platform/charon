"""Price refresher — background writers into the local ``model_pricing`` cache.

ADR-0016 step #3, ADOPT-NOT-BUILD (evidence: ``docs/adr/0016-demand-driven-capability-match.md``).
The router at request time reads ``srv.model_pricing`` (set by the proxy
constructor from the gateway's registry pass, which is what
``order_pool_by_live_cost`` resolves) — it never reaches out to a network. This
module is the OFF-HOT-PATH half of that contract: three background writers feed
the SAME cache the router reads, so the cheapest-first reorder can do real work
even before any traffic has accumulated meter data.

Three writers, all background (NEVER on the per-request path):

(a) **Vendored LiteLLM price table** — ``_data/litellm_prices.json``
    (`BerriAI/litellm` MIT, per-provider granularity). The seed layer: loaded
    once, in-process, at module import. R17's hand-typed TSV is replaced by
    this static snapshot — no bespoke scraper.

(b) **OpenRouter live poll** — ``GET https://openrouter.ai/api/v1/models``
    (no auth required, returns the whole catalog). The live layer for the
    OpenRouter pool AND the drift oracle for the vendored snapshot, because
    OpenRouter IS LiteLLM's own upstream for that provider, so the numbers
    must agree. Optional TTL polling; the gateway never blocks on it.

(c) **changedetection.io webhook ingest** — ``POST /pricing/drift`` handler
    accepting ``{"provider": str, "url": str, "old": any, "new": any}`` as
    out-of-band sourced-price updates for the no-API tail (nanogpt,
    neuralwatt, opencode-zen). The detector is self-hosted infra, not this
    repo — we expose just the ingest endpoint.

CRITICAL CONSTRAINT — OFF THE PER-REQUEST HOT PATH (ADR-0016 §Adversarial
stress-test #1, eval "Bottom line"): every writer here is cold-start /
advisory only. The METER-OBSERVED per-(model, provider) cost
(``observer.all_model_provider_costs`` proxy.py:549) supersedes any quoted
price inside ``order_pool_by_live_cost`` the moment traffic exists. This is
the only defense against thinking-token undercount — a static quote that
under-bills thinking tokens is worse than a meter that observes reality.
``apply_to_cache`` is exported ONLY for the background-poll call sites
(``refresh_openrouter_now``, webhook handler); the routing layer imports
nothing from this module.

Stdlib-only by design (the privileged core stays stdlib-only per ADR-0005).
No background scheduler is started here — that lives behind the F29 module
registry (``MODULE_SPECS``); we expose ``refresh_*`` callables so the registry
can wire them up without this module knowing about scheduling.

KEYING — pitfall #4 in the ticket: the SAME model is priced differently per
provider, so the cache is keyed per *model id* (the model's stable identity
in the registry), NOT per provider. Charon's registry pass already projects
each model onto a single (model_id → provider) route, so a model-keyed cache
is consistent with the routing layer's ``_live_rank_key`` lookup.

OWNERSHIP (single source of truth — ticket PRICE-REFRESHER): this file and
its vendored snapshot ``_data/litellm_prices.json`` are owned only by this
ticket. Do not edit ``routing_policy/__init__.py``, ``forwarder.py``, or
``proxy.py`` from here — they are read-only consumers of the cache this
module writes.
"""
from __future__ import annotations

import json
import logging
import math
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from importlib import resources
from typing import Any

from . import (
    _data as _data_pkg,  # type: ignore[attr-defined]  # sibling package for the vendored JSON
)

_log = logging.getLogger("charon.routing_policy.price_refresher")

# ---------------------------------------------------------------------------
# Vendored LiteLLM price table (MIT, BerriAI/litellm)
# ---------------------------------------------------------------------------

_VENDORED_FILE = "litellm_prices.json"


# Map LiteLLM provider keys → Charon pool labels. These are the providers
# Charon actually wires; only entries whose ``litellm_provider`` is in this
# map seed the cache. Other providers (Bedrock variants, Replicate niche,
# etc.) are intentionally not seeded — Charon doesn't route to them and
# seeding them would invent registry entries that don't exist.
PROVIDER_KEY_MAP: dict[str, str] = {
    "openai": "openai",
    "openrouter": "openrouter",
    "deepseek": "deepseek",
    "anthropic": "anthropic",
    "groq": "groq",
    "together_ai": "together",
    "mistral": "mistral",
    "fireworks_ai": "fireworks",
    "sambanova": "sambanova",
    "replicate": "replicate",
    "xai": "xai",
    "cohere": "cohere",
    "perplexity": "perplexity",
    "gemini": "gemini",
    "zai": "zai",
    "cerebras": "cerebras",
    "novita": "novita",
    "deepinfra": "deepinfra",
    "nebius": "nebius",
    "cloudflare": "cloudflare",
    "anyscale": "anyscale",
}


def load_vendored_snapshot() -> dict[str, dict[str, Any]]:
    """Load the vendored LiteLLM price snapshot from the package data directory.

    Returns the full dict ``{litellm_model_key: {input_cost_per_token, ...}}``.
    Returns ``{}`` if the snapshot is missing or unparseable — the rest of the
    gateway keeps working with an empty cache (meter-first, then registry
    fall-through). This is the seed layer; on any load failure we DO NOT raise
    — a poison vendored file must not break boot.
    """
    try:
        raw = resources.files(_data_pkg).joinpath(_VENDORED_FILE).read_text(
            encoding="utf-8"
        )
        data = json.loads(raw)
    except (OSError, ValueError, json.JSONDecodeError) as e:
        _log.warning("vendored LiteLLM snapshot unreadable: %s", e)
        return {}
    if not isinstance(data, dict):
        _log.warning("vendored LiteLLM snapshot is not a dict; ignoring")
        return {}
    return {k: v for k, v in data.items() if isinstance(v, dict)}


# ---------------------------------------------------------------------------
# Cache writer — mutates ``model_pricing`` in place under a lock
# ---------------------------------------------------------------------------


@dataclass
class CacheState:
    """Mutable, thread-safe state for the live cache this module writes.

    The lock makes ``apply_to_cache`` safe to call from a background poller
    while the gateway's request thread reads ``self.model_pricing`` directly.
    Reads in the routing layer (``proxy.py:_lookup_pricing``,
    ``proxy_server._pre_flight_pricing``) take NO lock — they tolerate
    seeing a stale-but-consistent dict for one request; the next request
    will see the new keys. That is the "STALE-BUT-USABLE" guarantee
    called out in the ticket (refresh failure must never block or slow a
    route)."""

    model_pricing: dict[str, dict]
    # Per-(provider, model) last-known quoted prices — the drift oracle for
    # the vendored snapshot. Updated alongside ``model_pricing`` so a
    # downstream drift-checker can compare quoted vs vendored.
    quoted_prices: dict[tuple[str, str], tuple[float, float]] = None  # type: ignore[assignment]
    # ``True`` after the vendored snapshot has been loaded at least once.
    seeded: bool = False
    # Last successful OpenRouter poll (epoch seconds) — drives the TTL.
    last_openrouter_poll_ts: float = 0.0
    # Last refresh error string — surfaced to logs and ``/charon/status``;
    # NEVER raised into the request path.
    last_error: str | None = None
    _lock: threading.Lock = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        self.model_pricing = dict(self.model_pricing or {})
        self.quoted_prices = {}
        self._lock = threading.Lock()


def _to_charon_model_id(model_key: str, charon_provider: str) -> str:
    """Project a LiteLLM ``model_key`` into the Charon registry model id.

    LiteLLM keys are ``{provider}/{org}/{model}`` for hosted
    (``openrouter/anthropic/claude-3-haiku``), or ``{org}/{model}``
    (``together_ai/Qwen/Qwen3-Coder-480B-A35B-Instruct-FP8``), or bare
    (``deepseek-chat``, ``deepseek-v4-pro``). Charon registry ids are
    stable strings the operator configures (``deepseek-v4-pro``,
    ``together-ai/Qwen/...`` — Charon's ``add_model`` does NOT namespace
    hosted providers, so the LiteLLM full key is the natural fit).

    We DO NOT strip a provider prefix here — Charon's
    ``_lookup_pricing`` in proxy.py:419 already normalizes on the final
    ``/``-segment, so either form resolves. The returned id is the same
    shape as the upstream registration in ``models.json`` for that route.
    """
    return model_key


def _entry_to_pricing(litellm_entry: dict, charon_provider: str) -> dict | None:
    """Translate one LiteLLM entry into a Charon pricing dict.

    Returns ``None`` if the entry lacks the per-token price fields (the
    SOURCED table must never invent a price — unknown is safer than wrong).
    The returned dict has at minimum ``cost_input`` and ``cost_output``,
    both per-token USD, plus ``source`` (URL the operator can audit) and
    ``priced_by: "vendored"`` so the discovery clobber-protection in
    ``discover._update_model_pricing_from_discovery`` does NOT overwrite
    an operator-set price with a discovery quote (this entry was set by
    this module's writer, not by a real /models response).
    """
    ci = litellm_entry.get("input_cost_per_token")
    co = litellm_entry.get("output_cost_per_token")
    if not isinstance(ci, (int, float)) or not isinstance(co, (int, float)):
        return None
    if not (math.isfinite(float(ci)) and math.isfinite(float(co))):
        return None
    if ci < 0 or co < 0:
        return None
    out: dict[str, Any] = {
        "cost_input": float(ci),
        "cost_output": float(co),
        "priced_by": "vendored",
    }
    src = litellm_entry.get("source")
    if isinstance(src, str) and src:
        out["source"] = src
    cache = litellm_entry.get("cache_read_input_token_cost")
    if isinstance(cache, (int, float)) and cache >= 0:
        out["cost_cache_read"] = float(cache)
    mit = litellm_entry.get("max_input_tokens")
    if isinstance(mit, int) and mit > 0:
        out["context_window"] = mit
    # Free tag: input == 0 AND output == 0 means a free tier in LiteLLM
    # (e.g. ``together_ai/meta-llama/Llama-3.3-70B-Instruct-Turbo-Free``).
    if ci == 0 and co == 0:
        out["free"] = True
    return out


def seed_from_vendored(state: CacheState) -> int:
    """Load the vendored LiteLLM snapshot into ``state.model_pricing``.

    Returns the number of entries written. Safe to call multiple times — a
    re-seed is idempotent (each key overwrites cleanly, and only NEW keys
    are added; existing keys are preserved so a later live poll is not
    clobbered). Skipped when ``state.seeded`` is already True (caller may
    force with ``force=True``). Failures are logged and reflected in
    ``state.last_error`` but NEVER raised."""
    if state.seeded:
        return 0
    snapshot = load_vendored_snapshot()
    if not snapshot:
        state.last_error = "vendored snapshot empty/unreadable"
        return 0
    written = 0
    with state._lock:  # type: ignore[union-attr]
        for litellm_key, entry in snapshot.items():
            if not isinstance(entry, dict):
                continue
            lp = entry.get("litellm_provider")
            if not isinstance(lp, str):
                continue
            charon_provider = PROVIDER_KEY_MAP.get(lp)
            if charon_provider is None:
                continue  # not a provider Charon routes to
            pricing = _entry_to_pricing(entry, charon_provider)
            if pricing is None:
                continue
            mid = _to_charon_model_id(litellm_key, charon_provider)
            # Don't clobber an operator-set price (anything not stamped by us).
            existing = state.model_pricing.get(mid)
            if isinstance(existing, dict) and existing.get("priced_by") not in (
                "vendored", "openrouter_live", "webhook",
            ):
                continue
            state.model_pricing[mid] = pricing
            state.quoted_prices[(charon_provider, mid)] = (
                float(pricing["cost_input"]), float(pricing["cost_output"]),
            )
            written += 1
        state.seeded = True
        state.last_error = None
    _log.info("price_refresher: vendored seed wrote %d entries", written)
    return written


def apply_to_cache(
    state: CacheState,
    *,
    provider: str,
    entries: dict[str, dict],
    priced_by: str,
) -> int:
    """Generic writer used by the OpenRouter poller and the webhook handler.

    ``entries`` is ``{model_id: {cost_input, cost_output, ...}}``. Each entry
    is merged into ``state.model_pricing`` under lock, with the same
    clobber-protection as the vendored seed (operator-set prices survive).
    ``priced_by`` is stamped on each written entry so later writers can tell
    whether a price is theirs to refresh."""
    if not isinstance(provider, str) or not provider:
        return 0
    written = 0
    with state._lock:  # type: ignore[union-attr]
        for mid, entry in entries.items():
            if not isinstance(mid, str) or not mid:
                continue
            if not isinstance(entry, dict):
                continue
            ci = entry.get("cost_input")
            co = entry.get("cost_output")
            if not isinstance(ci, (int, float)) or not isinstance(co, (int, float)):
                continue
            if ci < 0 or co < 0:
                continue
            existing = state.model_pricing.get(mid)
            if isinstance(existing, dict) and existing.get("priced_by") not in (
                "vendored", "openrouter_live", "webhook",
            ):
                continue
            merged = dict(existing) if isinstance(existing, dict) else {}
            merged["cost_input"] = float(ci)
            merged["cost_output"] = float(co)
            merged["priced_by"] = priced_by
            for k in ("cost_cache_read", "context_window", "source"):
                v = entry.get(k)
                if v is not None:
                    merged[k] = v
            state.model_pricing[mid] = merged
            state.quoted_prices[(provider, mid)] = (float(ci), float(co))
            written += 1
    return written


# ---------------------------------------------------------------------------
# (b) OpenRouter live poll — background, NEVER on the request path
# ---------------------------------------------------------------------------

_OPENROUTER_URL = "https://openrouter.ai/api/v1/models"
_OPENROUTER_TTL_S = 3600.0  # hourly; OpenRouter IS LiteLLM's own upstream,
                             # so this doubles as the vendored-snapshot drift
                             # oracle for the openrouter provider.


def parse_openrouter_payload(
    payload: Any, *, charon_provider: str = "openrouter",
) -> dict[str, dict]:
    """Parse one OpenRouter ``/api/v1/models`` response into the cache shape.

    OpenRouter returns ``{"data": [{"id", "pricing":
    {"prompt", "completion", "input_cache_read", ...}}]}``.
    Pricing values are STRINGS in the source ("0.0000025"); we parse to float
    per-token USD and reuse the same cache shape as the vendored seed so
    ``order_pool_by_live_cost`` resolves them identically. Unknown /
    non-numeric / negative values are skipped."""
    out: dict[str, dict] = {}
    items: list[dict] | None = None
    if isinstance(payload, dict):
        d = payload.get("data")
        if isinstance(d, list):
            items = d
    elif isinstance(payload, list):
        items = payload
    if not items:
        return out
    for m in items:
        if not isinstance(m, dict):
            continue
        mid = m.get("id")
        if not isinstance(mid, str) or not mid:
            continue
        pricing = m.get("pricing")
        if not isinstance(pricing, dict):
            continue
        ci_raw = pricing.get("prompt")
        co_raw = pricing.get("completion")
        if ci_raw is None or co_raw is None:
            continue
        try:
            ci = float(ci_raw)
            co = float(co_raw)
        except (TypeError, ValueError):
            continue
        if not (math.isfinite(ci) and math.isfinite(co)) or ci < 0 or co < 0:
            continue
        entry: dict[str, Any] = {"cost_input": ci, "cost_output": co}
        cache_raw = pricing.get("input_cache_read")
        if cache_raw is not None:
            try:
                cache = float(cache_raw)
                if math.isfinite(cache) and cache >= 0:
                    entry["cost_cache_read"] = cache
            except (TypeError, ValueError):
                pass
        cl = m.get("context_length")
        if isinstance(cl, int) and cl > 0:
            entry["context_window"] = cl
        out[mid] = entry
    return out


def refresh_openrouter_now(state: CacheState, *, timeout: float = 10.0) -> int:
    """One-shot OpenRouter poll. Returns the number of entries written.

    Intended to be called from a background scheduler (F29 MODULE_SPECS or
    any caller the operator wires up). The router NEVER calls this — see
    the module docstring for the off-hot-path guarantee."""
    try:
        req = urllib.request.Request(_OPENROUTER_URL, method="GET")
        req.add_header("User-Agent", "charon-price-refresher/1.0")
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            raw = resp.read(8 * 1024 * 1024)  # 8 MiB cap; OR catalog is ~500 KiB
        payload = json.loads(raw.decode("utf-8", "replace"))
    except (urllib.error.URLError, urllib.error.HTTPError, OSError, ValueError,
            json.JSONDecodeError) as e:
        with state._lock:  # type: ignore[union-attr]
            state.last_error = f"openrouter poll: {type(e).__name__}: {e}"
        _log.warning("price_refresher: openrouter poll failed: %s", e)
        return 0
    parsed = parse_openrouter_payload(payload)
    if not parsed:
        with state._lock:  # type: ignore[union-attr]
            state.last_error = "openrouter poll: empty/unparseable payload"
        return 0
    written = apply_to_cache(
        state, provider="openrouter", entries=parsed, priced_by="openrouter_live",
    )
    with state._lock:  # type: ignore[union-attr]
        state.last_openrouter_poll_ts = time.time()
        state.last_error = None
    _log.info("price_refresher: openrouter poll wrote %d entries", written)
    return written


def openrouter_poll_due(state: CacheState, *, now: float | None = None,
                        ttl_s: float = _OPENROUTER_TTL_S) -> bool:
    """True iff ``ttl_s`` has elapsed since the last successful OpenRouter poll."""
    ts = now if now is not None else time.time()
    return (ts - state.last_openrouter_poll_ts) >= ttl_s


# ---------------------------------------------------------------------------
# (c) changedetection.io webhook ingest — for the no-API tail
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class DriftEvent:
    """One pricing-drift event from changedetection.io.

    Schema matches the changedetection.io webhook body the detector posts:
    ``{"provider": str, "url": str, "old": any, "new": any}``. ``old`` /
    ``new`` are the per-token USD quotes the detector observed at its
    scrape-cadence; we keep them so the drift checker (R17, separate) can
    raise a red. ``model_id`` is derived from ``url`` by the handler."""

    provider: str
    url: str
    old: Any
    new: Any
    model_id: str = ""


def parse_drift_event(body: dict) -> DriftEvent | None:
    """Validate one webhook body → :class:`DriftEvent` or ``None``.

    ``model_id`` is the FINAL ``/``-segment of ``url`` — that is the model
    id the upstream pricing page lives at (e.g.
    ``https://api-docs.deepseek.com/quick_start/pricing/deepseek-v4-pro``
    → ``deepseek-v4-pro``). Empty / non-string fields return ``None``."""
    if not isinstance(body, dict):
        return None
    provider = body.get("provider")
    url = body.get("url")
    if not isinstance(provider, str) or not isinstance(url, str):
        return None
    model_id = url.rstrip("/").rsplit("/", 1)[-1] if "/" in url else url
    return DriftEvent(
        provider=provider, url=url, old=body.get("old"), new=body.get("new"),
        model_id=model_id,
    )


def apply_drift_event(state: CacheState, event: DriftEvent) -> int:
    """Apply one :class:`DriftEvent` to the cache.

    Only ``new`` is written — that is the detector's freshly-sourced quote.
    The cache key is ``event.model_id`` (the model the URL was about); the
    provider tag is stamped on the entry for the R17 drift checker to
    consume. Operator-set prices are NOT clobbered (same guard as the other
    writers)."""
    if not isinstance(event.new, (int, float)):
        return 0
    if event.new < 0:
        return 0
    # OpenRouter-only symmetric structure: ``new`` is total-cost per token
    # in practice. For DriftEvent we only carry a single number, so we
    # treat it as ``cost_output`` and leave ``cost_input`` untouched if
    # already set, else mirror it. This matches how the detector emits
    # symmetric providers (most of the no-API tail uses a flat rate).
    entry: dict[str, Any] = {
        "cost_input": float(event.new),
        "cost_output": float(event.new),
        "priced_by": "webhook",
    }
    return apply_to_cache(
        state, provider=event.provider, entries={event.model_id: entry},
        priced_by="webhook",
    )


# ---------------------------------------------------------------------------
# Convenience — the "registry" the router's R2 block reads
# ---------------------------------------------------------------------------


def build_registry_view(
    state: CacheState,
    *,
    models: dict[str, dict] | None = None,
) -> dict[str, dict]:
    """Build the registry view ``order_pool_by_live_cost`` consumes.

    The forwarder's R2 block (forwarder.py:386-393) currently builds this
    dict inline from ``srv.model_pricing`` + ``srv.model_meta``. This helper
    is the SAME composition expressed as one call so the price-refresher
    can be unit-tested against a stable contract:

        registry[mid] = {**model_pricing[mid], **model_meta[mid]}

    Operator-set fields (free, cost_class, cost_rank, ...) are preserved
    if *models* is provided. With *models=None* (default), only the price
    fields seeded by this module's writers are exposed — the test surface
    uses this."""
    out: dict[str, dict] = {}
    snapshot = state.model_pricing  # read without lock — see CacheState
    if models is None:
        for mid, entry in snapshot.items():
            if isinstance(entry, dict):
                out[mid] = dict(entry)
        return out
    for mid, meta in models.items():
        price = snapshot.get(mid, {})
        merged: dict = {}
        if isinstance(price, dict):
            merged.update(price)
        if isinstance(meta, dict):
            merged.update(meta)
        if merged:
            out[mid] = merged
    return out


__all__ = [
    "PROVIDER_KEY_MAP",
    "CacheState",
    "DriftEvent",
    "apply_drift_event",
    "apply_to_cache",
    "build_registry_view",
    "load_vendored_snapshot",
    "openrouter_poll_due",
    "parse_drift_event",
    "parse_openrouter_payload",
    "refresh_openrouter_now",
    "seed_from_vendored",
]