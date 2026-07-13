"""Provider ranking — mirrors Charon's gateway/rank.py shape.

rank_providers() sorts by cost_rank. On ties the order depends on input order
(a plain single-key sort is stable, so equal-cost providers keep whatever order
they arrived in) — so the same set in a different input order ranks differently.
The fix is a deterministic tie-break by name.
"""
from dataclasses import dataclass


@dataclass
class Provider:
    name: str
    cost_rank: int


def rank_providers(providers):
    """Return providers ordered by cost_rank ascending.

    BUG: ties are not broken deterministically — equal cost_rank keeps input
    order. Ties should break by name ascending.
    """
    return sorted(providers, key=lambda p: p.cost_rank)
