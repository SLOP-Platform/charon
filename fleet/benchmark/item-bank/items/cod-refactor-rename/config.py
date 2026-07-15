"""config.py — canonical cost_rank definition (to be renamed)."""
from dataclasses import dataclass


@dataclass
class ProviderConfig:
    name: str
    cost_rank: int  # rename: cost_rank -> price_rank
    cost_class: str  # NOT to be renamed
    base_url: str
    api_key: str = ""


def _resolve_cost_rank(providers: list[ProviderConfig]) -> list[ProviderConfig]:
    """Stable order: by cost_rank ascending, then name."""
    return sorted(providers, key=lambda p: (p.cost_rank, p.name))
