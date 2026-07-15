"""routing.py — uses cost_rank to pick the cheapest provider."""
from config import ProviderConfig, _resolve_cost_rank


def pick_cheapest(providers: list[ProviderConfig]) -> ProviderConfig:
    ordered = _resolve_cost_rank(providers)
    return ordered[0]


def fallback_chain(providers: list[ProviderConfig]) -> list[ProviderConfig]:
    """Build a failover chain ordered by cost_rank asc, then name asc."""
    return sorted(providers, key=lambda p: (p.cost_rank, p.name))
