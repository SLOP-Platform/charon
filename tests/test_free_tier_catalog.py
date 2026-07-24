"""FT-CATALOG-SEED — shipped SEED of free-tier limits and the new
hosted presets for GitHub Models / Featherless.ai / Ollama.com cloud.

FAIL-ON-REVERT: each test here pins a specific row of the seed (a
provider's preset, a catalog entry, or the "unknown returns None"
contract). Reverting any one of them flips the matching test red —
catching a missing vendor key, a removed seed row, or a broken
catalog accessor before it reaches production.
"""
from __future__ import annotations

from charon import providers
from charon.routing_policy.free_tier_catalog import (
    FREE_TIER_CATALOG,
    get_limits,
)
from charon.routing_policy.free_tier_catalog import (
    providers as catalog_providers,
)

# ── new hosted presets (provider_presets/hosted.py) ─────────────────────────

def test_github_models_preset_present_and_resolves():
    p = providers.resolve("github_models")
    assert p.base_url == "https://models.inference.ai.azure.com"
    assert p.key_env == "GITHUB_TOKEN"
    # non-Anthropic wire is the default; spot-check that resolve() didn't
    # accidentally promote it (revert a preset key → resolve() raises).
    assert p.wire == "openai"


def test_featherless_preset_present_and_resolves():
    p = providers.resolve("featherless")
    assert p.base_url == "https://api.featherless.ai/v1"
    assert p.key_env == "FEATHERLESS_API_KEY"
    # 32K session-context cap lives on the preset, not the catalog.
    assert p.max_context == 32_768


def test_ollama_cloud_preset_present_and_distinct_from_local_ollama():
    cloud = providers.resolve("ollama_cloud")
    local = providers.resolve("ollama")
    assert cloud.base_url == "https://ollama.com/v1"
    assert cloud.key_env == "OLLAMA_API_KEY"
    # Distinct: the local ollama is unauthenticated and on localhost.
    assert local.base_url == "http://localhost:11434/v1"
    assert local.key_env is None
    assert cloud.base_url != local.base_url


# ── catalog: known provider rows return the normalized shape ───────────────

def test_groq_rpd_14400_in_normalized_shape():
    limits = get_limits("groq")
    assert limits is not None
    assert limits["rpd"] == 14_400
    assert limits["rpm"] == 30
    assert limits["tpm"] == 6_000
    # Shape: every key the quota tracker / FT-CONFIG-SURFACE consumer
    # may ask for must be present (None is fine; missing key is not).
    for k in ("rpm", "rpd", "tpm", "tpd", "weekly", "monthly",
              "reset", "verified", "personal_only", "note"):
        assert k in limits, f"missing normalized key {k!r}"
    # Reset kind is one of the documented values.
    assert limits["reset"] in {"rolling", "calendar", "weekly", "monthly"}


def test_mistral_monthly_cap_in_normalized_shape():
    limits = get_limits("mistral")
    assert limits is not None
    assert limits["monthly"] == 1_000_000_000
    assert limits["reset"] == "monthly"
    # The other windows are not advertised — they're None, not missing.
    assert limits["rpm"] is None
    assert limits["rpd"] is None


def test_openrouter_personal_only_and_free_only_routing():
    limits = get_limits("openrouter")
    assert limits is not None
    assert limits["rpd"] == 1_000
    assert limits["rpm"] == 20
    assert limits["personal_only"] is True


def test_cerebras_tpd_one_million():
    limits = get_limits("cerebras")
    assert limits is not None
    assert limits["tpd"] == 1_000_000
    assert limits["rpm"] == 5


# ── catalog: unverified placeholders for the new providers ─────────────────

def test_github_models_catalog_placeholder_unverified():
    entry = FREE_TIER_CATALOG.get("github_models")
    assert entry is not None, "github_models seed row missing"
    assert entry["verified"] is False
    assert entry["personal_only"] is True
    # Normalized shape still complete — the placeholders are explicit
    # "we don't know" (None), not absent keys.
    for k in ("rpm", "rpd", "tpm", "tpd", "weekly", "monthly", "reset", "note"):
        assert k in entry, f"missing normalized key {k!r}"


def test_featherless_catalog_placeholder_unverified():
    entry = FREE_TIER_CATALOG.get("featherless")
    assert entry is not None, "featherless seed row missing"
    assert entry["verified"] is False


def test_ollama_cloud_catalog_placeholder_unverified():
    entry = FREE_TIER_CATALOG.get("ollama_cloud")
    assert entry is not None, "ollama_cloud seed row missing"
    assert entry["verified"] is False


# ── catalog: contract — unknown provider returns None ───────────────────────

def test_unknown_provider_returns_none():
    # A name the seed doesn't know about: not an error, just "no seed;
    # the live config or PRICING-LIMITS-CHECKER is the authority".
    assert get_limits("definitely-not-a-real-provider-xyz") is None


def test_empty_provider_returns_none():
    assert get_limits("") is None


# ── catalog: non-mutation contract ─────────────────────────────────────────

def test_get_limits_returns_defensive_copy():
    limits = get_limits("groq")
    assert limits is not None
    limits["rpd"] = -1  # must not bleed into the seed
    assert FREE_TIER_CATALOG["groq"]["rpd"] == 14_400
    # and a second call still returns the original
    again = get_limits("groq")
    assert again is not None
    assert again["rpd"] == 14_400


# ── catalog: provider list reflects the seed scope ─────────────────────────

def test_providers_list_includes_all_seeded_entries():
    seeded = set(catalog_providers())
    expected = {"groq", "openrouter", "cerebras", "mistral",
                "github_models", "featherless", "ollama_cloud"}
    assert expected <= seeded, f"missing from seed: {expected - seeded}"
    # And never the Anthropic provider (sg-never-anthropic).
    assert "anthropic" not in seeded


# ── catalog: every entry is non-Anthropic (sg-never-anthropic) ─────────────

def test_no_anthropic_entry_in_seed():
    assert "anthropic" not in FREE_TIER_CATALOG
    for name, entry in FREE_TIER_CATALOG.items():
        # If a future ticket ever adds an Anthropic-shaped entry, force
        # the reviewer to think about it: a guard fails loudly rather
        # than silently letting an Anthropic "free tier" leak in.
        assert "anthropic" not in name.lower() or entry.get("verified") is True, (
            f"unexpected anthropic entry in free-tier seed: {name}")


# ── catalog: shape parity with the quota tracker ───────────────────────────

def test_seed_shape_accepted_by_quota_tracker():
    """The seed must be consumable by quota.QuotaTracker unchanged —
    the same consumer the FT-CONFIG-SURFACE config path feeds."""
    from charon.quota import QuotaTracker

    limits = {name: {k: entry[k] for k in ("rpm", "tpm", "rpd", "tpd")
                     if k in entry and entry[k] is not None}
              for name, entry in FREE_TIER_CATALOG.items()}
    # No entry has all-None limits for the tracker windows (the only
    # shape QuotaTracker can act on); constructing it must not raise.
    tracker = QuotaTracker(limits=limits)
    # And a known provider with limits returns False (not blocked yet).
    assert tracker.should_skip("groq", est_tokens=0) is False
