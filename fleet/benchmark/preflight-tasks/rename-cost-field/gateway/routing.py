"""Routing — mirrors Charon's gateway/routing.py shape. Reads cost_rank."""


def order_by_cost(providers):
    """Return providers sorted ascending by cost_rank, tie-broken by name."""
    return sorted(providers, key=lambda p: (p.cost_rank, p.name))
