"""Routing — mirrors Charon's gateway/routing.py shape."""


def order_by_cost(providers):
    return sorted(providers, key=lambda p: p.cost_rank)
