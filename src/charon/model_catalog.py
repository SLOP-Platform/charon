"""Provider-agnostic curated model catalog (stdlib DATA, zero vendor branching).

The curated reference list of RECOMMENDED models for Charon tier assignment,
distilled from operator evaluation.  Every entry is a plain data record —
``id``, ``tier_hint`` (low/med/high), ``access`` (human-readable access path),
and ``note`` (short orientation).  The module contains NO vendor-specific
logic — ``access`` is a descriptive string (data), not a coupling.

The catalog is a convenience MENU, not a whitelist; users can always assign
an off-catalog custom model id to any tier.
"""
from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass


@dataclass(frozen=True)
class CatalogEntry:
    """One curated model recommendation."""

    id: str
    tier_hint: str  # "low" | "med" | "high"
    access: str
    note: str


# ---- data -------------------------------------------------------------------
# Entries are APPEND-ONLY — a stale entry is a data edit, never a code change.
# tier_hint uses the CANONICAL tier names (low/med/high) so catalog_for_tier
# can fold alias lookups via config.resolve_tier.

_CATALOG: tuple[CatalogEntry, ...] = (
    # ── high ──────────────────────────────────────────────────────────
    CatalogEntry(
        id="claude-opus-4-8",
        tier_hint="high",
        access="Anthropic direct",
        note="Lead frontier model; 1M ctx; state-of-the-art agentic coding + reasoning",
    ),
    CatalogEntry(
        id="claude-fable-5",
        tier_hint="high",
        access="Anthropic direct",
        note="Most capable; always-on thinking; best long-horizon reasoning",
    ),
    CatalogEntry(
        id="gpt-5.5",
        tier_hint="high",
        access="OpenAI direct",
        note="Frontier agentic coding; strong second-vendor voice for DTC diversity",
    ),
    CatalogEntry(
        id="gemini-3.1-pro",
        tier_hint="high",
        access="Google direct",
        note="Top-tier reasoning + very large context; strong whole-repo tracing",
    ),
    # ── med ───────────────────────────────────────────────────────────
    CatalogEntry(
        id="claude-sonnet-5",
        tier_hint="med",
        access="Anthropic direct",
        note="Default implementer; near-Opus coding quality at strong-tier price",
    ),
    CatalogEntry(
        id="deepseek-v4-pro",
        tier_hint="med",
        access="DeepSeek direct / open weights / OpenRouter",
        note="Strongest open-weight coder; 1.6T MoE, 1M ctx; excellent value",
    ),
    CatalogEntry(
        id="kimi-k2.6",
        tier_hint="med",
        access="Moonshot / open weights / OpenRouter",
        note="Agentic-tuned; strong on SWE-bench Pro; long-horizon sub-agent work",
    ),
    CatalogEntry(
        id="glm-5.2",
        tier_hint="med",
        access="z.ai / open weights / OpenRouter",
        note="753B MoE, 1M ctx; borderline frontier at ~1/6 cost",
    ),
    CatalogEntry(
        id="minimax-m2.5",
        tier_hint="med",
        access="MiniMax direct / open weights / OpenRouter",
        note="230B/10B MoE; strong open coder; fast + cheap",
    ),
    CatalogEntry(
        id="minimax-m3",
        tier_hint="med",
        access="MiniMax direct / open weights / OpenRouter",
        note="428B MoE, 1M ctx; frontier-adjacent open model",
    ),
    CatalogEntry(
        id="devstral-2",
        tier_hint="med",
        access="Mistral direct / open weights / OpenRouter",
        note="Purpose-built agentic coder, 256K ctx (123B); Small 24B variant available",
    ),
    # ── low ───────────────────────────────────────────────────────────
    CatalogEntry(
        id="claude-haiku-4.5",
        tier_hint="low",
        access="Anthropic direct",
        note="Fast, strong instruction-following; most capable economy Claude",
    ),
    CatalogEntry(
        id="gemini-3-flash",
        tier_hint="low",
        access="Google direct",
        note="Punches above its tier; near-frontier SWE-bench at ~1/4 Pro price",
    ),
    CatalogEntry(
        id="deepseek-v4-flash",
        tier_hint="low",
        access="DeepSeek direct / open weights / OpenRouter",
        note="284B MoE, 1M ctx; cheap open-weight workhorse",
    ),
    CatalogEntry(
        id="qwen3-coder-next",
        tier_hint="low",
        access="Qwen API / open weights / OpenRouter",
        note="Agentic-RL trained; 80B/3B-active hybrid MoE; efficient",
    ),
    CatalogEntry(
        id="qwen3.6-27b",
        tier_hint="low",
        access="Qwen API / open weights / OpenRouter",
        note="Dense 27B, 1M ctx; punches above its size; best self-host pick",
    ),
)


def catalog() -> Sequence[CatalogEntry]:
    """All curated catalog entries."""
    return list(_CATALOG)


def catalog_for_tier(tier: str) -> Sequence[CatalogEntry]:
    """Entries whose ``tier_hint`` folds to *tier* via ``config.resolve_tier``.

    ``tier`` may be a canonical name (low/med/high) or an alias
    (frontier/strong/economy, opus/sonnet/haiku).
    """
    from .config import resolve_tier

    canon = resolve_tier(tier)
    return [e for e in _CATALOG if e.tier_hint == canon]
