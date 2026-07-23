"""Degrade alert — surface routing degradation transitions that funding_class
currently parks silently.  Non-blocking (log-only, never changes routing or
billing).  Hooks the live funding_class / drain-then-park state; does NOT
re-implement it.

Three alert categories:
  1. LAST-RESORT / throttle: a request served only after failing over to the
     last leg (or throttled) — the pool is thinning; surface it.
  2. PREPAID LEG HITS ZERO: a drain-then-park provider parks (funding-class
     re-arm table fires) — surface "provider X parked, spilled to Y".
  3. ALL-degraded / pool-too-thin: escalate loudly — all routes excluded or
     every provider exhausted.  This is the state the whole session started in
     and it must never be silent again.

Additive, non-blocking — an alert must never change routing or billing.
Pairable with the live exhaustion ledger and FLOW-CANARY (proactive).

  [[last-resort-surface]]
  [[prepaid-zero-surface]]
  [[pool-too-thin-surface]]
  [[monitored-preflight-failure-attribution]]
  [[latency-is-a-failure-class]]
"""
from __future__ import annotations

import logging
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    from .balance import BalanceTracker

_log = logging.getLogger("charon.degrade_alert")


class DegradeAlert:
    """Surface silent degradation transitions as ``WARNING``-level log alerts.

    Instantiated once per gateway process (idempotent — no state mutation
    beyond counters).  The forwarder calls the ``alert_*`` methods at the
    exact transition points it already detects — this class only SURFACES,
    never decides.
    """

    def __init__(self, balance_tracker: BalanceTracker | None = None) -> None:
        self._bt = balance_tracker
        self._counters: dict[str, int] = {}

    # -- public alert surface -----------------------------------------------

    def alert_last_resort(
        self,
        provider: str,
        model: str = "",
        failover_count: int = 0,
        reason: str = "",
    ) -> None:
        """A request was served (or relayed) only after failing over to the
        LAST leg — the pool is thinning; surface it.

        Called from the failover loop when ``more`` is False (no further
        providers left to try) AND at least one prior failover was recorded.
        A single-upstream gateway with no failover slots does NOT trigger this
        — only a genuine multi-leg chain that exhausted all earlier options.
        """
        self._counters["last_resort"] = (
            self._counters.get("last_resort", 0) + 1
        )
        _log.warning(
            "LAST-RESORT: model=%r served by %r after %d failovers%s"
            " — pool thinning",
            model,
            provider,
            failover_count,
            f" ({reason})" if reason else "",
        )

    def alert_prepaid_zero(
        self,
        provider: str,
        model: str = "",
        spill_to: str = "",
    ) -> None:
        """A drain-then-park provider just parked (funding-class re-arm table
        fired).  Surface the spill target so a silent slide isn't invisible.

        Called immediately after ``bt.park(provider)`` in the pre-flight
        exclusion loop — only for class-3 drain-then-park providers whose
        balance just hit zero.
        """
        self._counters["prepaid_zero"] = (
            self._counters.get("prepaid_zero", 0) + 1
        )
        fc = None
        if self._bt is not None:
            fc = self._bt.funding_class(provider)
        _log.warning(
            "PREPAID-LEG-ZERO: provider %r (fc=%s) parked%s%s",
            provider,
            fc if fc is not None else "?",
            f", spilled to {spill_to}" if spill_to else "",
            f" (model={model})" if model else "",
        )

    def alert_pool_too_thin(
        self,
        model: str,
        total: int = 0,
        reason: str = "all routes excluded",
    ) -> None:
        """All routes excluded by pre-flight drain routing, OR every provider
        in the chain exhausted — escalate loudly.

        This is the state the whole session started in and it must never be
        silent again.  Called from the "all routes excluded" safety fallback
        in pre-flight, OR from the "all providers exhausted" terminal
        synthesis in the failover loop.
        """
        self._counters["pool_too_thin"] = (
            self._counters.get("pool_too_thin", 0) + 1
        )
        _log.warning(
            "POOL-TOO-THIN: model=%r — %s%s",
            model,
            reason,
            f" ({total} routes)" if total else "",
        )

    # -- counters ------------------------------------------------------------

    @property
    def counters(self) -> dict[str, int]:
        """Snapshot of per-category alert emission counts."""
        return dict(self._counters)
