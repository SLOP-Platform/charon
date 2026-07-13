"""Provider helpers — mirrors Charon's gateway/providers.py shape."""
from dataclasses import dataclass


@dataclass
class Provider:
    name: str
    cost_rank: int


def dedupe_providers(providers):
    """Return `providers` with duplicate names removed, first occurrence kept
    and original order preserved.

    BUG: currently returns the list unchanged — duplicates survive.
    """
    return list(providers)
