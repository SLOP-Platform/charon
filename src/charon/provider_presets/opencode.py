"""OpenCode Zen provider preset data (internal endpoints).

These share the ``OPENCODE_ZEN_KEY`` env var but expose different model subsets
on different paths.
"""
from __future__ import annotations

CATEGORY_PRESETS_DATA: dict[str, dict] = {
    "opencode-zen": {
        "base_url": "https://opencode.ai/zen/v1",
        "key_env": "OPENCODE_ZEN_KEY",
        "note": "OpenCode Zen — full catalog (Claude/GPT/Gemini/Qwen + open models).",
    },
    "opencode-go": {
        "base_url": "https://opencode.ai/zen/go/v1",
        "key_env": "OPENCODE_ZEN_KEY",
        "note": "OpenCode Zen 'go' — coding-focused subset; same OPENCODE_ZEN_KEY.",
    },
}
