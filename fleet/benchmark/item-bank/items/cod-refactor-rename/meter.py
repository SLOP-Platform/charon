"""meter.py — uses cost_rank for billing aggregation."""
from config import ProviderConfig


def billable_cost(providers: list[ProviderConfig]) -> dict[str, int]:
    return {p.name: p.cost_rank for p in providers}
