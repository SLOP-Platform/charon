"""Provider model + cheapest_provider() — mirrors Charon's gateway/providers.py shape."""
from dataclasses import dataclass

VALID_COST_CLASSES = ("cheap", "strong", "premium")


@dataclass
class Provider:
    name: str
    base_url: str
    cost_class: str
    cost_rank: int


def cheapest_provider(providers):
    """Return the provider with the lowest cost_rank.

    BUG: currently just returns the last provider in the list instead of the
    true minimum by cost_rank.
    """
    return providers[-1]
