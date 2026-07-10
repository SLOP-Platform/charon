"""Cost-rank derivation (SR-6) — moved from ``charon.pools.derived_cost_rank``.

Wave 2 (COST-RANK-AUTO) extends this module with automatic per-provider
cost-rank computation from live pricing data.
"""
from __future__ import annotations


def derived_cost_rank(spec: dict) -> int:
    """SR-6: derive cost_rank from per-token pricing (3:1 in:out blend) when
    pricing is present and no explicit ``cost_rank`` override is set. Returns
    the explicit ``cost_rank`` when set, else the derived rank, else 1000."""
    explicit = spec.get("cost_rank")
    if explicit is not None:
        return int(explicit)
    ci = spec.get("cost_input")
    co = spec.get("cost_output")
    if ci is None and co is None:
        return 1000  # missing-pricing fallback: neutral middle rank
    ci = float(ci) if ci is not None else 0.0
    co = float(co) if co is not None else 0.0
    blended = (3.0 * ci + co) / 4.0
    return max(0, round(blended * 1_000_000 * 100))
