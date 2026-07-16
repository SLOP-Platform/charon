"""Provider presets + resolution (ADR-0005 P3).

A *provider* groups the things that repeat across a vendor's models: the
OpenAI-compatible ``base_url``, the env var holding its key, and per-vendor
*quirks* (e.g. whether to strip the ``/v1`` prefix, whether it is prone to silent
downgrades). A *model* then just references a provider + its upstream model id,
instead of repeating the base URL on every entry.

Presets ship the base URLs we know so the operator only supplies the key env. A
preset is always overridable (``base_url``/``key_env``/``strip_v1`` in the
``[providers.<name>]`` table) — important because some vendor base URLs below are
**unverified** (no key on hand to live-check); override if a call 404s. Local
providers ship no key (localhost servers are usually unauthenticated).
"""
from __future__ import annotations

import json
import math
import urllib.request
from dataclasses import dataclass, replace
from urllib.parse import urlsplit

from .netutil import BROWSER_UA  # shared browser-like UA (P5 — Cloudflare 1010)
from .provider_presets import MERGED_RAW_DATA  # data merged from category modules

# ── Upstream wire-format vocabulary (SR-6) ─────────────────────────────────────
# The vendor-agnostic gateway/proxy core references these by constant, never by
# literal, so it stays product-clean; the vendor vocabulary lives here in the
# provider-adapter module (the layer the product-clean gate deliberately exempts).
WIRE_OPENAI = "openai"       # OpenAI chat-completions wire (the default; never enriched)
WIRE_ANTHROPIC = "anthropic"  # Anthropic /v1/messages wire (SR-6 prompt-cache target)
# Gateway config key for the SR-6 prompt-cache toggle (default ON).
ANTHROPIC_PROMPT_CACHE_KEY = "anthropic_prompt_cache"


@dataclass(frozen=True)
class ProviderPreset:
    base_url: str
    key_env: str | None = None
    strip_v1: bool = True       # most OpenAI-compatible bases already end in /v1
    downgrade_prone: bool = False  # vendor known to silently swap models (arms R1 strictly)
    # Upstream wire format: "openai" (default) or "anthropic". Drives SR-6 Phase-1
    # prompt-cache enrichment — an "anthropic"-wire route may get one cache_control
    # breakpoint injected; "openai" routes are NEVER touched. Provider-agnostic (a
    # per-provider marker, not a hardcoded model list).
    wire: str = WIRE_OPENAI
    # Response-shape adapter key (see response_adapters.py): the name of the adapter
    # that maps this provider's non-OpenAI response shape into canonical OpenAI shape.
    # None (the default) → the IDENTITY passthrough (byte-identical). Provider-agnostic
    # (a per-provider marker, declared not detected — mirrors ``wire``).
    adapter: str | None = None
    note: str = ""
    # Capability-engine (R7): per-provider hard limits surfaced for proactive
    # eligibility filtering.  None/absent means "unknown / no limit" (safe default).
    max_context: int | None = None       # max input+output tokens this provider admits
    max_concurrency: int | None = None   # max in-flight requests to this provider


# Built-in presets assembled from the ``provider_presets/`` category modules.
# ``MERGED_RAW_DATA`` is a plain dict merged by the registry; we construct
# ``ProviderPreset`` instances here to avoid a circular import (the category
# modules must not depend on this module).
PRESETS: dict[str, ProviderPreset] = {
    k: ProviderPreset(**v) for k, v in MERGED_RAW_DATA.items()}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects — a redirect could carry the ``Authorization`` Bearer to
    another host (urllib does NOT strip it cross-host). Key-exfil guard."""
    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


_MAX_MODELS_BYTES = 1_000_000  # cap the /models response (memory-DoS guard)


# ── Endpoint URL construction (PROVIDER-URL-HELPER) ─────────────────────────────
# The ONE place that knows how to turn a stored ``base_url`` into a concrete
# ``/models`` or ``/chat/completions`` endpoint. Previously each call site
# (``list_models`` here, ``config.keyprobe.validate_provider_key``,
# ``discover.discover_provider``) re-implemented ``base.rstrip("/") + "/suffix"``
# with its own subtly different edge-case handling, so a fix to one (e.g. the
# SSRF guard) didn't propagate to the others — exactly the drift the provider-
# probe bug depended on. ``validate_base_url`` consolidates the SSRF/link-local/
# metadata-host guard that used to live inline in ``config._store._validate_base_url``
# and ``keyprobe.validate_provider_key``; ``models_url``/``chat_url`` are the
# thin endpoint-specific entry points callers should reach for.


def validate_base_url(base_url: str) -> str:
    """Validate ``base_url`` and return it with trailing slashes stripped.

    Refuses non-http(s) schemes and link-local / cloud-metadata hosts (the SSRF
    guard that used to be forked inline in ``config._store`` and
    ``config.keyprobe``). Returns the base with no trailing ``/`` so a caller
    can safely ``+ "/" + path``. Raises ``ValueError`` on an invalid base.

    A falsy ``base_url`` (``""`` or ``None``) raises — callers that treat an
    absent base as non-fatal should branch before calling this (mirrors the old
    ``raw_base = base_url.rstrip("/") if base_url else ""`` sites, which left
    empty-string.URL construction to the caller)."""
    parts = urlsplit(base_url)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"invalid base URL scheme {parts.scheme!r}")
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        raise ValueError(f"refusing link-local / metadata host {host!r}")
    return base_url.rstrip("/")


def join_endpoint(base_url: str, path: str) -> str:
    """Join ``path`` onto ``base_url`` with exactly one ``/`` between them.

    Strips trailing slashes from the base and any leading slash from ``path``,
    then joins with a single ``/`` — so a base that already carries a path
    segment (``https://opencode.ai/zen/v1``) keeps every segment and never gets
    a double slash. Does NOT re-validate the scheme/host; callers composing from
    untrusted input should pass through ``validate_base_url`` first (or just use
    ``models_url`` / ``chat_url`` which do both)."""
    return base_url.rstrip("/") + "/" + path.lstrip("/")


def models_url(base_url: str) -> str:
    """The ONE place that knows the ``/models`` suffix. Validates + joins."""
    return join_endpoint(validate_base_url(base_url), "models")


def chat_url(base_url: str) -> str:
    """The ONE place that knows the ``/chat/completions`` suffix. Validates + joins."""
    return join_endpoint(validate_base_url(base_url), "chat/completions")


def _is_free(item: dict) -> bool:
    """Best-effort free detection from an OpenAI-style /models entry: an OpenRouter
    ``:free`` id suffix, or a ``pricing`` map whose prompt+completion are all 0."""
    mid = item.get("id")
    if isinstance(mid, str) and mid.endswith(":free"):
        return True
    pricing = item.get("pricing")
    if isinstance(pricing, dict):
        vals = []
        for k in ("prompt", "completion"):
            try:
                vals.append(float(pricing[k]))
            except (KeyError, TypeError, ValueError):
                return False
        return bool(vals) and all(v == 0 for v in vals)
    return False


_UPSTREAM_METADATA_MAP: tuple[tuple[str, str, type], ...] = (
    ("context_window", "context_window", int),
    ("context_length", "context_window", int),
    ("max_tokens", "max_tokens", int),
    ("reasoning", "reasoning", bool),
    ("vision", "vision", bool),
    ("audio", "audio", bool),
)


def _parse_models(data: object) -> list[dict]:
    """Pull ``[{id, free}]`` out of a provider's /models payload — the OpenAI
    ``{"data": [...]}`` shape, a bare list, or a list of strings. Optionally
    carries through upstream metadata (context_window, max_tokens, reasoning,
    vision, audio, cost_input, cost_output) if present.
    OpenRouter pricing (per-token USD strings) is stored verbatim as per-token USD."""
    items = data.get("data") if isinstance(data, dict) else data
    out: list[dict] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            entry: dict[str, object] = {"id": it["id"], "free": _is_free(it)}
            for src_key, dst_key, want_type in _UPSTREAM_METADATA_MAP:
                v = it.get(src_key)
                if v is not None and isinstance(v, want_type):
                    entry[dst_key] = v
            _extract_pricing(it, entry)
            out.append(entry)
        elif isinstance(it, str):
            out.append({"id": it, "free": False})
    return out


def _extract_pricing(source: dict, entry: dict[str, object]) -> None:
    """Read OpenRouter-style ``pricing: {prompt, completion}`` and store as
    ``cost_input`` / ``cost_output``.

    CANONICAL UNIT: **per-token USD** (the raw float — NO scaling). The
    ``pricing.{prompt,completion}`` field is the OpenRouter convention and is
    already quoted per single token (e.g. ``"0.0000025"`` == $2.50 / 1M tokens),
    so the value is stored verbatim. (An earlier version divided by 1e6 on the
    mistaken assumption it was per-1M — that undercounted 1,000,000×.) A provider
    that ever reports genuinely per-1M pricing would need its own ``/1e6`` seam;
    none of the wired providers do.

    Values that are non-numeric, non-finite (NaN/inf), or negative are rejected
    so garbage never persists into ``models.json``."""
    pricing = source.get("pricing")
    if not isinstance(pricing, dict):
        return
    for src, dst in ("prompt", "cost_input"), ("completion", "cost_output"):
        val = pricing.get(src)
        if val is None:
            continue
        try:
            per_token = float(val)
        except (ValueError, TypeError):
            continue
        if not (math.isfinite(per_token) and per_token >= 0):
            continue
        entry[dst] = per_token


def list_models(name: str, overrides: dict | None = None, *,
                api_key: str | None = None, timeout: float = 20.0) -> list[dict]:
    """``GET <base>/models`` for a provider and return ``[{id, free}]`` it advertises.

    Security (the key rides as a Bearer): non-http(s) and link-local/metadata bases
    are refused (SSRF), redirects are disabled (no cross-host key leak), and the
    response is size-capped. Raises ``ValueError`` for a bad base; urllib errors
    propagate (the caller reports them)."""
    preset = resolve(name, overrides)
    url = models_url(preset.base_url)
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", BROWSER_UA)
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    opener = urllib.request.build_opener(_NoRedirect())
    resp = opener.open(req, timeout=timeout)
    raw = resp.read(_MAX_MODELS_BYTES + 1)
    if len(raw) > _MAX_MODELS_BYTES:
        raise ValueError("models response too large")
    return _parse_models(json.loads(raw.decode("utf-8", "replace")))


_PRESET_FIELDS = ("base_url", "key_env", "strip_v1", "downgrade_prone", "wire", "adapter",
                  "max_context", "max_concurrency")


def resolve(name: str, overrides: dict | None = None) -> ProviderPreset:
    """Resolve a provider to a concrete preset: start from a built-in (if ``name``
    matches one), then apply ``[providers.<name>]`` overrides.

    A name with no built-in preset match instead starts from the persisted
    ``[providers.<name>]`` entry that ``providers add`` writes to
    ``providers.json`` (when one exists) — mirrors ``discover.py:discover_models``
    (the real routing path), which already reads this for exactly these
    providers. Without this, a provider added via ``providers add`` (not a
    built-in preset) had no way to be found by a caller — like the
    ``providers test`` CLI subcommand — that passes no explicit override.
    Explicit ``overrides`` are still applied on top, so they win over both the
    built-in preset and the persisted entry.

    A name with no preset, no persisted entry, and no explicit ``base_url``
    override is an error (we don't know where to send)."""
    overrides = dict(overrides or {})
    base = PRESETS.get(name)
    if base is None:
        from . import config  # deferred: config has no reverse dependency on this
                               # module, but keep the import local to this rarely-
                               # hit fallback branch rather than module-level.
        persisted = config.load_providers().get(name)
        if isinstance(persisted, dict) and persisted.get("base_url"):
            base = ProviderPreset(**{k: v for k, v in persisted.items()
                                     if k in _PRESET_FIELDS and v is not None})
    if base is None:
        if not overrides.get("base_url"):
            raise ValueError(
                f"unknown provider {name!r}: not a built-in preset "
                f"({', '.join(sorted(PRESETS))}) and no base_url override given")
        base = ProviderPreset(base_url=str(overrides["base_url"]))
    fields = {}
    for k in _PRESET_FIELDS:
        if k in overrides and overrides[k] is not None:
            fields[k] = overrides[k]
    return replace(base, **fields) if fields else base
