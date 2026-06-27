"""Pluggable capacity-limiter seam (ADR-0010 D2 / E2).

The scheduler must not let one tier (e.g. expensive ``opus`` workers) saturate
the warm-ACP pool. The *limiter* is the small seam that gates per-tier
concurrency: before launching a claimed unit the scheduler asks the limiter for a
slot for that unit's tier, and returns the slot when the unit finishes.

This module ships ONLY the seam + a conservative default:

- :class:`CapacityLimiter` — the Protocol (``try_acquire`` / ``release``).
- :class:`FixedCap` — a thread-safe, fixed per-tier cap from config (the default).
- :func:`select_limiter` — the selector the scheduler consults.

**AIMD is deliberately NOT built here.** Adaptive capacity stays gated until a
real run saturates a tier (ADR-0010 D5; DECISIONS D004). It plugs in *later*
(ticket E10) by adding an adaptive ``CapacityLimiter`` to this file and teaching
:func:`select_limiter` to pick it — no scheduler change. Building the seam now is
justified because that consumer is committed, not speculative.

Stdlib-only (ADR-0005 R3 / ADR-0010 D2): ``threading`` + typing, nothing else.
"""
from __future__ import annotations

import threading
from collections.abc import Mapping
from typing import Protocol, runtime_checkable


class CapacityError(RuntimeError):
    """Raised on an illegal limiter op (e.g. a release without an acquire)."""


@runtime_checkable
class CapacityLimiter(Protocol):
    """Gate per-tier concurrency. Non-blocking by contract: ``try_acquire``
    returns ``False`` rather than waiting, so the scheduler stays in control of
    *when* it retries (it defers the unit and re-checks after a sibling frees a
    slot) instead of parking a thread inside the limiter."""

    def try_acquire(self, tier: str) -> bool:
        """Take one slot for ``tier`` if one is free; ``True`` iff acquired."""
        ...

    def release(self, tier: str) -> None:
        """Return one previously-acquired slot for ``tier``."""
        ...


class FixedCap:
    """A conservative, fixed per-tier concurrency cap (the default limiter).

    ``caps`` maps a tier name to its max concurrent slots; any tier not named
    uses ``default``. Counting is guarded by one lock, so ``try_acquire`` /
    ``release`` are race-free across the scheduler's worker threads. This is the
    *fixed* baseline ADR-0010 D5 mandates until a run proves a tier can take more;
    AIMD replaces only the count, never the seam.
    """

    def __init__(
        self, caps: Mapping[str, int] | None = None, *, default: int = 1
    ) -> None:
        if default < 1:
            raise CapacityError(f"default cap must be >= 1, got {default}")
        bad = {t: c for t, c in (caps or {}).items() if c < 1}
        if bad:
            raise CapacityError(f"per-tier caps must be >= 1, got {bad}")
        self._caps: dict[str, int] = dict(caps or {})
        self._default = default
        self._active: dict[str, int] = {}
        self._lock = threading.Lock()

    def cap_for(self, tier: str) -> int:
        """The configured concurrency cap for ``tier``."""
        return self._caps.get(tier, self._default)

    def try_acquire(self, tier: str) -> bool:
        with self._lock:
            active = self._active.get(tier, 0)
            if active >= self.cap_for(tier):
                return False
            self._active[tier] = active + 1
            return True

    def release(self, tier: str) -> None:
        with self._lock:
            active = self._active.get(tier, 0)
            if active <= 0:
                raise CapacityError(
                    f"release for tier {tier!r} without a matching acquire"
                )
            self._active[tier] = active - 1

    def active(self, tier: str) -> int:
        """Slots currently held for ``tier`` (introspection/tests)."""
        with self._lock:
            return self._active.get(tier, 0)


def select_limiter(
    limiter: CapacityLimiter | None = None,
    *,
    caps: Mapping[str, int] | None = None,
    default: int = 1,
) -> CapacityLimiter:
    """The selector the scheduler consults for its limiter.

    Returns ``limiter`` as-is when one is supplied (the E10 AIMD limiter will be
    selected here); otherwise builds the conservative :class:`FixedCap` default
    from ``caps`` / ``default``.
    """
    if limiter is not None:
        return limiter
    return FixedCap(caps, default=default)
