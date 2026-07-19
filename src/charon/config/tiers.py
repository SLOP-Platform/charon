"""Tier config store — DTC tier-abstraction with canonical low/med/high vocabulary."""
from __future__ import annotations

from collections.abc import Mapping, Sequence
from pathlib import Path

from ._store import _as_str_tuple, _load, _save

_TIERS_FILE = "tiers.json"
CANONICAL_TIERS: tuple[str, ...] = ("low", "med", "high")
# Legacy/synonym name → canonical tier (the backward-compat seam). Seeded into a fresh
# ``tiers.json`` and used as a fallback when a recognized synonym is missing from the file.
_LEGACY_ALIASES: dict[str, str] = {
    "opus": "high", "sonnet": "med", "haiku": "low",
    "frontier": "high", "strong": "med", "economy": "low",
}
# Day-one == today: each tier seeds the single matching Anthropic model.
_LEGACY_MEMBERS: dict[str, list[str]] = {"low": ["haiku"], "med": ["sonnet"], "high": ["opus"]}
# The provider those seeds belong to. The line above has always ASSERTED that the
# seeds are Anthropic models; this makes that assertion machine-readable so a
# caller can look it up instead of guessing at a bare id like "opus".
LEGACY_SEED_PROVIDER = "anthropic"


def legacy_seed_members() -> frozenset[str]:
    """The bare model ids seeded when ``tiers.json`` is absent (``haiku``/``sonnet``/
    ``opus``), whose provider is :data:`LEGACY_SEED_PROVIDER`.

    These ids name an Anthropic model by convention but never spell the vendor, so
    a generic route matcher cannot classify them — that is a fact this config layer
    OWNS, not something a matcher should be taught to infer. Exposing it here lets
    an executor filter resolve the absent-config path without widening any
    provider-matching rule (which would then misclassify an unrelated third-party
    model that merely shares one of these names).
    """
    return frozenset(m for ms in _LEGACY_MEMBERS.values() for m in ms)


def _legacy_tiers() -> dict:
    """The absent-file default: canonical order + legacy aliases + one Anthropic model
    per tier, so behavior matches the pre-abstraction ``opus/sonnet/haiku`` world."""
    return {
        "order": list(CANONICAL_TIERS),
        "members": {t: list(ms) for t, ms in _LEGACY_MEMBERS.items()},
        "aliases": dict(_LEGACY_ALIASES),
    }


def load_tiers() -> dict:
    """Parsed ``tiers.json`` (normalized to canonical keys), or the legacy default when
    the file is absent/empty. Always returns ``{order, members, aliases}`` with ``order``
    a subset of the canonical tiers and ``members`` keyed by every tier in ``order``."""
    data = _load(_TIERS_FILE)
    if not data:
        return _legacy_tiers()
    order = [t for t in data.get("order", []) if t in CANONICAL_TIERS]
    if not order:
        order = list(CANONICAL_TIERS)
    raw_members = data.get("members") or {}
    members = {t: list(_as_str_tuple(raw_members.get(t))) for t in order}
    raw_aliases = data.get("aliases")
    if not isinstance(raw_aliases, Mapping):
        raw_aliases = {}
    aliases = {
        str(name).strip().lower(): tier
        for name, tier in raw_aliases.items()
        if isinstance(tier, str) and tier in CANONICAL_TIERS
    }
    return {"order": order, "members": members, "aliases": aliases}


def set_tiers(order: Sequence[str], members: Mapping[str, Sequence[str]],
              aliases: Mapping[str, str]) -> Path:
    """Atomically persist ``tiers.json`` (reuses the ``_save`` pattern). ``order`` must be
    exactly the canonical tiers ``low/med/high`` (a permutation); member ids must pass
    ``_ID_RE``; alias targets must be canonical. Member existence in ``models.json`` is
    NOT enforced here — the gateway reuses the registry at compile time."""
    from ._store import _ID_RE
    order = list(order)
    bad = [t for t in order if t not in CANONICAL_TIERS]
    if bad:
        raise ValueError(f"non-canonical tier(s) in order: {bad}")
    if set(order) != set(CANONICAL_TIERS):
        raise ValueError("order must contain exactly the canonical tiers low/med/high")
    out_members: dict[str, list[str]] = {}
    for t in order:
        ms = list(members.get(t, []))
        invalid = [m for m in ms if not isinstance(m, str) or not _ID_RE.match(m)]
        if invalid:
            raise ValueError(f"invalid model id(s) in tier {t!r}: {invalid}")
        out_members[t] = ms
    out_aliases: dict[str, str] = {}
    for name, tier in aliases.items():
        if tier not in CANONICAL_TIERS:
            raise ValueError(f"alias {name!r} targets non-canonical tier {tier!r}")
        out_aliases[str(name).strip().lower()] = tier
    return _save(_TIERS_FILE, {"order": order, "members": out_members, "aliases": out_aliases})


def resolve_tier(name: str, tiers: Mapping | None = None) -> str:
    """Fold ``name`` (case-insensitive) to a canonical tier. Canonical names pass through;
    file aliases then legacy synonyms map to canonical. Unknown names raise ``ValueError``."""
    t = load_tiers() if tiers is None else tiers
    key = str(name).strip().lower()
    if key in CANONICAL_TIERS:
        return key
    file_aliases = t.get("aliases") or {}
    if key in file_aliases:
        return file_aliases[key]
    if key in _LEGACY_ALIASES:  # safety net even if the file dropped a known synonym
        return _LEGACY_ALIASES[key]
    raise ValueError(f"unknown tier {name!r}")


def tier_members(tier: str, tiers: Mapping | None = None) -> list[str]:
    """The ordered member model ids for a (resolved) tier. Within-tier order is the stored
    member order; the gateway later applies free-first→cost_rank (not this layer's concern)."""
    t = load_tiers() if tiers is None else tiers
    canon = resolve_tier(tier, t)
    return list((t.get("members") or {}).get(canon, []))


def tier_rank(name: str, tiers: Mapping | None = None) -> int:
    """1-based rank of a tier within ``order`` (alias-folded): ``low=1 med=2 high=3``,
    so legacy ``opus=3 sonnet=2 haiku=1`` falls out for free. Unknown names → ``0``."""
    t = load_tiers() if tiers is None else tiers
    try:
        canon = resolve_tier(name, t)
    except ValueError:
        return 0
    order = t.get("order") or list(CANONICAL_TIERS)
    return order.index(canon) + 1 if canon in order else 0
