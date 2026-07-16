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


def test_huggingface_neuralwatt_presets_present():
    # config-only OpenAI-compatible presets (no adapter): resolve, /v1 base, key_env set
    for n, key in (("huggingface", "HF_TOKEN"), ("neuralwatt", "NEURALWATT_API_KEY")):
        p = providers.resolve(n)
        assert p.base_url.endswith("/v1"), n
        assert p.key_env == key, n
    assert providers.resolve("huggingface").base_url == "https://router.huggingface.co/v1"
    assert providers.resolve("neuralwatt").base_url == "https://api.neuralwatt.com/v1"


def test_opencode_zen_go_presets_present():
    # SR-12: lock in the opencode-zen / opencode-go presets (both on the zen key)
    p_zen = providers.resolve("opencode-zen")
    assert p_zen.base_url == "https://opencode.ai/zen/v1"
    assert p_zen.key_env == "OPENCODE_ZEN_KEY"
    p_go = providers.resolve("opencode-go")
    assert p_go.base_url == "https://opencode.ai/zen/go/v1"
    assert p_go.key_env == "OPENCODE_ZEN_KEY"


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


def test_resolve_falls_back_to_persisted_config_for_non_preset_provider(monkeypatch, tmp_path):
    """A provider added via `providers add` (not a built-in PRESETS entry) is
    persisted to providers.json but has no explicit override at the call site —
    e.g. the `providers test <name>` CLI subcommand, which previously raised
    "unknown provider ... not a built-in preset" for exactly this case (the real
    routing path in discover.py already reads this persisted config; resolve()
    did not). resolve() must fall back to the persisted `[providers.<name>]`
    entry when name isn't a preset and no explicit override is given."""
    from charon import config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("deepinfra", base_url="https://api.deepinfra.com/v1/openai",
                        key_env="DEEPINFRA_API_KEY")
    assert "deepinfra" not in providers.PRESETS

    p = providers.resolve("deepinfra")
    assert p.base_url == "https://api.deepinfra.com/v1/openai"
    assert p.key_env == "DEEPINFRA_API_KEY"


def test_resolve_explicit_override_still_wins_over_persisted_config(monkeypatch, tmp_path):
    from charon import config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("deepinfra", base_url="https://api.deepinfra.com/v1/openai",
                        key_env="DEEPINFRA_API_KEY")

    p = providers.resolve("deepinfra", {"base_url": "http://override/v1"})
    assert p.base_url == "http://override/v1"
    assert p.key_env == "DEEPINFRA_API_KEY"  # non-overridden fields still fall back


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


# ── SR-5: pricing extraction unit + guards ────────────────────────

def test_extract_pricing_stores_per_token_verbatim():
    # OpenRouter quotes pricing per TOKEN; the value is stored raw (no /1e6).
    entry: dict = {}
    providers._extract_pricing(
        {"pricing": {"prompt": "0.0000025", "completion": "0.00001"}}, entry)
    assert entry["cost_input"] == 0.0000025
    assert entry["cost_output"] == 0.00001


def test_extract_pricing_accepts_numeric_and_zero():
    entry: dict = {}
    providers._extract_pricing({"pricing": {"prompt": 0.0, "completion": 3e-7}}, entry)
    assert entry["cost_input"] == 0.0
    assert entry["cost_output"] == 3e-7


def test_extract_pricing_rejects_nonfinite_and_negative():
    for bad in ("nan", "inf", "-inf", "-5", float("nan"), float("inf"), -0.01):
        entry: dict = {}
        providers._extract_pricing({"pricing": {"prompt": bad}}, entry)
        assert "cost_input" not in entry, bad


def test_extract_pricing_rejects_garbage_string():
    entry: dict = {}
    providers._extract_pricing({"pricing": {"prompt": "free!"}}, entry)
    assert "cost_input" not in entry


def test_extract_pricing_no_pricing_field():
    entry: dict = {}
    providers._extract_pricing({"id": "x"}, entry)
    assert entry == {}


# ── PROVIDER-URL-HELPER: shared endpoint URL construction ──────────
#
# ``models_url`` / ``chat_url`` are the ONE place that knows the /models and
# /chat/completions suffixes. The guard below pins their exact resolved URL for
# every provider preset (hardcoded strings, including the nested-path bases like
# opencode-zen / opencode-go / zai) so the dedup refactor can't silently change
# any provider's actual endpoint — the "no behavior change" correctness bar.

# Expected (base.rstrip("/") + suffix) for every preset that shipped BEFORE the
# refactor — this is the regression guard the acceptance criteria require.
# Includes the nested-path bases (opencode-zen, opencode-go, zai, groq,
# cline-pass, fireworks) that a naive join would mangle.
_EXPECTED_MODELS_URLS = {
    "anthropic": "https://api.anthropic.com/models",
    "chutes": "https://llm.chutes.ai/v1/models",
    "cline-pass": "https://api.cline.bot/api/v1/models",
    "cohere": "https://api.cohere.ai/v1/models",
    "deepseek": "https://api.deepseek.com/v1/models",
    "fireworks": "https://api.fireworks.ai/inference/v1/models",
    "groq": "https://api.groq.com/openai/v1/models",
    "huggingface": "https://router.huggingface.co/v1/models",
    "jan": "http://localhost:1337/v1/models",
    "lmstudio": "http://localhost:1234/v1/models",
    "local": "http://localhost:1234/v1/models",
    "mistral": "https://api.mistral.ai/v1/models",
    "nanogpt": "https://nano-gpt.com/api/v1/models",
    "neuralwatt": "https://api.neuralwatt.com/v1/models",
    "ollama": "http://localhost:11434/v1/models",
    "openai": "https://api.openai.com/v1/models",
    "opencode-go": "https://opencode.ai/zen/go/v1/models",
    "opencode-zen": "https://opencode.ai/zen/v1/models",
    "openrouter": "https://openrouter.ai/api/v1/models",
    "perplexity": "https://api.perplexity.ai/models",
    "replicate": "https://api.replicate.com/v1/models",
    "sambanova": "https://api.sambanova.ai/v1/models",
    "together": "https://api.together.xyz/v1/models",
    "vllm": "http://localhost:8000/v1/models",
    "xai": "https://api.x.ai/v1/models",
    "zai": "https://api.z.ai/api/paas/v4/models",
}

_EXPECTED_CHAT_URLS = {
    "anthropic": "https://api.anthropic.com/chat/completions",
    "chutes": "https://llm.chutes.ai/v1/chat/completions",
    "cline-pass": "https://api.cline.bot/api/v1/chat/completions",
    "cohere": "https://api.cohere.ai/v1/chat/completions",
    "deepseek": "https://api.deepseek.com/v1/chat/completions",
    "fireworks": "https://api.fireworks.ai/inference/v1/chat/completions",
    "groq": "https://api.groq.com/openai/v1/chat/completions",
    "huggingface": "https://router.huggingface.co/v1/chat/completions",
    "jan": "http://localhost:1337/v1/chat/completions",
    "lmstudio": "http://localhost:1234/v1/chat/completions",
    "local": "http://localhost:1234/v1/chat/completions",
    "mistral": "https://api.mistral.ai/v1/chat/completions",
    "nanogpt": "https://nano-gpt.com/api/v1/chat/completions",
    "neuralwatt": "https://api.neuralwatt.com/v1/chat/completions",
    "ollama": "http://localhost:11434/v1/chat/completions",
    "openai": "https://api.openai.com/v1/chat/completions",
    "opencode-go": "https://opencode.ai/zen/go/v1/chat/completions",
    "opencode-zen": "https://opencode.ai/zen/v1/chat/completions",
    "openrouter": "https://openrouter.ai/api/v1/chat/completions",
    "perplexity": "https://api.perplexity.ai/chat/completions",
    "replicate": "https://api.replicate.com/v1/chat/completions",
    "sambanova": "https://api.sambanova.ai/v1/chat/completions",
    "together": "https://api.together.xyz/v1/chat/completions",
    "vllm": "http://localhost:8000/v1/chat/completions",
    "xai": "https://api.x.ai/v1/chat/completions",
    "zai": "https://api.z.ai/api/paas/v4/chat/completions",
}


def test_models_url_preserves_all_preset_endpoints_exactly():
    """No-behavior-change guard: for EVERY preset in PRESETS, models_url(base)
    must equal the exact string the old inline `base.rstrip("/") + "/models"`
    produced — including the nested-path bases (opencode-zen, opencode-go, zai,
    groq, cline-pass, fireworks) that a naive join could drop or double-slash."""
    missing = set(providers.PRESETS) - set(_EXPECTED_MODELS_URLS)
    extra = set(_EXPECTED_MODELS_URLS) - set(providers.PRESETS)
    assert not missing, f"preset(s) without a pinned models_url expectation: {sorted(missing)}"
    assert not extra, f"stale expectation(s) for a removed preset: {sorted(extra)}"
    for name, preset in providers.PRESETS.items():
        got = providers.models_url(preset.base_url)
        exp = _EXPECTED_MODELS_URLS[name]
        assert got == exp, f"{name}: models_url drifted\n  got: {got!r}\n  exp: {exp!r}"


def test_chat_url_preserves_all_preset_endpoints_exactly():
    """No-behavior-change guard for chat_url — mirrors the models_url guard.
    Catches an accidental `/v1/chat/completions` vs `/chat/completions` drift on
    the nested-path bases (opencode-zen, opencode-go, zai)."""
    missing = set(providers.PRESETS) - set(_EXPECTED_CHAT_URLS)
    extra = set(_EXPECTED_CHAT_URLS) - set(providers.PRESETS)
    assert not missing, f"preset(s) without a pinned chat_url expectation: {sorted(missing)}"
    assert not extra, f"stale expectation(s) for a removed preset: {sorted(extra)}"
    for name, preset in providers.PRESETS.items():
        got = providers.chat_url(preset.base_url)
        exp = _EXPECTED_CHAT_URLS[name]
        assert got == exp, f"{name}: chat_url drifted\n  got: {got!r}\n  exp: {exp!r}"


def test_models_url_keeps_nested_path_segments():
    """A base that already ends in a path segment (opencode-zen's
    .../zen/v1) must keep every segment — not collapse to .../zen/models or
    produce a double slash. This is the specific edge case the dedup was
    introduced to handle consistently."""
    assert providers.models_url("https://opencode.ai/zen/v1") == "https://opencode.ai/zen/v1/models"
    assert providers.models_url("https://opencode.ai/zen/go/v1") == "https://opencode.ai/zen/go/v1/models"
    assert providers.models_url("https://api.z.ai/api/paas/v4") == "https://api.z.ai/api/paas/v4/models"


def test_chat_url_strips_trailing_slash_once():
    """A base with a trailing slash resolves to a single slash before the suffix
    (no `//models`), and a base without one is untouched."""
    assert providers.chat_url("https://api.example.com/v1/") == "https://api.example.com/v1/chat/completions"
    assert providers.chat_url("https://api.example.com/v1") == "https://api.example.com/v1/chat/completions"
    assert "//chat/completions" not in providers.chat_url("https://api.example.com/v1/")


def test_models_url_rejects_link_local_and_metadata_hosts():
    """The SSRF guard survived the move from config.py's inline check to the
    shared helper — a link-local (169.254.x) or GCP metadata base is refused,
    not silently constructed into a probeable URL. This is the security
    regression guard the acceptance criteria require."""
    with pytest.raises(ValueError):
        providers.models_url("http://169.254.169.254/latest/meta-data/")
    with pytest.raises(ValueError):
        providers.models_url("http://metadata.google.internal/computeMetadata/v1/")


def test_chat_url_rejects_link_local_and_metadata_hosts():
    """Same SSRF guard applies to chat_url — a cloud-metadata host can't be
    turned into a /chat/completions URL (where an Authorization Bearer would
    ride). The guard moved intact, not just on the /models path."""
    with pytest.raises(ValueError):
        providers.chat_url("http://169.254.169.254/")
    with pytest.raises(ValueError):
        providers.chat_url("http://metadata.google.internal/")


def test_validate_base_url_rejects_non_https_scheme():
    """A non-http(s) base (ftp/file/gopher) is refused — the SSRF-adjacent scheme
    check moved with the host check."""
    for bad in ("ftp://example.com", "file:///etc/passwd", "gopher://x"):
        with pytest.raises(ValueError):
            providers.validate_base_url(bad)


def test_validate_base_url_accepts_http_and_https_and_strips_trailing_slash():
    """http (localhost) and https are both valid; trailing slashes are stripped
    so the caller can safely append. Local providers (ollama/lmstudio/vllm) ship
    http://localhost bases and must still resolve."""
    assert providers.validate_base_url("https://api.example.com/v1/") == "https://api.example.com/v1"
    assert providers.validate_base_url("http://localhost:1234/v1") == "http://localhost:1234/v1"
    assert providers.validate_base_url("https://x.example.com///") == "https://x.example.com"


def test_join_endpoint_single_slash_no_path_drop():
    """join_endpoint guarantees exactly one slash between base and path, never
    drops a path segment, and tolerates a path with or without a leading slash."""
    assert providers.join_endpoint("https://x.example.com/v1", "models") == "https://x.example.com/v1/models"
    assert providers.join_endpoint("https://x.example.com/v1", "/models") == "https://x.example.com/v1/models"
    assert providers.join_endpoint("https://x.example.com/v1/", "models") == "https://x.example.com/v1/models"
    assert providers.join_endpoint("https://x.example.com/", "/chat/completions") == "https://x.example.com/chat/completions"

