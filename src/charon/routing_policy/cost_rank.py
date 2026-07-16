"""Cost-rank derivation (SR-6) — moved from ``charon.pools.derived_cost_rank``.

Wave 2 (COST-RANK-AUTO) extended this module with automatic per-provider
cost-rank computation from live pricing data.

DELETE-STATIC-RANK (ADR-0016 step #6): the hand-typed ``cost_rank`` integer
is REMOVED as a config input. Ordering is ALWAYS derived from live/sourced/
meter price — a magnitude a hand-typed scalar could never be trusted to keep
in sync with.  See ``docs/adr/0016-demand-driven-capability-match.md``.
"""
from __future__ import annotations

import warnings

# Order: cheaper funding classes first.  Matches _COST_CLASSES in config.py
# ("free-daily", "expiring", "prepaid", "metered", "premium").
_COST_CLASS_PRIORITY: dict[str, int] = {
    "free-daily": 0,
    "expiring": 1,
    "prepaid": 2,
    "metered": 3,
    "premium": 4,
}

# One-release deprecation window (ADR-0016 Consequences): an external config
# that still stamps ``cost_rank`` is no longer honored, but the validator
# warns so operators see a clean signal during migration.
_DEPRECATION_WINDOW_RELEASES = 1


def _warn_static_cost_rank_deprecated(spec: dict) -> None:
    """Emit a one-release deprecation warning when an external config still
    sets ``cost_rank``. ADR-0016 step #6: the hand-typed integer is no longer
    a config INPUT — ordering derives from live/sourced/meter price only.
    The warning is the migration signal operators see while the .60 deploy
    purges the field from ``models.json``."""
    cr = spec.get("cost_rank")
    if cr is None:
        return
    model_id = spec.get("id") or spec.get("model") or "<unknown>"
    warnings.warn(
        f"cost_rank={cr!r} on model {model_id!r} is deprecated and IGNORED "
        f"(ADR-0016 step #6). Ordering is now derived from "
        f"cost_input/cost_output + the live meter; remove the field from "
        f"models.json to silence this warning.",
        DeprecationWarning,
        stacklevel=3,
    )


def cost_class_priority(spec: dict) -> int:
    """Return the sort priority for *spec*'s ``cost_class``.

    Lower = preferred (cheaper funding class first).  Unknown / missing values
    return the highest priority (``premium``) so unclassified entries sort
    last and never accidentally float above known classes.
    """
    cc = spec.get("cost_class")
    if isinstance(cc, str):
        return _COST_CLASS_PRIORITY.get(cc.strip().lower(), 4)
    return 4


def derived_cost_rank(spec: dict, metered_cost: float | None = None) -> int:
    """SR-6 + R5: derive cost_rank from per-token pricing (3:1 in:out blend).

    ADR-0016 step #6: a hand-typed ``cost_rank`` override is NO LONGER
    honored.  Ordering is ALWAYS derived from live/sourced/meter price — the
    source of truth that a hand-set integer can never be trusted to track.
    An external config that still stamps ``cost_rank`` emits a
    ``DeprecationWarning`` (one-release migration window) but the integer is
    ignored for ordering.

    If *metered_cost* is provided (live per-(model,provider) cost from the R4
    meter), it is used directly as the authoritative cost figure.  When absent
    (no traffic yet), the configured ``cost_input`` / ``cost_output`` pricing
    is used.  Falls back to a neutral 1000 when neither is set.
    """
    if spec.get("cost_rank") is not None:
        _warn_static_cost_rank_deprecated(spec)

    # R5: prefer live metered cost when available
    if metered_cost is not None:
        return max(0, round(float(metered_cost) * 1_000_000 * 100))

    ci = spec.get("cost_input")
    co = spec.get("cost_output")
    if ci is None and co is None:
        return 1000  # missing-pricing fallback: neutral middle rank
    ci = float(ci) if ci is not None else 0.0
    co = float(co) if co is not None else 0.0
    blended = (3.0 * ci + co) / 4.0
    return max(0, round(blended * 1_000_000 * 100))
