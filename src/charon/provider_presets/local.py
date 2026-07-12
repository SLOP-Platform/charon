"""Local / on-premise provider preset data (no auth, localhost addresses).

These are OpenAI-compatible servers running on localhost; they ship no API key
since authentication is typically disabled.
"""
from __future__ import annotations

CATEGORY_PRESETS_DATA: dict[str, dict] = {
    "lmstudio": {
        "base_url": "http://localhost:1234/v1", "key_env": None,
        "note": "LM Studio (default port 1234).",
    },
    "jan": {
        "base_url": "http://localhost:1337/v1", "key_env": None,
        "note": "Jan (default port 1337).",
    },
    "ollama": {
        "base_url": "http://localhost:11434/v1", "key_env": None,
        "note": "Ollama OpenAI-compatible endpoint (port 11434).",
    },
    "vllm": {
        "base_url": "http://localhost:8000/v1", "key_env": None,
        "note": "vLLM (default port 8000, OpenAI-compatible server).",
    },
    "local": {
        "base_url": "http://localhost:1234/v1", "key_env": None,
        "note": "Generic OpenAI-compatible localhost — set base_url.",
    },
}
