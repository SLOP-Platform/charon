"""Hosted / cloud provider preset data (OpenAI-compatible, key-auth).

All base URLs were verified live via ``providers test`` (2026-06-26) unless
otherwise noted.
"""
from __future__ import annotations

CATEGORY_PRESETS_DATA: dict[str, dict] = {
    "openrouter": {
        "base_url": "https://openrouter.ai/api/v1",
        "key_env": "OPENROUTER_API_KEY",
        "downgrade_prone": True,
        "note": "Free tiers can silently route to a different model — failover-guarded.",
    },
    "cline-pass": {
        "base_url": "https://api.cline.bot/api/v1",
        "key_env": "CLINE_PASS_API_KEY",
        "strip_v1": True,
        "adapter": "cline",
        "note": "Cline Pass — non-stream bodies are wrapped ({data,success}); adapter="
                "'cline' unwraps them. No /models endpoint (setup key probe false-fails).",
    },
    "nanogpt": {
        "base_url": "https://nano-gpt.com/api/v1",
        "key_env": "NANOGPT_API_KEY",
        "note": "Base verified live (HTTP 200 from /models).",
    },
    "zai": {
        "base_url": "https://api.z.ai/api/paas/v4",
        "key_env": "ZAI_API_KEY",
        "note": "Verified live: chat at /api/paas/v4/chat/completions (strip_v1 strips "
                "the client's /v1 and appends to the /v4 base).",
    },
    "deepseek": {
        "base_url": "https://api.deepseek.com/v1",
        "key_env": "DEEPSEEK_API_KEY",
        "note": "DeepSeek (base verified).",
    },
    "chutes": {
        "base_url": "https://llm.chutes.ai/v1",
        "key_env": "CHUTES_API_KEY",
        "note": "Chutes.ai (base verified, /models open).",
    },
    "groq": {
        "base_url": "https://api.groq.com/openai/v1",
        "key_env": "GROQ_API_KEY",
        "note": "Groq (base verified).",
    },
    "together": {
        "base_url": "https://api.together.xyz/v1",
        "key_env": "TOGETHER_API_KEY",
        "note": "Together AI (base verified).",
    },
    "mistral": {
        "base_url": "https://api.mistral.ai/v1",
        "key_env": "MISTRAL_API_KEY",
        "note": "Mistral (base verified).",
    },
    "fireworks": {
        "base_url": "https://api.fireworks.ai/inference/v1",
        "key_env": "FIREWORKS_API_KEY",
        "note": "Fireworks AI (base verified, HTTP 401 on /models).",
    },
    "sambanova": {
        "base_url": "https://api.sambanova.ai/v1",
        "key_env": "SAMBANOVA_API_KEY",
        "note": "SambaNova (base verified, /models HTTP 200).",
    },
    "replicate": {
        "base_url": "https://api.replicate.com/v1",
        "key_env": "REPLICATE_API_KEY",
        "note": "Replicate (base verified, HTTP 401 on /models).",
    },
    "xai": {
        "base_url": "https://api.x.ai/v1",
        "key_env": "XAI_API_KEY",
        "note": "xAI (Grok API, base verified, HTTP 401 on /models).",
    },
    "cohere": {
        "base_url": "https://api.cohere.ai/v1",
        "key_env": "COHERE_API_KEY",
        "note": "Cohere (base verified, HTTP 401 on /models).",
    },
    "openai": {
        "base_url": "https://api.openai.com/v1",
        "key_env": "OPENAI_API_KEY",
        "note": "OpenAI (base verified, HTTP 401 on /models).",
    },
    "huggingface": {
        "base_url": "https://router.huggingface.co/v1",
        "key_env": "HF_TOKEN",
        "note": "HF Inference Providers router; OpenAI-compatible, chat-only; model ids "
                "are org/model[:provider|:fastest|:cheapest].",
    },
    "neuralwatt": {
        "base_url": "https://api.neuralwatt.com/v1",
        "key_env": "NEURALWATT_API_KEY",
        "note": "Neuralwatt energy-aware inference; OpenAI-compatible chat. Base from "
                "docs/plugins — live-verify with `charon providers test`.",
    },
    "perplexity": {
        "base_url": "https://api.perplexity.ai",
        "key_env": "PERPLEXITY_API_KEY",
        "strip_v1": False,
        "note": "Perplexity (domain resolves, /models may 404; "
                "endpoint varies; if using, check strip_v1 setting).",
    },
}
