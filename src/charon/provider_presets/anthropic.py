"""Anthropic-family provider preset data (native Anthropic wire format).

Anthropic uses a non-OpenAI wire format (``/v1/messages`` + ``x-api-key`` header),
so its preset carries ``wire="anthropic"`` and ``strip_v1=False``.
"""
from __future__ import annotations

# Raw data dicts — ProviderPreset instances are created by the registry
# in __init__.py to avoid circular imports with providers.py.
CATEGORY_PRESETS_DATA: dict[str, dict] = {
    "anthropic": {
        "base_url": "https://api.anthropic.com",
        "key_env": "ANTHROPIC_API_KEY",
        "strip_v1": False,
        "wire": "anthropic",
        "note": "Anthropic native wire (/v1/messages). SR-6 Phase-1 prompt-cache "
                "enrichment target; full OpenAI<->Anthropic translation is Phase-2.",
    },
}
