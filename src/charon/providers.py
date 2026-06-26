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

from dataclasses import dataclass, replace


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
    # OpenCode Zen — already wired as the project's `opencode-go` upstream.
    "opencode-go": ProviderPreset(
        "https://opencode.ai/zen/go/v1", "OPENCODE_ZEN_KEY",
        note="OpenCode Zen 'go' endpoint (verified, already used by charon doctor)."),
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
