"""Provider ordering — mirrors Charon's gateway/routing.py shape.

OUT OF SCOPE for the current ticket. Present only so the dedupe change has a
realistic neighbouring module; it is correct as-is and must not be edited.
"""


def order_by_cost(providers):
    """Return providers sorted ascending by cost_rank (stable)."""
    return sorted(providers, key=lambda p: p.cost_rank)
