"""Tests proving that litellm pricing enrichment (#266) produces correct
pool ordering — cheaper direct legs rank ahead of aggregator legs that carry
a platform markup.

The live defect (2026-08-10): $30.86/day through openrouter (cost_rank 50,
~5% markup) because deepseek-direct (cost_rank 8) had no pricing, so
derived_cost_rank collapsed both to the neutral 1000 and the hand-authored
order governed.
"""
from __future__ import annotations

import pytest

from charon.proxy_server import UpstreamRoute
from charon.routing_policy import build_routes_and_pools


def _try_import_litellm() -> bool:
    try:
        import litellm  # noqa: F401
        return True
    except ImportError:
        return False


# A minimal registry mimicking the live pool shape for deepseek-v4-flash.
# Order: nv(free) -> go(DISABLED) -> ng(rank 800) -> hf(parked) -> or(rank 50) -> ds(rank 8)
# With enrichment, ds (1.4e-7/2.8e-7, rank ~18) sorts BEFORE or (unpriced, rank 1000).
_LIVE_DS_FLASH_REGISTRY: dict[str, dict] = {
    "dsv4-flash-free": {
        "provider": "groq",
        "upstream_model": "deepseek-v4-flash-free",
        "free": True,
    },
    "dsv4-flash-go": {
        "provider": "groq",
        "upstream_model": "deepseek-v4-flash",
        "enabled": False,
    },
    "dsv4-flash-ng": {
        "provider": "nanogpt",
        "upstream_model": "deepseek-v4-flash",
    },
    "dsv4-flash-hf": {
        "provider": "huggingface",
        "upstream_model": "deepseek-v4-flash",
    },
    "dsv4-flash-or": {
        "provider": "openrouter",
        "upstream_model": "openai/deepseek-v4-flash",
    },
    "dsv4-flash-ds": {
        "provider": "deepseek",
        "upstream_model": "deepseek-v4-flash",
    },
}

_LIVE_DS_FLASH_POOL = {
    "deepseek-v4-flash": [
        "dsv4-flash-free",
        "dsv4-flash-go",
        "dsv4-flash-ng",
        "dsv4-flash-hf",
        "dsv4-flash-or",
        "dsv4-flash-ds",
    ],
}


def _providers_in_order(pools: dict, vid: str) -> list[str]:
    return [r.provider or r.label for r in pools.get(vid, [])]


@pytest.mark.skipif(not _try_import_litellm(), reason="litellm not installed")
def test_deepseek_direct_ahead_of_openrouter_after_enrichment():
    """With litellm enrichment (PR #266), deepseek-direct v4-flash gets
    input=1.4e-7/output=2.8e-7 from litellm.model_cost. OpenRouter has no
    litellm price for deepseek-v4-flash — it stays 1000. Deepseek-direct
    (rank ~18) sorts BEFORE openrouter (rank 1000)."""
    _, pools, _ = build_routes_and_pools(
        dict(_LIVE_DS_FLASH_REGISTRY), dict(_LIVE_DS_FLASH_POOL))
    providers = _providers_in_order(pools, "deepseek-v4-flash")
    assert "deepseek" in providers, f"deepseek-direct missing from pool: {providers}"
    assert "openrouter" in providers, f"openrouter missing from pool: {providers}"
    ds_idx = providers.index("deepseek")
    or_idx = providers.index("openrouter")
    assert ds_idx < or_idx, (
        f"deepseek-direct must sort BEFORE openrouter after enrichment. "
        f"Got order: {providers} (ds at {ds_idx}, or at {or_idx})")


@pytest.mark.skipif(not _try_import_litellm(), reason="litellm not installed")
def test_free_legs_sort_first():
    """Free legs always sort before all paid legs, enrichment or not."""
    _, pools, _ = build_routes_and_pools(
        dict(_LIVE_DS_FLASH_REGISTRY), dict(_LIVE_DS_FLASH_POOL))
    providers = _providers_in_order(pools, "deepseek-v4-flash")
    assert providers[0] == "groq", (
        f"free leg must be first, got {providers}")


@pytest.mark.skipif(not _try_import_litellm(), reason="litellm not installed")
def test_pool_still_contains_all_eligible_legs():
    """All legs are present — narrowing must not drop providers.
    enabled=false is no longer exclusion by itself (ADR-0016 step 6)."""
    _, pools, _ = build_routes_and_pools(
        dict(_LIVE_DS_FLASH_REGISTRY), dict(_LIVE_DS_FLASH_POOL))
    providers = _providers_in_order(pools, "deepseek-v4-flash")
    # Both groq entries appear: one free (dsv4-flash-free), one disabled (dsv4-flash-go)
    expected = {"groq", "nanogpt", "huggingface", "openrouter", "deepseek"}
    present = set(providers)
    assert expected == present, (
        f"expected providers {expected}, got {present}. "
        f"Full order: {providers}")


@pytest.mark.skipif(not _try_import_litellm(), reason="litellm not installed")
def test_pool_order_reverts_to_wrong_order_without_enrichment():
    """Red-proof: without litellm enrichment (pre-#266), both deepseek-direct
    and openrouter get rank 1000. The hand-authored pool order governs, placing
    openrouter (position 4) before deepseek-direct (position 5)."""
    from unittest.mock import patch

    with patch("charon.routing_policy.litellm_pricing.enrich_registry",
               side_effect=lambda r: dict(r)):
        _, pools, _ = build_routes_and_pools(
            dict(_LIVE_DS_FLASH_REGISTRY), dict(_LIVE_DS_FLASH_POOL))
        providers = _providers_in_order(pools, "deepseek-v4-flash")
        ds_idx = providers.index("deepseek")
        or_idx = providers.index("openrouter")
        assert or_idx < ds_idx, (
            f"WITHOUT enrichment, openrouter must be BEFORE deepseek-direct "
            f"(preserves hand-authored order). "
            f"Got: {providers} (or at {or_idx}, ds at {ds_idx})")
