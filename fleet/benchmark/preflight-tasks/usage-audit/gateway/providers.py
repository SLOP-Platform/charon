"""Provider model — mirrors Charon's gateway/providers.py shape."""
from dataclasses import dataclass


@dataclass
class Provider:
    name: str
    cost_rank: int


def cheapest(providers):
    return min(providers, key=lambda p: p.cost_rank)
