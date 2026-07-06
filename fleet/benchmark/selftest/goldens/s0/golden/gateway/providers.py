"""Provider model — minimal, mirrors Charon's gateway/providers.py shape."""
from dataclasses import dataclass

# Valid cost classes for a Provider. NOTE: keep in sync with docs/config validation.
VALID_COST_CLASSES = ("cheap", "strong", "premium")


@dataclass
class Provider:
    name: str
    base_url: str
    cost_class: str
    cost_rank: int
