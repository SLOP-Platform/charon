"""F29-PROVIDERS-DATA: verify PRESETS assembly from category modules.

FAIL-ON-REVERT: if the registry merge is broken or a category module is
dropped, these tests go RED — catching missing vendor keys or absent presets
before they reach production.
"""
from __future__ import annotations

from charon import providers
from charon.provider_presets import MERGED_RAW_DATA as _RAW

# The 26 vendor keys the original PRESETS dict held before the refactor.
_KNOWN_KEYS = frozenset({
    "anthropic",
    "opencode-zen", "opencode-go",
    "openrouter", "cline-pass",
    "nanogpt", "zai",
    "deepseek", "chutes", "groq", "together", "mistral",
    "fireworks", "sambanova", "replicate", "xai", "cohere", "openai",
    "huggingface", "neuralwatt",
    "perplexity", "github_models", "featherless", "ollama_cloud",
    "lmstudio", "jan", "ollama", "vllm", "local",
})


def test_all_original_keys_present():
    """Every key that existed before the refactor must still be in PRESETS."""
    assert len(providers.PRESETS) == len(_KNOWN_KEYS)
    assert providers.PRESETS.keys() == _KNOWN_KEYS


def test_providers_presets_derived_from_registry():
    """providers.PRESETS is derived from MERGED_RAW_DATA."""
    assert providers.PRESETS.keys() == _RAW.keys()


def test_spot_check_anthropic():
    p = providers.resolve("anthropic")
    assert p.base_url == "https://api.anthropic.com"
    assert p.key_env == "ANTHROPIC_API_KEY"
    assert p.strip_v1 is False
    assert p.wire == "anthropic"


def test_spot_check_opencode_go():
    p = providers.resolve("opencode-go")
    assert p.base_url == "https://opencode.ai/zen/go/v1"
    assert p.key_env == "OPENCODE_ZEN_KEY"


def test_spot_check_openrouter():
    p = providers.resolve("openrouter")
    assert p.base_url == "https://openrouter.ai/api/v1"
    assert p.key_env == "OPENROUTER_API_KEY"
    assert p.downgrade_prone is True


def test_spot_check_cline_pass():
    p = providers.resolve("cline-pass")
    assert p.base_url == "https://api.cline.bot/api/v1"
    assert p.key_env == "CLINE_PASS_API_KEY"
    assert p.adapter == "cline"


def test_spot_check_local_servers():
    for n in ("lmstudio", "jan", "ollama", "vllm", "local"):
        p = providers.resolve(n)
        assert p.key_env is None, n
        assert p.base_url.startswith("http://localhost"), n


def test_spot_check_deepseek():
    p = providers.resolve("deepseek")
    assert p.base_url == "https://api.deepseek.com/v1"
    assert p.key_env == "DEEPSEEK_API_KEY"


def test_spot_check_openai():
    p = providers.resolve("openai")
    assert p.base_url == "https://api.openai.com/v1"
    assert p.key_env == "OPENAI_API_KEY"


def test_spot_check_perplexity():
    p = providers.resolve("perplexity")
    assert p.base_url == "https://api.perplexity.ai"
    assert p.strip_v1 is False


def test_spot_check_zai():
    p = providers.resolve("zai")
    assert p.base_url == "https://api.z.ai/api/paas/v4"
    assert p.strip_v1 is True


def test_spot_check_neuralwatt():
    p = providers.resolve("neuralwatt")
    assert p.base_url == "https://api.neuralwatt.com/v1"
    assert p.key_env == "NEURALWATT_API_KEY"


# ── NEW PRESET APPEARS IN PRESETS WITH ZERO EDIT TO MACHINERY ──────

def test_new_preset_appears_without_edit_to_providers_machinery():
    """A preset injected into a category module appears in PRESETS with
    zero changes to providers.py's machinery (resolve, list_models, etc.)."""
    import importlib

    import charon.provider_presets as ppkg
    import charon.provider_presets.hosted as hosted_mod

    # Inject a synthetic preset as raw data into the category module
    hosted_mod.CATEGORY_PRESETS_DATA["__test_new_vendor"] = {
        "base_url": "https://test-new.example.com/v1",
        "key_env": "__TEST_KEY",
        "note": "Injected by test_new_preset_appears_without_edit_to_providers_machinery",
    }

    # Reload the registry + providers to re-merge
    importlib.reload(ppkg)
    importlib.reload(providers)

    assert "__test_new_vendor" in providers.PRESETS
    p = providers.resolve("__test_new_vendor")
    assert p.base_url == "https://test-new.example.com/v1"
    assert p.key_env == "__TEST_KEY"

    # Cleanup — remove the synthetic key and reload
    del hosted_mod.CATEGORY_PRESETS_DATA["__test_new_vendor"]
    importlib.reload(ppkg)
    importlib.reload(providers)
    assert "__test_new_vendor" not in providers.PRESETS
