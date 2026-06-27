"""Engine scheduler tests (ADR-0010 D2 / E2). Proven-red on the binding rules:

  - a unit runs THROUGH the fenced ``coordinator.run`` (an ESCAPE backend yields
    ``status == "escaped"`` — a verdict only the fence escape-scan produces), and
    the scheduler never dispatches a backend itself;
  - ``depends_on`` waves run in dependency order;
  - disjoint units run concurrently;
  - the capacity limiter bounds per-tier concurrency;
  - a failed unit releases its claim (back to ready for retry, epoch-fenced).
"""
from __future__ import annotations

import threading
import time
from pathlib import Path

import pytest

from charon.adapters.mock import MockBackend, MockMode
from charon.coordinator import RunResult
from charon.engine.board import (
    BLOCKED,
    CLAIMED,
    DONE,
    READY,
    Board,
    Unit,
)
from charon.engine.capacity import CapacityError, FixedCap, select_limiter
from charon.engine.claim import _LOCK_TTL_SECONDS
from charon.engine.claim import claim as claim_unit
from charon.engine.claim import current as claim_current
from charon.engine.scheduler import (
    CoordinatorRunner,
    Disposition,
    Scheduler,
    default_classify,
)


# --------------------------------------------------------------------- helpers
def _board(tmp_path: Path, units: list[Unit]) -> Board:
    b = Board.create(tmp_path / "board.json")
    for u in units:
        b.add(u)
    return b


def _claims(tmp_path: Path) -> Path:
    d = tmp_path / "claims"
    d.mkdir(exist_ok=True)
    return d


def _wt_factory(tmp_path: Path):
    """A worktree factory that just hands back a fresh per-unit path string — no
    real git needed when the runner is a fake (claim only records the path)."""

    def make(unit: Unit) -> str:
        p = tmp_path / "wt" / unit.id
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    return make


class RecordingRunner:
    """A fake :class:`FencedRunner` that records start order + observed peak
    concurrency, optionally gated on a barrier, and returns a fixed status."""

    def __init__(self, status: str = "complete", *, barrier: threading.Barrier | None = None):
        self.status = status
        self._barrier = barrier
        self._lock = threading.Lock()
        self.started: list[str] = []
        self.active = 0
        self.peak = 0

    def __call__(self, unit: Unit, worktree: str, *, cost_gate) -> RunResult:
        with self._lock:
            self.started.append(unit.id)
            self.active += 1
            self.peak = max(self.peak, self.active)
        if self._barrier is not None:
            try:
                self._barrier.wait(timeout=5)
            except threading.BrokenBarrierError:
                pass
        with self._lock:
            self.active -= 1
        return RunResult(status=self.status, checkpoints=1)


# --------------------------------------------------------------- capacity seam
def test_fixedcap_bounds_per_tier() -> None:
    cap = FixedCap({"opus": 2}, default=1)
    assert cap.try_acquire("opus") and cap.try_acquire("opus")
    assert not cap.try_acquire("opus")  # tier full at 2
    assert cap.try_acquire("haiku")  # different tier uses default=1
    assert not cap.try_acquire("haiku")
    cap.release("opus")
    assert cap.try_acquire("opus")


def test_fixedcap_release_without_acquire_is_loud() -> None:
    cap = FixedCap()
    with pytest.raises(CapacityError):
        cap.release("opus")


def test_select_limiter_default_and_passthrough() -> None:
    assert isinstance(select_limiter(), FixedCap)
    mine = FixedCap({"x": 3})
    assert select_limiter(mine) is mine


def test_default_classify() -> None:
    assert default_classify("complete") is Disposition.DONE
    assert default_classify("error") is Disposition.RETRY
    assert default_classify("exhausted") is Disposition.RETRY
    assert default_classify("budget") is Disposition.RETRY
    assert default_classify("escaped") is Disposition.BLOCKED
    assert default_classify("blocked") is Disposition.BLOCKED


# ------------------------------------------------- THROUGH the fence (D008)
def test_unit_runs_through_fenced_coordinator(tmp_path: Path) -> None:
    """The CRITICAL property: the scheduler drives the unit through the EXISTING
    fenced ``coordinator.run`` — proven by an ESCAPE backend coming back
    ``escaped`` (only the fence escape-scan produces that), via the default
    ``CoordinatorRunner`` with NO bespoke dispatch path in the scheduler."""
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"], accept=["test -f x"])])
    runner = CoordinatorRunner(
        state_dir=str(tmp_path / "state"),
        backend_factory=lambda unit, checks: {"mock": MockBackend(mode=MockMode.ESCAPE)},
        autonomy="L1",
    )
    sched = Scheduler(
        board, _claims(tmp_path), runner, state_dir=str(tmp_path / "state"),
    )
    out = sched.drain()
    assert [r.status for r in out.results] == ["escaped"]
    # escaped is a rejection → BLOCKED on the board, claim released.
    assert board.get("u1").state == BLOCKED
    assert claim_current(_claims(tmp_path), "u1") is None


def test_satisfying_unit_completes_and_advances(tmp_path: Path) -> None:
    """A well-behaved backend at L1 reaches ``complete`` through the fence and the
    board is advanced to DONE; the claim is released."""
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"], accept=["test -f f.txt"])])
    runner = CoordinatorRunner(
        state_dir=str(tmp_path / "state"),
        backend_factory=lambda unit, checks: {"mock": MockBackend.satisfying(checks)},
        autonomy="L1",
    )
    sched = Scheduler(board, _claims(tmp_path), runner, state_dir=str(tmp_path / "state"))
    out = sched.drain()
    assert [r.status for r in out.results] == ["complete"]
    assert board.get("u1").state == DONE
    assert claim_current(_claims(tmp_path), "u1") is None


# --------------------------------------------------------------- waves in order
def test_depends_on_waves_run_in_order(tmp_path: Path) -> None:
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"], depends_on=["u1"]),
        ],
    )
    runner = RecordingRunner(status="complete")
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
    )
    out = sched.drain()
    assert runner.started == ["u1", "u2"]  # dep before dependent
    assert board.get("u1").state == DONE and board.get("u2").state == DONE
    assert out.rounds >= 2  # two waves


def test_dependent_blocked_when_dep_not_done(tmp_path: Path) -> None:
    """If the dep does not reach DONE (transient failure → RETRY/READY), the
    dependent never becomes claimable, so it never runs in this drain."""
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"], depends_on=["u1"]),
        ],
    )
    runner = RecordingRunner(status="error")  # dep fails → RETRY → stays READY
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
    )
    sched.drain()
    assert runner.started == ["u1"]  # u2 never claimable (dep not DONE)
    assert board.get("u1").state == READY  # released for retry
    assert board.get("u2").state == READY


# ------------------------------------------------------- disjoint concurrency
def test_disjoint_units_run_concurrently(tmp_path: Path) -> None:
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"]),
            Unit(id="u3", tier="opus", owns=["c.py"]),
        ],
    )
    barrier = threading.Barrier(3)  # all three must be in-flight together to pass
    runner = RecordingRunner(status="complete", barrier=barrier)
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
        limiter=FixedCap(default=3), max_parallel=3,
    )
    out = sched.drain()
    assert runner.peak == 3  # genuinely concurrent (barrier only clears at 3)
    assert all(board.get(i).state == DONE for i in ("u1", "u2", "u3"))
    assert out.rounds == 1


# ------------------------------------------------------- capacity bounds it
def test_capacity_limiter_bounds_concurrency(tmp_path: Path) -> None:
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"]),
            Unit(id="u3", tier="opus", owns=["c.py"]),
        ],
    )
    # No barrier: with cap=1 the units MUST serialize, so peak concurrency is 1.
    runner = RecordingRunner(status="complete")
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
        limiter=FixedCap({"opus": 1}), max_parallel=4,
    )
    sched.drain()
    assert runner.peak == 1  # capacity cap, not the pool, bounded it
    assert sorted(runner.started) == ["u1", "u2", "u3"]  # all still ran
    assert all(board.get(i).state == DONE for i in ("u1", "u2", "u3"))
    # slots are balanced — none leaked.
    assert sched.limiter.active("opus") == 0  # type: ignore[attr-defined]


# ------------------------------------------------- failed unit releases claim
def test_failed_unit_releases_its_claim(tmp_path: Path) -> None:
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"])])
    claims = _claims(tmp_path)
    runner = RecordingRunner(status="error")  # transient failure → RETRY
    sched = Scheduler(
        board, claims, runner, worktree_factory=_wt_factory(tmp_path),
    )
    out = sched.drain()
    assert out.results[0].disposition is Disposition.RETRY
    assert claim_current(claims, "u1") is None  # claim RELEASED
    assert board.get("u1").state == READY  # released for retry, not stuck CLAIMED


def test_runner_exception_is_isolated_and_releases(tmp_path: Path) -> None:
    """A runner that raises is captured as ``error`` (the pool is never torn
    down), the claim is released, and the unit is freed for retry."""
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"])])
    claims = _claims(tmp_path)

    def boom(unit: Unit, worktree: str, *, cost_gate) -> RunResult:
        raise RuntimeError("backend blew up")

    sched = Scheduler(board, claims, boom, worktree_factory=_wt_factory(tmp_path))
    out = sched.drain()
    assert out.results[0].status == "error"
    assert "backend blew up" in out.results[0].note
    assert claim_current(claims, "u1") is None
    assert board.get("u1").state == READY


# ------------------------------------------------------------- attempt cap
def test_attempt_cap_prevents_relaunch_within_drain(tmp_path: Path) -> None:
    """A perpetually-failing unit is launched at most ``max_attempts`` per drain —
    it does not spin the loop; it is left READY for a future drain."""
    board = _board(tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"])])
    runner = RecordingRunner(status="error")
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
        max_attempts=1,
    )
    sched.drain()
    assert runner.started == ["u1"]  # launched exactly once, no spin
    assert board.get("u1").state == READY


# ------------------------------------------------------------- in-wave collision
def test_in_wave_owns_collision_serializes(tmp_path: Path) -> None:
    """Two ready units sharing an owned path never run concurrently — the lower id
    runs first (board collision rule), then the other."""
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["shared/x.py"]),
            Unit(id="u2", tier="opus", owns=["shared/x.py"]),
        ],
    )
    runner = RecordingRunner(status="complete")
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=_wt_factory(tmp_path),
        limiter=FixedCap(default=4), max_parallel=4,
    )
    sched.drain()
    assert runner.peak == 1  # colliding owns serialized despite spare capacity
    assert runner.started == ["u1", "u2"]
    assert all(board.get(i).state == DONE for i in ("u1", "u2"))


# ------------------------------------------- RETRY actually re-runs (FB4 #2)
def test_retry_relaunches_and_lands(tmp_path: Path) -> None:
    """A unit that fails transiently once and succeeds on retry must actually land.
    The old runner re-called ``Ledger.create`` (which raises when ``ledger.json``
    exists), so every RETRY re-failed at ledger creation and looped to the attempt
    cap. With create-or-load the second attempt resumes the ledger and completes."""
    board = _board(
        tmp_path, [Unit(id="u1", tier="opus", owns=["a.py"], accept=["test -f f.txt"])]
    )
    calls = {"n": 0}

    def factory(unit: Unit, checks):  # type: ignore[no-untyped-def]
        calls["n"] += 1
        if calls["n"] == 1:
            return {"mock": MockBackend(mode=MockMode.EXHAUST)}  # transient → RETRY
        return {"mock": MockBackend.satisfying(checks)}  # second attempt succeeds

    runner = CoordinatorRunner(
        state_dir=str(tmp_path / "state"), backend_factory=factory, autonomy="L1"
    )
    sched = Scheduler(
        board, _claims(tmp_path), runner, state_dir=str(tmp_path / "state"),
        max_attempts=2,
    )
    out = sched.drain()
    assert [r.status for r in out.results] == ["exhausted", "complete"]
    assert out.results[0].disposition is Disposition.RETRY
    assert board.get("u1").state == DONE  # the retry actually landed
    assert claim_current(_claims(tmp_path), "u1") is None


# --------------------------------- claim failure releases the slot (FB4 #3)
def test_claim_failure_releases_slot_and_drain_continues(tmp_path: Path) -> None:
    """A non-``ClaimContended`` failure in the claim path (here a worktree-factory
    error) must release the capacity slot acquired just before AND not tear down the
    drain. With a single opus slot, a leaked slot would starve the sibling forever;
    the old code let the exception propagate out of the whole drain."""
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"]),
        ],
    )
    calls: dict[str, int] = {}

    def factory(unit: Unit) -> str:
        calls[unit.id] = calls.get(unit.id, 0) + 1
        if unit.id == "u1" and calls["u1"] == 1:
            raise RuntimeError("worktree factory blew up")
        p = tmp_path / "wt" / f"{unit.id}-{calls[unit.id]}"
        p.mkdir(parents=True, exist_ok=True)
        return str(p)

    runner = RecordingRunner(status="complete")
    sched = Scheduler(
        board, _claims(tmp_path), runner, worktree_factory=factory,
        limiter=FixedCap({"opus": 1}), max_parallel=4, max_attempts=2,
    )
    sched.drain()
    assert board.get("u2").state == DONE  # sibling ran — slot was not leaked
    assert board.get("u1").state == DONE  # recovered on its second attempt
    assert sorted(runner.started) == ["u1", "u2"]
    assert sched.limiter.active("opus") == 0  # type: ignore[attr-defined]


# ----------------------- stale release does not abort siblings (FB4 #4)
def test_stale_release_does_not_abort_sibling_settlement(tmp_path: Path) -> None:
    """If a unit's epoch-fenced release raises ``StaleReclaim`` (a reclaim bumped
    the epoch mid-flight — the exact double-exec the fence detects), settlement of
    its in-flight siblings must NOT be aborted. The superseded unit is logged and
    left CLAIMED (the fresh holder owns it), the sibling still advances to DONE."""
    claims = _claims(tmp_path)
    board = _board(
        tmp_path,
        [
            Unit(id="u1", tier="opus", owns=["a.py"]),
            Unit(id="u2", tier="opus", owns=["b.py"]),
        ],
    )
    barrier = threading.Barrier(2)
    lock = threading.Lock()
    started: list[str] = []

    def runner(unit: Unit, worktree: str, *, cost_gate) -> RunResult:  # type: ignore[no-untyped-def]
        with lock:
            started.append(unit.id)
        barrier.wait(timeout=5)  # both units in flight together
        if unit.id == "u1":
            # Simulate a reclaim onto a FRESH worktree while this run is in flight:
            # it bumps the epoch, so the scheduler's release (under the old epoch)
            # is fenced out with StaleReclaim.
            claim_unit(
                claims, "u1", tmp_path / "reclaimed-wt",
                now=time.time() + _LOCK_TTL_SECONDS + 5,
            )
        return RunResult(status="complete", checkpoints=1)

    sched = Scheduler(
        board, claims, runner, worktree_factory=_wt_factory(tmp_path),
        limiter=FixedCap(default=2), max_parallel=2,
    )
    out = sched.drain()
    by_id = {r.unit_id: r for r in out.results}
    assert set(by_id) == {"u1", "u2"}  # the drain settled both (did not abort)
    assert by_id["u2"].disposition is Disposition.DONE
    assert board.get("u2").state == DONE  # sibling advanced normally
    # the superseded unit is logged-and-skipped, never advanced
    assert by_id["u1"].disposition is Disposition.SUPERSEDED
    assert board.get("u1").state == CLAIMED
