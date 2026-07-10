"""DRAIN-ROUTING policy (Wave 2).

Stub — the full implementation lands in Wave 2. Drain routing directs
traffic AWAY from a provider/model that is approaching quota or rate-limit
exhaustion, transparently shifting requests to alternative candidates
before the upstream rejects them.
"""
from __future__ import annotations

from .base import Policy


class DrainPolicy(Policy):
    """Stub — returns empty list (not yet implemented)."""

    name = "drain"

    def select(self, **kwargs):
        return []
