"""providers.py — uses cost_rank to filter high-cost providers."""
from config import ProviderConfig


def affordable(providers: list[ProviderConfig], max_rank: int) -> list[ProviderConfig]:
    return [p for p in providers if p.cost_rank <= max_rank]
