"""FT-CATALOG-SEED — shipped SEED of known free-tier rate limits for the
providers the product has not yet been taught by the build-rig's
FREE-TIER-LIMITS.tsv (the product/rig boundary means the product cannot
read that file at runtime — it ships its own copy).

Authority order (overridable; the seed is the LOWEST tier):

  1. Live limits refreshed by ``PRICING-LIMITS-CHECKER`` (the build-rig
     refresher that writes back into the in-process config).
  2. Explicit config (FT-CONFIG-SURFACE — the operator-authoritative
     ``[providers.<name>]`` overrides).
  3. THIS SEED — the conservative defaults below. Fills the gap when
     a leg has no explicit config AND no fresh refresh.

The seed is intentionally stdlib-only: a ``dict[str, dict]`` plus
``get_limits(provider)`` and ``providers()`` accessors.  The shape
matches what FT-CONFIG-SURFACE emits, so the same consumer code
(``quota.QuotaTracker``) accepts the merged result without a second
parser.

Shape (per provider)::

    {
        "rpm":      int | None,   # requests per minute
        "rpd":      int | None,   # requests per day
        "tpm":      int | None,   # tokens per minute
        "tpd":      int | None,   # tokens per day
        "weekly":   int | None,   # requests-or-tokens per ISO week (None if N/A)
        "monthly":  int | None,   # requests-or-tokens per calendar month
        "reset":    "rolling" | "calendar" | "weekly" | "monthly",
        "verified": bool,         # True if a human/rig confirmed the number
        "personal_only": bool,    # True if the free tier is restricted to
                                  # individual/personal accounts
        "note":     str,          # human-readable provenance
    }

Every entry is non-Anthropic (``sg-never-anthropic``); Anthropic's
free tier is intentionally excluded from the seed — Anthropic has no
genuine free tier and any entry here would mislead the router. If a
future ticket ever adds one, it must be flagged separately.

New entries should be appended with ``verified=False`` until the
PRICING-LIMITS-CHECKER job confirms them — that's how the seed stays
a SEED, not an undocumented source of truth.
"""
from __future__ import annotations

from typing import TypedDict, cast


class _LimitDict(TypedDict, total=False):
    rpm: int | None
    rpd: int | None
    tpm: int | None
    tpd: int | None
    weekly: int | None
    monthly: int | None
    reset: str
    verified: bool
    personal_only: bool
    note: str


# Public, read-only seed. Do NOT mutate at runtime — tests and the live
# router both rely on a stable baseline.  The PRICING-LIMITS-CHECKER
# writes its refreshed view into config, not into this dict.
FREE_TIER_CATALOG: dict[str, _LimitDict] = {
    "groq": {
        "rpm": 30,
        "rpd": 14_400,
        "tpm": 6_000,
        "tpd": None,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        "verified": True,
        "personal_only": False,
        "note": "Groq free tier (8B-class models); 30 req/min and 14,400 req/day, "
                "6,000 tokens/min. Rolling windows.",
    },
    "openrouter": {
        "rpm": 20,
        "rpd": 1_000,
        "tpm": None,
        "tpd": None,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        # :free models are routed only on personal accounts; business/team
        # accounts see metered pricing.
        "verified": True,
        "personal_only": True,
        "note": "OpenRouter :free models — 1,000 req/day, 20 req/min, "
                "personal accounts only. Free routes can silently downgrade; "
                "the router's downgrade-detector still applies.",
    },
    "cerebras": {
        "rpm": 5,
        "rpd": None,
        "tpm": None,
        "tpd": 1_000_000,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        "verified": True,
        "personal_only": False,
        "note": "Cerebras free tier — 5 req/min, 1,000,000 tokens/day.",
    },
    "mistral": {
        "rpm": None,
        "rpd": None,
        "tpm": None,
        "tpd": None,
        "weekly": None,
        "monthly": 1_000_000_000,
        "reset": "monthly",
        "verified": True,
        "personal_only": False,
        "note": "Mistral free tier — ~1e9 tokens/month (calendar-month reset).",
    },
    "github_models": {
        "rpm": None,
        "rpd": None,
        "tpm": None,
        "tpd": None,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        "verified": False,
        "personal_only": True,
        "note": "GitHub Models free tier — limits UNVERIFIED; PRICING-LIMITS-CHECKER "
                "must confirm. Personal GitHub accounts only.",
    },
    "featherless": {
        "rpm": None,
        "rpd": None,
        "tpm": None,
        "tpd": None,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        "verified": False,
        "personal_only": False,
        "note": "Featherless.ai free tier — 32K session-context cap is on the "
                "provider preset (max_context), not on the quota tracker. Limits "
                "UNVERIFIED; PRICING-LIMITS-CHECKER must confirm.",
    },
    "ollama_cloud": {
        "rpm": None,
        "rpd": None,
        "tpm": None,
        "tpd": None,
        "weekly": None,
        "monthly": None,
        "reset": "rolling",
        "verified": False,
        "personal_only": False,
        "note": "Ollama.com hosted free/turbo tier — limits UNVERIFIED; "
                "PRICING-LIMITS-CHECKER must confirm. Distinct from the local "
                "Ollama preset (local.py), which is unbounded and intentionally "
                "absent from the catalog.",
    },
}


def get_limits(provider: str) -> _LimitDict | None:
    """Return the seeded limits for *provider*, or ``None`` if unknown.

    Unknown is NOT an error — the seed is a gap-filler, and a missing
    entry simply means "the live config or the PRICING-LIMITS-CHECKER
    is the authority here, not the seed".  Callers must treat ``None``
    as "no seed; check elsewhere" and never as "zero".
    """
    entry = FREE_TIER_CATALOG.get(provider)
    if entry is None:
        return None
    # Defensive copy: callers must not be able to mutate the seed by
    # editing the returned dict (e.g. via setdefault on a nested key).
    return cast(_LimitDict, dict(entry))


def providers() -> list[str]:
    """Return the sorted list of provider names with a seeded entry.

    A provider in this list still has ``verified=False`` until the
    PRICING-LIMITS-CHECKER confirms it — the list is the SCOPE, not
    a guarantee of accuracy.
    """
    return sorted(FREE_TIER_CATALOG.keys())
