"""FT-CATALOG-SEED — shipped free-tier presets + catalog are present and correct.

FAIL-ON-REVERT:
* The three new hosted presets (github_models / featherless / ollama_cloud)
  resolve to their shipped base_url + key_env — revert or break one → RED.
* The catalog returns groq's 14400 rpd and mistral's monthly ~1e9 cap in the
  FT-CONFIG-SURFACE normalized shape — remove a seed row → RED.
* An unknown provider returns None (no seeded limits).
* Every seeded entry is NON-Anthropic (sg-never-anthropic).
"""
from __future__ import annotations

import pytest

from charon import providers
from charon.providers import is_anthropic_route
from charon.routing_policy.free_tier_catalog import (
    FREE_TIER_CATALOG,
    limits_for,
)

# The three free/cheap NON-Anthropic hosted presets FT-CATALOG-SEED ships.
_FT_SEED_PRESETS = {
    "github_models": ("https://models.inference.ai.azure.com", "GITHUB_TOKEN"),
    "featherless": ("https://api.featherless.ai/v1", "FEATHERLESS_API_KEY"),
    "ollama_cloud": ("https://ollama.com/v1", "OLLAMA_API_KEY"),
}


@pytest.mark.parametrize("name,expected", sorted(_FT_SEED_PRESETS.items()))
def test_ft_seed_preset_resolves(name: str, expected: tuple[str, str]) -> None:
    """Each new free-tier preset is importable/parseable with its shipped shape."""
    p = providers.resolve(name)
    assert p.base_url == expected[0]
    assert p.key_env == expected[1]
    assert p.wire == providers.WIRE_OPENAI
    assert not is_anthropic_route(provider=name), name


def test_ft_seed_featherless_32k_context_cap() -> None:
    """Featherless.ai's free tier carries a 32K session-context cap."""
    assert providers.resolve("featherless").max_context == 32768


def test_ft_seed_ollama_cloud_distinct_from_local() -> None:
    """Ollama.com cloud/turbo free tier is DISTINCT from the local 'ollama'
    preset (localhost:11434) — a hosted base + key vs a keyless localhost."""
    cloud = providers.resolve("ollama_cloud")
    local = providers.resolve("ollama")
    assert cloud.base_url.startswith("https://")
    assert local.base_url.startswith("http://localhost")
    assert cloud.base_url != local.base_url
    assert cloud.key_env is not None
    assert local.key_env is None


def test_catalog_groq_rpd_in_normalized_shape() -> None:
    """Groq's seeded rpd=14400 (8B tier) comes back in the normalized shape."""
    limits = limits_for("groq")
    assert limits is not None
    assert limits["rpd"] == 14400
    assert limits["rpm"] == 30
    assert limits["tpm"] == 6000


def test_catalog_mistral_monthly_cap() -> None:
    """Mistral's seeded monthly cap (~1e9) comes back in the normalized shape."""
    limits = limits_for("mistral")
    assert limits is not None
    assert limits["monthly_tokens"] == 1_000_000_000


def test_catalog_openrouter_and_cerebras() -> None:
    """The other two verified seeds: openrouter :free rpd=1000/rpm=20 and
    cerebras tpd=1_000_000/rpm=5."""
    openrouter = limits_for("openrouter")
    assert openrouter is not None
    assert openrouter["rpd"] == 1000
    assert openrouter["rpm"] == 20
    cerebras = limits_for("cerebras")
    assert cerebras is not None
    assert cerebras["tpd"] == 1_000_000
    assert cerebras["rpm"] == 5


def test_catalog_unknown_provider_returns_none() -> None:
    """An unknown provider has no seeded limits -> None (caller treats as
    unlimited).  Reverting a seed row to nothing also yields None."""
    assert limits_for("does-not-exist") is None
    assert limits_for("") is None


def test_catalog_projection_strips_metadata() -> None:
    """limits_for returns ONLY the FT-CONFIG-SURFACE normalized keys — never
    the metadata (verified / personal_only)."""
    limits = limits_for("groq")
    assert limits is not None
    assert "verified" not in limits
    assert "personal_only" not in limits
    assert set(limits) <= {"rpm", "rpd", "tpm", "tpd",
                           "weekly_tokens", "monthly_tokens", "reset"}


def test_catalog_unverified_placeholders_present() -> None:
    """GitHub Models / Featherless / Ollama.com are known to the catalog as
    placeholders flagged verified=False until PRICING-LIMITS-CHECKER confirms
    their numbers — they project to an empty (not None) block."""
    for name in ("github_models", "featherless", "ollama_cloud"):
        assert name in FREE_TIER_CATALOG, name
        assert FREE_TIER_CATALOG[name]["verified"] is False, name
        assert limits_for(name) == {}


def test_catalog_every_entry_non_anthropic() -> None:
    """sg-never-anthropic: no seeded provider (catalog row or new preset) is
    an Anthropic/Claude route."""
    for name in FREE_TIER_CATALOG:
        assert not is_anthropic_route(provider=name), name
    for name in _FT_SEED_PRESETS:
        assert not is_anthropic_route(provider=name), name


def test_catalog_personal_only_free_tiers_marked() -> None:
    """Every seeded free tier is a personal-only free tier."""
    for name, limits in FREE_TIER_CATALOG.items():
        assert limits.get("personal_only") is True, name
