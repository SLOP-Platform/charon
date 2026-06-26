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


# --------------------------------------------------------------- PERF-4 (T1)

def test_sandbox_repo_is_nested_per_unit_for_guard_isolation(tmp_path: Path) -> None:
    """D2/CONC-1: the demo sandbox repo nests at ``sandbox/<task_id>/repo`` so a
    unit's guard_dir (= the repo's parent) is UNIQUE per unit — a sibling unit's
    legitimate writes can never be seen by this unit's escape scan."""
    from charon import api

    out_a = api.run_task(goal="alpha unit", accept=["test -f hello.txt"],
                         state_dir=str(tmp_path / "state"), backend_name="mock",
                         autonomy="L1")
    out_b = api.run_task(goal="beta unit", accept=["test -f hello.txt"],
                         state_dir=str(tmp_path / "state"), backend_name="mock",
                         autonomy="L1")
    repo_a, repo_b = Path(out_a["target_repo"]), Path(out_b["target_repo"])
    # each sandbox repo is nested one level under its own <task_id> dir …
    assert repo_a.name == "repo" and repo_b.name == "repo"
    # … so the guard parents are distinct per unit (no shared sandbox parent).
    assert repo_a.parent != repo_b.parent
    assert repo_a.parent.name == out_a["task_id"]
    assert repo_b.parent.name == out_b["task_id"]


def test_sandbox_escape_into_own_guard_dir_is_rejected(tmp_path: Path) -> None:
    """The per-unit guard_dir still catches an escape into the unit's OWN tree
    (writes alongside the nested repo), so narrowing the guard did not blind it."""
    state = tmp_path / "state"
    # First create the ledger+sandbox the normal way to learn the task path…
    # then drive the loop with an ESCAPE backend whose target is inside the guard.
    led_task = api_make_unit_ledger(state, "escape demo", ["test -f hello.txt"])
    repo = Path(led_task.target_repo)
    escape = repo.parent / "escaped.txt"  # inside guard_dir, outside the worktree
    backend = MockBackend(mode=MockMode.ESCAPE, escape_path=escape)
    router = StaticRouter(backends=[backend.name])
    res = coordinator.run(WorkUnit(task_id=led_task.task_id, goal="escape demo"),
                          {backend.name: backend}, led_task, Fence(Autonomy.L1), router)
    assert res.status == "escaped"
    assert led_task.lkg_ref == led_task.base_ref


def api_make_unit_ledger(state: Path, goal: str, accept: list[str]) -> Ledger:
    """Build a sandbox-backed ledger the way the API does (nested repo)."""
    from charon import api
    sdir = Path(state).resolve()
    task_id = api.make_task_id(goal)
    target = api._prepare_repo(None, sdir, task_id)
    checks = [AcceptanceCheck(f"a{i}", c) for i, c in enumerate(accept)]
    return Ledger.create(sdir, task_id, goal, checks, target, gitutil.head(Path(target)))
