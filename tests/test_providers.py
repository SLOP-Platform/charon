"""P3 — provider presets + resolution, and models referencing a provider."""
from __future__ import annotations

import pytest

from charon import gateway, providers


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
    assert cfg.routes["glm"].strip_v1 is False           # zai preset quirk
    assert cfg.routes["n"].upstream_base == "http://my-nano/v1"  # override applied
