from __future__ import annotations

from pathlib import Path

from charon import coordinator, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend, MockMode
from charon.fence import Fence
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, Health, WorkUnit


def _setup(state_dir: Path, repo: Path, checks, backend):
    led = Ledger.create(state_dir, "t1", "goal", checks, str(repo), gitutil.head(repo))
    router = StaticRouter(backends=[backend.name])
    return led, {backend.name: backend}, router


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def test_mock_end_to_end_completes_at_l1(state_dir: Path, git_repo: Path) -> None:
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend.satisfying(checks)
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)
    assert res.status == "complete"
    assert res.remaining == []
    assert led.lkg_ref != led.base_ref  # lkg advanced past base
    assert (git_repo / "hello.txt").exists()


def test_l0_propose_only_applies_nothing(state_dir: Path, git_repo: Path) -> None:
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend.satisfying(checks)
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L0), router)
    assert res.status == "blocked"  # propose-only never "completes" applied work
    assert led.lkg_ref == led.base_ref  # nothing applied
    assert not (git_repo / "hello.txt").exists()  # worktree rolled back
    # but the proposal WAS recorded as a checkpoint
    assert len(led.checkpoints()) == 1


def test_lying_backend_cannot_fake_done(state_dir: Path, git_repo: Path) -> None:
    # BR-6 adversarial: backend claims PROGRESSED + commits, satisfies nothing.
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend(mode=MockMode.LIE)
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)
    assert res.status == "budget"  # never completes
    assert "a0" in res.remaining
    assert led.lkg_ref == led.base_ref  # lkg NEVER advanced past unverified (INV-2)


def test_escape_is_rejected_and_rolled_back(state_dir: Path, git_repo: Path) -> None:
    # BR-2 adversarial: backend writes outside the worktree.
    escape = git_repo.parent / "escaped.txt"
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend(mode=MockMode.ESCAPE, escape_path=escape)
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)
    assert res.status == "escaped"
    assert led.lkg_ref == led.base_ref  # not applied
    assert "escape" in res.note.lower()


def test_exhaustion_with_single_backend_stops_cleanly(state_dir: Path, git_repo: Path) -> None:
    # H4: exhaustion detected via health(); no handoff target -> clean stop.
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend(mode=MockMode.EXHAUST,
                          health=Health(budget_remaining=False))
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)
    assert res.status == "exhausted"
    assert led.lkg_ref == led.base_ref  # no progress lost, none falsely applied


def test_multi_checkpoint_accumulates(state_dir: Path, git_repo: Path) -> None:
    checks = [AcceptanceCheck("a0", "test -f a.txt"), AcceptanceCheck("a1", "test -f b.txt")]
    backend = MockBackend(mode=MockMode.SATISFY, creates=["a.txt", "b.txt"])
    led, backends, router = _setup(state_dir, git_repo, checks, backend)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)
    assert res.status == "complete"
    assert sorted(res.verified) == ["a0", "a1"]
