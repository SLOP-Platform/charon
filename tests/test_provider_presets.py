"""F29-PROVIDERS-DATA: verify PRESETS assembly from category modules.

FAIL-ON-REVERT: if the registry merge is broken or a category module is
dropped, these tests go RED — catching missing vendor keys or absent presets
before they reach production.

FIX-FT-CATALOG-CONTRACT-TESTS: FT-CATALOG-SEED (PR #135) is a SEPARATE branch
that adds three more vendor presets (github_models / featherless / ollama_cloud)
to src/charon/provider_presets/hosted.py. The 26 original keys are still the
floor for "no preset was dropped"; the 3 new ones are the expected additions.
Until that branch lands, the assertions below are forward-compatible: the
original 26 must all be present (FAIL-ON-REVERT preserved), the count must be
>= 26, and the spot-check tests for the 3 new presets skip cleanly when their
preset is not yet in PRESETS. Once #135 merges, the count check becomes
strict again (29 == 29) and the 3 new spot-checks stop skipping — both branches
landing on master yields a fully-asserted 29-preset registry.
"""
from __future__ import annotations

import pytest

from charon import providers
from charon.provider_presets import MERGED_RAW_DATA as _RAW

# The 26 vendor keys the original PRESETS dict held before the FT-CATALOG-SEED
# (PR #135) refactor.
_ORIGINAL_KEYS = frozenset({
    "anthropic",
    "opencode-zen", "opencode-go",
    "openrouter", "cline-pass",
    "nanogpt", "zai",
    "deepseek", "chutes", "groq", "together", "mistral",
    "fireworks", "sambanova", "replicate", "xai", "cohere", "openai",
    "huggingface", "neuralwatt",
    "perplexity",
    "lmstudio", "jan", "ollama", "vllm", "local",
})

# The 3 vendor keys FT-CATALOG-SEED (PR #135) adds. Declared here so the
# post-#135 state is documented in the test file even before that PR lands.
_FT_CATALOG_SEED_KEYS = frozenset({
    "github_models",
    "featherless",
    "ollama_cloud",
})

# Full expected set once #135 has landed.
_KNOWN_KEYS = _ORIGINAL_KEYS | _FT_CATALOG_SEED_KEYS

# Minimum count expected without FT-CATALOG-SEED merged; once #135 lands the
# strict equality assertion below takes over (the gate is the same in both
# states — original 26 must always be present, so a dropped category module
# still goes RED).
_MIN_KEYS = len(_ORIGINAL_KEYS)
_FULL_KEYS = len(_KNOWN_KEYS)


def test_all_original_keys_present():
    """Every key that existed before the refactor must still be in PRESETS.

    Forward-compatible with FT-CATALOG-SEED (PR #135): the 26 originals are a
    subset of PRESETS (FAIL-ON-REVERT preserved), and the count is at least 26.
    If the 3 new keys are already merged the count is 29; if not, the count is
    still 26 and the strict equality branch below re-arms itself the moment
    they land. Either way: dropping an original preset goes RED.
    """
    present = frozenset(providers.PRESETS.keys())
    missing = _ORIGINAL_KEYS - present
    assert not missing, f"original presets lost: {sorted(missing)}"
    assert len(present) >= _MIN_KEYS, (
        f"PRESETS shrank below the original 26: got {len(present)}")
    if _FT_CATALOG_SEED_KEYS.issubset(present):
        assert present == _KNOWN_KEYS, (
            f"FT-CATALOG-SEED landed but PRESETS != expected 29: extra="
            f"{sorted(present - _KNOWN_KEYS)}, missing={sorted(_KNOWN_KEYS - present)}")
        assert len(present) == _FULL_KEYS


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


# ── FT-CATALOG-SEED (PR #135) WIRE-SHAPE FIXTURES ───────────────────
# These three presets land in src/charon/provider_presets/hosted.py on the
# feat/ft-catalog-seed branch. Declared here so the contract test tracks the
# expected wire shape (base_url / key_env / strip_v1 / adapter / max_context)
# the moment the PR merges. The tests skip cleanly when the preset is not
# yet registered — see test_all_original_keys_present for the floor check.

def _require_preset(name: str):
    p = providers.PRESETS.get(name)
    if p is None:
        pytest.skip(f"{name}: preset not yet in providers.PRESETS "
                    "(FT-CATALOG-SEED PR #135 not yet merged)")
    return p


def test_spot_check_github_models():
    """GitHub Models (Azure-hosted inference, GitHub-issued token,
    OpenAI-compatible chat; base verified live)."""
    p = _require_preset("github_models")
    assert p.base_url == "https://models.inference.ai.azure.com"
    assert p.key_env == "GITHUB_TOKEN"
    assert p.strip_v1 is False


def test_spot_check_featherless():
    """Featherless.ai — OpenAI-compatible chat; free tier carries a 32K
    session-context cap surfaced via max_context."""
    p = _require_preset("featherless")
    assert p.base_url == "https://api.featherless.ai/v1"
    assert p.key_env == "FEATHERLESS_API_KEY"
    assert getattr(p, "max_context", None) == 32768


def test_spot_check_ollama_cloud():
    """Ollama.com hosted cloud (free/turbo tier) — DISTINCT from the LOCAL
    'ollama' preset in local.py (localhost:11434). OpenAI-compatible; key
    required even on the free tier."""
    p = _require_preset("ollama_cloud")
    assert p.base_url == "https://ollama.com/v1"
    assert p.key_env == "OLLAMA_API_KEY"
    # Local 'ollama' uses http://localhost:11434/v1 with no key_env; the
    # cloud preset must not be conflated with the local one.
    assert p.base_url != "http://localhost:11434/v1"
    assert p.key_env is not None


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
