"""Pluggable capacity-limiter seam (ADR-0010 D2 / E2).

The scheduler must not let one tier (e.g. expensive ``opus`` workers) saturate
the warm-ACP pool. The *limiter* is the small seam that gates per-tier
concurrency: before launching a claimed unit the scheduler asks the limiter for a
slot for that unit's tier, and returns the slot when the unit finishes.

This module ships the seam + two implementations:

- :class:`CapacityLimiter` — the Protocol (``try_acquire`` / ``release``).
- :class:`FixedCap` — a thread-safe, fixed per-tier cap from config (the default).
- :class:`AimdCap` — an adaptive (additive-increase / multiplicative-decrease)
  per-tier cap, **off by default** (selected only by config — E10).
- :func:`select_limiter` — the selector the scheduler consults.

**AIMD stays OFF by default** (ADR-0010 D5; DECISIONS D004 — adaptive capacity is
*trust-extending* automation, gated until a real run saturates a tier). :class:`AimdCap`
plugs into the SAME Protocol :class:`FixedCap` uses, so the scheduler is unchanged: it
only ever sees a :class:`CapacityLimiter`. :class:`AimdCap` widens its cap on a success
streak (``record_success``) and shrinks it multiplicatively on failure/backpressure
(``record_failure``), clamped to ``[floor, ceiling]``; those feedback hooks are extra to
the Protocol, so a consumer wires them only when it opts AIMD in via :func:`select_limiter`.

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


class AimdCap:
    """An adaptive (AIMD) per-tier concurrency cap — **off by default**.

    Each tier carries a *current* cap that starts at ``start`` (defaults to
    ``floor`` — conservative) and moves on observed signals:

    - **additive increase** — ``record_success(tier)`` raises the cap by ``step``
      (a sustained success streak slowly opens the tier up), capped at ``ceiling``;
    - **multiplicative decrease** — ``record_failure(tier)`` multiplies the cap by
      ``factor`` (``0 < factor < 1``) and floors it, so backpressure backs off
      fast, never below ``floor``.

    The cap is always clamped to ``[floor, ceiling]``. Counting and adaptation are
    guarded by one lock, so the limiter is race-free across the scheduler's worker
    threads. ``try_acquire`` / ``release`` satisfy the same :class:`CapacityLimiter`
    Protocol :class:`FixedCap` does (so the scheduler needs no change); the
    ``record_*`` feedback hooks are *extra* — a consumer calls them only after it
    opts AIMD in (DECISIONS D004: AIMD is trust-extending, never forced on).

    The internal cap is held as a float (so ``factor`` decreases compose cleanly);
    the admission threshold is its floor, :meth:`cap_for`.
    """

    def __init__(
        self,
        *,
        floor: int = 1,
        ceiling: int = 4,
        step: int = 1,
        factor: float = 0.5,
        start: int | None = None,
    ) -> None:
        if floor < 1:
            raise CapacityError(f"floor must be >= 1, got {floor}")
        if ceiling < floor:
            raise CapacityError(
                f"ceiling ({ceiling}) must be >= floor ({floor})"
            )
        if step < 1:
            raise CapacityError(f"step must be >= 1, got {step}")
        if not 0.0 < factor < 1.0:
            raise CapacityError(f"factor must be in (0, 1), got {factor}")
        start = floor if start is None else start
        if not floor <= start <= ceiling:
            raise CapacityError(
                f"start ({start}) must be within [floor={floor}, ceiling={ceiling}]"
            )
        self._floor = floor
        self._ceiling = ceiling
        self._step = step
        self._factor = factor
        self._start = float(start)
        self._caps: dict[str, float] = {}
        self._active: dict[str, int] = {}
        self._lock = threading.Lock()

    def _clamp(self, cap: float) -> float:
        return max(float(self._floor), min(float(self._ceiling), cap))

    def cap_for(self, tier: str) -> int:
        """The tier's *current* integer admission cap (its float cap, floored)."""
        with self._lock:
            return int(self._caps.get(tier, self._start))

    def try_acquire(self, tier: str) -> bool:
        with self._lock:
            active = self._active.get(tier, 0)
            cap = int(self._caps.get(tier, self._start))
            if active >= cap:
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

    def record_success(self, tier: str) -> None:
        """Additive increase: widen ``tier``'s cap by ``step`` (clamped at ceiling)."""
        with self._lock:
            cap = self._caps.get(tier, self._start)
            self._caps[tier] = self._clamp(cap + self._step)

    def record_failure(self, tier: str) -> None:
        """Multiplicative decrease: shrink ``tier``'s cap by ``factor`` (floored)."""
        with self._lock:
            cap = self._caps.get(tier, self._start)
            self._caps[tier] = self._clamp(cap * self._factor)

    def active(self, tier: str) -> int:
        """Slots currently held for ``tier`` (introspection/tests)."""
        with self._lock:
            return self._active.get(tier, 0)


def select_limiter(
    limiter: CapacityLimiter | None = None,
    *,
    policy: str = "fixed",
    caps: Mapping[str, int] | None = None,
    default: int = 1,
    aimd: Mapping[str, object] | None = None,
) -> CapacityLimiter:
    """The selector the scheduler consults for its limiter.

    Precedence: an explicit ``limiter`` instance wins (test/consumer injection);
    otherwise ``policy`` chooses the implementation. ``policy`` defaults to
    ``"fixed"`` — the conservative :class:`FixedCap` built from ``caps`` /
    ``default`` — so **AIMD is never the default**; a consumer opts in with
    ``policy="aimd"`` (DECISIONS D004), tuned via the ``aimd`` kwargs mapping.
    """
    if limiter is not None:
        return limiter
    if policy == "fixed":
        return FixedCap(caps, default=default)
    if policy == "aimd":
        return AimdCap(**(aimd or {}))  # type: ignore[arg-type]
    raise CapacityError(
        f"unknown capacity policy {policy!r}; expected 'fixed' or 'aimd'"
    )
