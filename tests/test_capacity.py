"""Tests for the engine capacity-limiter seam (ADR-0010 D2 / E2) and the AIMD
adaptive limiter that plugs into it (E10).

The seam contract (``CapacityLimiter``: ``try_acquire`` / ``release``) is shared by
the conservative :class:`FixedCap` default and the adaptive :class:`AimdCap`; the
scheduler only ever sees a ``CapacityLimiter``. AIMD is **off by default** — the
selector returns it only when explicitly configured.
"""
from __future__ import annotations

import pytest

from charon.engine.capacity import (
    AimdCap,
    CapacityError,
    CapacityLimiter,
    FixedCap,
    select_limiter,
)

# --------------------------------------------------------------- FixedCap (E2)

def test_fixedcap_caps_per_tier_and_releases() -> None:
    cap = FixedCap({"opus": 2}, default=1)
    assert cap.try_acquire("opus")
    assert cap.try_acquire("opus")
    assert not cap.try_acquire("opus")  # at cap=2
    cap.release("opus")
    assert cap.try_acquire("opus")  # slot freed
    # an unnamed tier uses the default cap
    assert cap.try_acquire("haiku")
    assert not cap.try_acquire("haiku")


def test_fixedcap_release_without_acquire_raises() -> None:
    cap = FixedCap(default=1)
    with pytest.raises(CapacityError):
        cap.release("opus")


# ---------------------------------------------------------- AIMD: the Protocol

def test_aimd_satisfies_the_capacity_protocol() -> None:
    assert isinstance(AimdCap(), CapacityLimiter)


def test_aimd_starts_conservative_at_floor() -> None:
    cap = AimdCap(floor=1, ceiling=4)
    assert cap.cap_for("opus") == 1  # default start == floor
    assert cap.try_acquire("opus")
    assert not cap.try_acquire("opus")  # floor cap of 1


def test_aimd_configurable_start() -> None:
    cap = AimdCap(floor=1, ceiling=4, start=2)
    assert cap.cap_for("opus") == 2
    assert cap.try_acquire("opus")
    assert cap.try_acquire("opus")
    assert not cap.try_acquire("opus")


# -------------------------------------------------- AIMD: additive increase

def test_aimd_increases_additively_on_success_streak() -> None:
    cap = AimdCap(floor=1, ceiling=4, step=1)
    assert cap.cap_for("opus") == 1
    cap.record_success("opus")
    assert cap.cap_for("opus") == 2  # +1
    cap.record_success("opus")
    assert cap.cap_for("opus") == 3  # +1 (additive, not doubling)
    cap.record_success("opus")
    assert cap.cap_for("opus") == 4


def test_aimd_increase_clamps_at_ceiling() -> None:
    cap = AimdCap(floor=1, ceiling=3, step=1)
    for _ in range(10):
        cap.record_success("opus")
    assert cap.cap_for("opus") == 3  # never exceeds ceiling


def test_aimd_increase_admits_more_concurrency() -> None:
    cap = AimdCap(floor=1, ceiling=4, step=1)
    assert cap.try_acquire("opus")
    assert not cap.try_acquire("opus")  # at floor cap of 1
    cap.record_success("opus")  # cap -> 2
    assert cap.try_acquire("opus")  # the widened slot is usable
    assert cap.active("opus") == 2


# ---------------------------------------------- AIMD: multiplicative decrease

def test_aimd_decreases_multiplicatively_on_failure() -> None:
    cap = AimdCap(floor=1, ceiling=8, step=1, factor=0.5, start=8)
    assert cap.cap_for("opus") == 8
    cap.record_failure("opus")
    assert cap.cap_for("opus") == 4  # 8 * 0.5 (multiplicative, not -1)
    cap.record_failure("opus")
    assert cap.cap_for("opus") == 2  # 4 * 0.5


def test_aimd_decrease_clamps_at_floor() -> None:
    cap = AimdCap(floor=2, ceiling=8, factor=0.5, start=4)
    cap.record_failure("opus")  # 4 * 0.5 = 2 (== floor)
    assert cap.cap_for("opus") == 2
    cap.record_failure("opus")  # 2 * 0.5 = 1 -> clamped to floor 2
    assert cap.cap_for("opus") == 2


def test_aimd_is_per_tier_independent() -> None:
    cap = AimdCap(floor=1, ceiling=4, step=1, factor=0.5, start=2)
    cap.record_success("opus")  # opus -> 3
    cap.record_failure("haiku")  # haiku -> 1
    assert cap.cap_for("opus") == 3
    assert cap.cap_for("haiku") == 1


def test_aimd_release_without_acquire_raises() -> None:
    cap = AimdCap()
    with pytest.raises(CapacityError):
        cap.release("opus")


# ------------------------------------------------------- AIMD: config validation

@pytest.mark.parametrize(
    "kwargs",
    [
        {"floor": 0},  # floor must be >= 1
        {"floor": 3, "ceiling": 2},  # ceiling < floor
        {"step": 0},  # step must be >= 1
        {"factor": 1.0},  # factor must be in (0, 1)
        {"factor": 0.0},
        {"floor": 1, "ceiling": 4, "start": 5},  # start outside [floor, ceiling]
    ],
)
def test_aimd_rejects_bad_config(kwargs: dict[str, object]) -> None:
    with pytest.raises(CapacityError):
        AimdCap(**kwargs)  # type: ignore[arg-type]


# --------------------------------------------------------------- the selector

def test_selector_defaults_to_fixedcap() -> None:
    limiter = select_limiter()
    assert isinstance(limiter, FixedCap)


def test_selector_explicit_policy_fixed() -> None:
    limiter = select_limiter(policy="fixed", caps={"opus": 2})
    assert isinstance(limiter, FixedCap)
    assert limiter.cap_for("opus") == 2


def test_selector_returns_aimd_only_when_configured() -> None:
    limiter = select_limiter(policy="aimd", aimd={"floor": 1, "ceiling": 4})
    assert isinstance(limiter, AimdCap)
    assert not isinstance(limiter, FixedCap)
    assert limiter.cap_for("opus") == 1


def test_selector_passes_injected_limiter_through() -> None:
    injected = AimdCap(floor=2, ceiling=6, start=2)
    assert select_limiter(injected) is injected
    # an injected instance wins even against a fixed policy
    assert select_limiter(injected, policy="fixed") is injected


def test_selector_rejects_unknown_policy() -> None:
    with pytest.raises(CapacityError):
        select_limiter(policy="bogus")
