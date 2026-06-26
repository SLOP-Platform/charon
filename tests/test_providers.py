"""P3 — provider presets + resolution, and models referencing a provider."""
from __future__ import annotations

import pytest

from charon import gateway, providers


def test_all_presets_have_valid_http_base():
    from urllib.parse import urlsplit
    for name, p in providers.PRESETS.items():
        parts = urlsplit(p.base_url)
        assert parts.scheme in ("http", "https") and parts.netloc, name


def test_hosted_presets_present():
    for n in ("deepseek", "chutes", "groq", "together", "mistral"):
        assert n in providers.PRESETS and providers.PRESETS[n].key_env


def test_new_hosted_presets_present():
    for n in ("fireworks", "sambanova", "replicate", "xai", "cohere", "openai"):
        assert n in providers.PRESETS and providers.PRESETS[n].key_env


def test_preset_resolves_known_provider():
    p = providers.resolve("openrouter")
    assert p.base_url == "https://openrouter.ai/api/v1"
    assert p.key_env == "OPENROUTER_API_KEY"


def test_overrides_apply_over_preset():
    p = providers.resolve("nanogpt", {"base_url": "http://my-nano/v1", "key_env": "NK"})
    assert p.base_url == "http://my-nano/v1" and p.key_env == "NK"


def test_unknown_provider_without_base_url_errors():
    with pytest.raises(ValueError):
        providers.resolve("does-not-exist")


def test_unknown_provider_with_base_url_ok():
    p = providers.resolve("my-local", {"base_url": "http://localhost:9/v1"})
    assert p.base_url == "http://localhost:9/v1" and p.key_env is None


def test_zai_preset_strips_v1():
    # live-confirmed: zai chat is /api/paas/v4/chat/completions, so the client's
    # /v1 prefix must be stripped (strip_v1 True) — NOT forwarded as /v4/v1/...
    assert providers.resolve("zai").strip_v1 is True


def test_perplexity_preset_does_not_strip_v1():
    # Perplexity endpoint path varies; strip_v1=False avoids double-stripping
    assert providers.resolve("perplexity").strip_v1 is False


def test_local_servers_have_no_auth():
    for n in ("lmstudio", "jan", "ollama", "vllm", "local"):
        assert n in providers.PRESETS and providers.PRESETS[n].key_env is None


def test_new_vendor_bases_valid():
    # Verify new hosted providers have valid base URLs (tested live 2026-06-26)
    assert providers.resolve("sambanova").base_url == "https://api.sambanova.ai/v1"
    assert providers.resolve("fireworks").base_url == "https://api.fireworks.ai/inference/v1"
    assert providers.resolve("xai").base_url == "https://api.x.ai/v1"


def test_openai_preset_exists():
    p = providers.resolve("openai")
    assert p.base_url == "https://api.openai.com/v1"
    assert p.key_env == "OPENAI_API_KEY"


def test_model_referencing_provider_resolves_route(monkeypatch, tmp_path):
    monkeypatch.setenv("MY_OR_KEY", "sekret")
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[providers.openrouter]\nkey_env = "MY_OR_KEY"\n\n'
        '[providers.nanogpt]\nbase_url = "http://my-nano/v1"\nkey_env = "NK"\n\n'
        '[models."qwen"]\nprovider = "openrouter"\n'
        'upstream_model = "qwen/coder:free"\nfree = true\n\n'
        '[models."glm"]\nprovider = "zai"\n\n'
        '[models."n"]\nprovider = "nanogpt"\n'
    )
    cfg = gateway.load_config(toml_path=toml)
    qwen = cfg.routes["qwen"]
    assert qwen.upstream_base == "https://openrouter.ai/api/v1"
    assert qwen.api_key == "sekret" and qwen.upstream_model == "qwen/coder:free"
    assert qwen.provider == "openrouter" and qwen.strip_v1 is True
    assert cfg.routes["glm"].strip_v1 is True            # zai preset quirk (strips /v1)
    assert cfg.routes["n"].upstream_base == "http://my-nano/v1"  # override applied
