"""Failover glue — connects the observing proxy to the pool router (ADR-0004).

The proxy (proxy.py) observes the gateway and knows which *models* are exhausted
or silently-downgraded. The router (pools.py) chooses among *(agent, model)*
profiles and excludes by entry key. This module is the small translation between
them, so cross-model failover (H6) is automatic: a 429 / pseudo-success on the
current model marks it excluded, and the next route for that role picks the next
cheapest live profile.

Also provides ``ReviewerCircuitBreaker``: a transparent ``Reviewer`` wrapper that
opens after ``threshold`` consecutive failures and refuses calls until ``cooldown_s``
elapses (then half-opens for one probe; success closes, failure re-opens).  Lives
here — not coordinator.py — so it stays unit-provable with no live agent or gate.

Kept separate from the coordinator so the selection logic is unit-provable with
no live agent.
"""
from __future__ import annotations

import threading
import time
from enum import Enum, auto

from .pools import PoolEntry
from .ports.reviewer import Findings, Reviewer, ReviewerError
from .proxy import GatewayProxy
from .router import StaticRouter
from .types import Outcome, WorkUnit


def proxy_excluded_keys(pool: list[PoolEntry], proxy: GatewayProxy) -> set[str]:
    """Pool-entry keys to exclude because their model exhausted/downgraded at the
    gateway. The proxy keys by model id; the router excludes by ``agent:model``,
    so this maps one to the other against the role's pool."""
    exhausted = proxy.exhausted_models()
    return {e.key for e in pool if e.model in exhausted}


def next_entry(
    router: StaticRouter,
    role: str,
    proxy: GatewayProxy,
    *,
    also_exclude: set[str] | None = None,
    code_safe_only: bool = False,
) -> PoolEntry:
    """Pick the next live profile for ``role``: free-first/cheapest-first, skipping
    any model the proxy has flagged exhausted (plus any caller-supplied keys).
    Raises (clean ``exhausted`` stop) when the pool is dry."""
    pool = router.pools.get(role, [])
    exclude = proxy_excluded_keys(pool, proxy) | (also_exclude or set())
    return router.route_pool(role, exclude=exclude, code_safe_only=code_safe_only)


# NOTE (ADR-0014 D6, Phase B): ``select_live_entry`` — the engine-side pre-flight
# pool-probe — was retired here. Tier routing now consumes the LIVE gateway path
# (``GatewayProxyServer`` resolves the tier vid → pool → provider and fails over
# in-request), so the engine no longer probes models itself. Its "pool exhausted"
# and skipped-provider contracts are re-homed onto the gateway's own observability
# in ``api._tier_failover_note`` / the dry-pool early-return (ADR-0014 B4).


# ---------------------------------------------------------------------------
# Reviewer circuit breaker
# ---------------------------------------------------------------------------

class _State(Enum):
    CLOSED = auto()    # normal — calls forwarded
    OPEN = auto()      # tripped — calls rejected immediately
    HALF_OPEN = auto() # cooling down — one probe allowed


class ReviewerCircuitBreaker:
    """Wraps any ``Reviewer`` and trips after ``threshold`` consecutive failures.

    State machine:
      CLOSED  → OPEN      after ``threshold`` consecutive errors/exceptions
      OPEN    → HALF_OPEN after ``cooldown_s`` seconds
      HALF_OPEN → CLOSED  on a successful probe call
      HALF_OPEN → OPEN    on another failure (re-arms the cooldown)

    Thread-safe: a single ``threading.Lock`` guards all state mutations.
    """

    def __init__(
        self,
        reviewer: Reviewer,
        *,
        threshold: int = 3,
        cooldown_s: float = 60.0,
    ) -> None:
        self._reviewer = reviewer
        self._threshold = threshold
        self._cooldown_s = cooldown_s
        self._state = _State.CLOSED
        self._consecutive_failures = 0
        self._open_since: float = 0.0
        self._lock = threading.Lock()

    # ---------------------------------------------------------------- public
    @property
    def state(self) -> str:
        """Human-readable state name (for tests and diagnostics)."""
        return self._state.name.lower()

    def review(self, unit: WorkUnit, outcome: Outcome) -> Findings:
        with self._lock:
            state = self._maybe_transition()
            if state is _State.OPEN:
                raise ReviewerError(
                    f"circuit open after {self._threshold} consecutive failures"
                )

        try:
            result = self._reviewer.review(unit, outcome)
        except Exception as exc:
            with self._lock:
                self._record_failure()
            raise ReviewerError(str(exc)) from exc

        with self._lock:
            self._record_success()
        return result

    # ---------------------------------------------------------------- private
    def _maybe_transition(self) -> _State:
        """Compute (and apply) any time-driven transition; return current state."""
        if self._state is _State.OPEN:
            if time.monotonic() - self._open_since >= self._cooldown_s:
                self._state = _State.HALF_OPEN
        return self._state

    def _record_failure(self) -> None:
        self._consecutive_failures += 1
        if self._state is _State.HALF_OPEN or self._consecutive_failures >= self._threshold:
            self._state = _State.OPEN
            self._open_since = time.monotonic()

    def _record_success(self) -> None:
        self._consecutive_failures = 0
        self._state = _State.CLOSED
