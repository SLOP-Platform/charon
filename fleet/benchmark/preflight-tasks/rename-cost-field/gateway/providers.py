"""Provider model — mirrors Charon's gateway/providers.py shape."""
from dataclasses import dataclass


@dataclass
class Provider:
    name: str
    cost_rank: int  # rename target -> price_rank


def cheapest(providers):
    """Return the provider with the lowest cost_rank."""
    return min(providers, key=lambda p: p.cost_rank)
