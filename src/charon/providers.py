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
import urllib.request
from dataclasses import dataclass, replace
from urllib.parse import urlsplit


@dataclass(frozen=True)
class ProviderPreset:
    base_url: str
    key_env: str | None = None
    strip_v1: bool = True       # most OpenAI-compatible bases already end in /v1
    downgrade_prone: bool = False  # vendor known to silently swap models (arms R1 strictly)
    note: str = ""


# Built-in presets. VERIFIED bases are marked; UNVERIFIED ones carry a note and
# should be confirmed (or overridden) before trusting them with a real key.
PRESETS: dict[str, ProviderPreset] = {
    # OpenCode Zen — one key (OPENCODE_ZEN_KEY), two endpoints with DIFFERENT model
    # sets (verified live 2026-06-26): /zen/v1 = full catalog (~49: Claude/GPT/Gemini/
    # Qwen + open); /zen/go/v1 = coding-focused subset (~20).
    "opencode-zen": ProviderPreset(
        "https://opencode.ai/zen/v1", "OPENCODE_ZEN_KEY",
        note="OpenCode Zen — full catalog (Claude/GPT/Gemini/Qwen + open models)."),
    "opencode-go": ProviderPreset(
        "https://opencode.ai/zen/go/v1", "OPENCODE_ZEN_KEY",
        note="OpenCode Zen 'go' — coding-focused subset; same OPENCODE_ZEN_KEY."),
    # OpenRouter — base verified.
    "openrouter": ProviderPreset(
        "https://openrouter.ai/api/v1", "OPENROUTER_API_KEY",
        downgrade_prone=True,
        note="Free tiers can silently route to a different model — failover-guarded."),
    # NanoGPT / ZAI — base URLs verified live via `providers test` (2026-06-26):
    # nano-gpt.com/api/v1 → 200 from /models; api.z.ai/api/paas/v4 → 401 (needs key).
    # The full chat-completion contract is still pending a real key.
    "nanogpt": ProviderPreset(
        "https://nano-gpt.com/api/v1", "NANOGPT_API_KEY",
        note="Base verified live (HTTP 200 from /models)."),
    "zai": ProviderPreset(
        "https://api.z.ai/api/paas/v4", "ZAI_API_KEY",
        note="Verified live: chat at /api/paas/v4/chat/completions (strip_v1 strips "
             "the client's /v1 and appends to the /v4 base)."),
    # More hosted providers — all base URLs verified live via `providers test`
    # (2026-06-26): /models returns 200 (chutes) or 401-needs-key (the rest).
    "deepseek": ProviderPreset("https://api.deepseek.com/v1", "DEEPSEEK_API_KEY",
                               note="DeepSeek (base verified)."),
    "chutes": ProviderPreset("https://llm.chutes.ai/v1", "CHUTES_API_KEY",
                            note="Chutes.ai (base verified, /models open)."),
    "groq": ProviderPreset("https://api.groq.com/openai/v1", "GROQ_API_KEY",
                          note="Groq (base verified)."),
    "together": ProviderPreset("https://api.together.xyz/v1", "TOGETHER_API_KEY",
                              note="Together AI (base verified)."),
    "mistral": ProviderPreset("https://api.mistral.ai/v1", "MISTRAL_API_KEY",
                             note="Mistral (base verified)."),
    # Local OpenAI-compatible servers (usually no auth). Default ports shown.
    "lmstudio": ProviderPreset("http://localhost:1234/v1", None,
                               note="LM Studio (default port 1234)."),
    "jan": ProviderPreset("http://localhost:1337/v1", None,
                          note="Jan (default port 1337)."),
    "ollama": ProviderPreset("http://localhost:11434/v1", None,
                            note="Ollama OpenAI-compatible endpoint (port 11434)."),
    "local": ProviderPreset("http://localhost:1234/v1", None,
                           note="Generic OpenAI-compatible localhost — set base_url."),
}


class _NoRedirect(urllib.request.HTTPRedirectHandler):
    """Refuse redirects — a redirect could carry the ``Authorization`` Bearer to
    another host (urllib does NOT strip it cross-host). Key-exfil guard."""
    def redirect_request(self, *a, **k):  # noqa: ANN002, ANN003
        return None


_MAX_MODELS_BYTES = 1_000_000  # cap the /models response (memory-DoS guard)


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


def _parse_models(data: object) -> list[dict]:
    """Pull ``[{id, free}]`` out of a provider's /models payload — the OpenAI
    ``{"data": [...]}`` shape, a bare list, or a list of strings. Pure (testable)."""
    items = data.get("data") if isinstance(data, dict) else data
    out: list[dict] = []
    if not isinstance(items, list):
        return out
    for it in items:
        if isinstance(it, dict) and isinstance(it.get("id"), str):
            out.append({"id": it["id"], "free": _is_free(it)})
        elif isinstance(it, str):
            out.append({"id": it, "free": False})
    return out


def list_models(name: str, overrides: dict | None = None, *,
                api_key: str | None = None, timeout: float = 20.0) -> list[dict]:
    """``GET <base>/models`` for a provider and return ``[{id, free}]`` it advertises.

    Security (the key rides as a Bearer): non-http(s) and link-local/metadata bases
    are refused (SSRF), redirects are disabled (no cross-host key leak), and the
    response is size-capped. Raises ``ValueError`` for a bad base; urllib errors
    propagate (the caller reports them)."""
    preset = resolve(name, overrides)
    base = preset.base_url
    parts = urlsplit(base)
    if parts.scheme not in ("http", "https"):
        raise ValueError(f"base URL must be http(s), got {parts.scheme!r}")
    host = parts.hostname or ""
    if host.startswith("169.254.") or host == "metadata.google.internal":
        raise ValueError(f"refusing link-local / metadata host {host!r}")
    url = base.rstrip("/") + "/models"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")
    if api_key:
        req.add_header("Authorization", "Bearer " + api_key)
    opener = urllib.request.build_opener(_NoRedirect())
    resp = opener.open(req, timeout=timeout)
    raw = resp.read(_MAX_MODELS_BYTES + 1)
    if len(raw) > _MAX_MODELS_BYTES:
        raise ValueError("models response too large")
    return _parse_models(json.loads(raw.decode("utf-8", "replace")))


def resolve(name: str, overrides: dict | None = None) -> ProviderPreset:
    """Resolve a provider to a concrete preset: start from a built-in (if ``name``
    matches one), then apply ``[providers.<name>]`` overrides. A name with no preset
    and no ``base_url`` override is an error (we don't know where to send)."""
    overrides = overrides or {}
    base = PRESETS.get(name)
    if base is None:
        if not overrides.get("base_url"):
            raise ValueError(
                f"unknown provider {name!r}: not a built-in preset "
                f"({', '.join(sorted(PRESETS))}) and no base_url override given")
        base = ProviderPreset(base_url=str(overrides["base_url"]))
    fields = {}
    for k in ("base_url", "key_env", "strip_v1", "downgrade_prone"):
        if k in overrides and overrides[k] is not None:
            fields[k] = overrides[k]
    return replace(base, **fields) if fields else base
