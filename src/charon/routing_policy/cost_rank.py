"""Cost-rank derivation (SR-6) — moved from ``charon.pools.derived_cost_rank``.

Wave 2 (COST-RANK-AUTO) extends this module with automatic per-provider
cost-rank computation from live pricing data.
"""
from __future__ import annotations

# Order: cheaper funding classes first.  Matches _COST_CLASSES in config.py
# ("free-daily", "expiring", "prepaid", "metered", "premium").
_COST_CLASS_PRIORITY: dict[str, int] = {
    "free-daily": 0,
    "expiring": 1,
    "prepaid": 2,
    "metered": 3,
    "premium": 4,
}


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
    """SR-6 + R5: derive cost_rank from per-token pricing (3:1 in:out blend)
    when pricing is present and no explicit ``cost_rank`` override is set.

    If *metered_cost* is provided (live per-(model,provider) cost from the R4
    meter), it is used directly as the authoritative cost figure.  When absent
    (no traffic yet), we FALL BACK to the configured ``cost_input`` /
    ``cost_output`` pricing.  Returns the explicit ``cost_rank`` when set, else
    the computed rank, else 1000."""
    explicit = spec.get("cost_rank")
    if explicit is not None:
        return int(explicit)

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
