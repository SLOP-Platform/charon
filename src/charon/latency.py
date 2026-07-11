"""Per-provider rolling latency tracker (R8 latency-signal).

A lightweight EWMA keyed by provider label; consumed by the gateway router as
a secondary ordering signal and a slow-provider flag for graceful-degrade.
"""
from __future__ import annotations

import threading


class RollingLatency:
    """Thread-safe EWMA of observed request latency per provider label.

    ``alpha`` controls how aggressively new samples move the average:
    * alpha=1.0 → no smoothing (latest sample only)
    * alpha=0.3 → moderate smoothing (default)
    * alpha=0.1 → slow smoothing (heavy history weight)
    """

    def __init__(self, alpha: float = 0.3) -> None:
        self._alpha = alpha
        self._latencies: dict[str, float] = {}
        self._lock = threading.Lock()

    def record(self, provider: str, latency_ms: float) -> None:
        """Fold one observed latency sample into the rolling average."""
        with self._lock:
            prev = self._latencies.get(provider)
            if prev is None:
                self._latencies[provider] = float(latency_ms)
            else:
                self._latencies[provider] = (
                    self._alpha * float(latency_ms)
                    + (1.0 - self._alpha) * prev
                )

    def latency_ms(self, provider: str) -> float | None:
        """Current EWMA latency for ``provider``, or ``None`` if no samples yet."""
        with self._lock:
            return self._latencies.get(provider)

    def all_latencies(self) -> dict[str, float]:
        """Snapshot of all provider latencies."""
        with self._lock:
            return dict(self._latencies)

    def is_slow(
        self,
        provider: str,
        threshold_ms: float | None,
    ) -> bool:
        """True when the provider's measured latency exceeds ``threshold_ms``.

        Returns ``False`` when there is no data or no threshold is configured.
        """
        if threshold_ms is None:
            return False
        lat = self.latency_ms(provider)
        if lat is None:
            return False
        return lat > threshold_ms
