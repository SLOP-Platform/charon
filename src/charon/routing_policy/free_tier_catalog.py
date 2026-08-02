"""Free-tier limits catalog — the product's own shipped seed of known limits.

The product cannot read the build-rig FREE-TIER-LIMITS.tsv (product/rig
boundary), so this module ships a SEED of the free-tier rate limits we know,
in the SAME normalized shape the FT-CONFIG-SURFACE ``free_tier`` block emits
(``rpm``/``rpd``/``tpm``/``tpd``/``weekly_tokens``/``monthly_tokens`` plus a
``reset`` kind).  The projection (:func:`limits_for`) returns ONLY those
normalized keys; per-entry metadata (``verified``, ``personal_only``) is kept
on the raw catalog rows, never in the projected block.

This is a SEED / default source only.  The LIVE authority is explicit
per-provider config (FT-CONFIG-SURFACE ``free_tier`` blocks persisted in
providers.json) plus the refresh path (PRICING-LIMITS-CHECKER).  The catalog
fills gaps for a leg that has no explicit config; it never overrides an
explicit block.

Every entry is NON-Anthropic (sg-never-anthropic) — none of the seeded
providers is an Anthropic/Claude route.  Personal-only free tiers are marked
``personal_only=True``.
"""
from __future__ import annotations

# Normalized free_tier keys — mirrors the FT-CONFIG-SURFACE schema
# (``charon.config.providers._FREE_TIER_KEYS``).  Kept local (this is a pure
# stdlib data module) so the projection returns exactly what the config
# surface would persist; only these keys cross the API.
_FREE_TIER_KEYS = ("rpm", "rpd", "tpm", "tpd",
                   "weekly_tokens", "monthly_tokens", "reset")

# provider -> seeded free-tier limits (normalized keys) + metadata.
#
# ``verified``: True = numbers confirmed (see FREE-TIER-LIMITS.tsv / live
# probes); False = placeholder row so the provider is KNOWN to the catalog
# until PRICING-LIMITS-CHECKER confirms its numbers.  A ``verified=False``
# row projects to an empty block (present-but-unconfirmed), distinct from an
# unknown provider (``limits_for`` returns None).
FREE_TIER_CATALOG: dict[str, dict] = {
    "groq": {
        "rpd": 14400,
        "rpm": 30,
        "tpm": 6000,
        "reset": "rolling",
        "personal_only": True,
        "verified": True,
    },
    "openrouter": {
        "rpd": 1000,
        "rpm": 20,
        "reset": "rolling",
        "personal_only": True,
        "verified": True,
    },
    "cerebras": {
        "tpd": 1_000_000,
        "rpm": 5,
        "reset": "rolling",
        "personal_only": True,
        "verified": True,
    },
    "mistral": {
        "monthly_tokens": 1_000_000_000,
        "reset": "calendar",
        "personal_only": True,
        "verified": True,
    },
    "github_models": {
        "personal_only": True,
        "verified": False,
    },
    "featherless": {
        "personal_only": True,
        "verified": False,
    },
    "ollama_cloud": {
        "personal_only": True,
        "verified": False,
    },
}


def limits_for(provider: str) -> dict | None:
    """Return *provider*'s seeded free-tier limits as a normalized
    FT-CONFIG-SURFACE ``free_tier`` block, or None when the catalog has no
    entry for *provider* (no known limits -> the caller treats the leg as
    unlimited).

    A present-but-``verified=False`` row (e.g. the three new free presets
    awaiting PRICING-LIMITS-CHECKER confirmation) projects to an empty dict —
    the provider is KNOWN to the catalog but its numbers are unconfirmed.
    That is deliberately distinct from an unknown provider, which returns
    None.  Only the normalized keys cross the API; ``verified`` and
    ``personal_only`` are metadata and never appear in the returned block.
    """
    entry = FREE_TIER_CATALOG.get(provider)
    if entry is None:
        return None
    return {k: v for k, v in entry.items() if k in _FREE_TIER_KEYS}
