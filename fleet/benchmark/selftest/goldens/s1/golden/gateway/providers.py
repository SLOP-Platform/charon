"""Provider model + cheapest_provider() - fixed."""
from dataclasses import dataclass

VALID_COST_CLASSES = ("cheap", "strong", "premium")


@dataclass
class Provider:
    name: str
    base_url: str
    cost_class: str
    cost_rank: int


def cheapest_provider(providers):
    """Return the provider with the lowest cost_rank."""
    best = providers[0]
    for p in providers[1:]:
        if p.cost_rank < best.cost_rank:
            best = p
    return best
