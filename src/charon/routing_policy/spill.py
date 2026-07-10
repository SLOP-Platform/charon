"""FREE-TIER-QUOTA-SPILL policy (Wave 2).

Stub — the full implementation lands in Wave 2. Spill routing moves
overflow traffic from free-tier providers (whose daily quota is exhausted)
to paid providers, preferring the cheapest paid candidate that still
satisfies the request's capability requirements.
"""
from __future__ import annotations

from .base import Policy


class SpillPolicy(Policy):
    """Stub — returns empty list (not yet implemented)."""

    name = "spill"

    def select(self, **kwargs):
        return []
