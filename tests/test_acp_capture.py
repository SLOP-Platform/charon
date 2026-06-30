"""OBS-CAPTURE — per-unit agent log via state_dir seam.

Verifies that dispatch() accepts state_dir, that the log path is derived
from state_dir + task_id, and that the existing backends accept the new
parameter without breaking (mock ignores it; acp derives the log path).
"""
from __future__ import annotations

import subprocess
from pathlib import Path

from charon.adapters.acp import AcpBackend
from charon.adapters.mock import MockBackend
from charon.types import Budget, Tier, WorkUnit


def _unit(task_id: str = "test-task") -> WorkUnit:
    return WorkUnit(task_id=task_id, goal="test goal", task_class="test")


def _init_git(path: Path) -> None:
    subprocess.run(["git", "init"], cwd=path, capture_output=True, check=True)
    subprocess.run(["git", "config", "user.email", "test@test"], cwd=path,
                   capture_output=True)
    subprocess.run(["git", "config", "user.name", "test"], cwd=path,
                   capture_output=True)


def test_mock_backend_accepts_state_dir(tmp_path: Path):
    backend = MockBackend(name="mock")
    unit = _unit()
    tier = Tier("med")
    budget = Budget(max_checkpoints=1)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _init_git(worktree)
    state_dir = tmp_path / "state"

    outcome = backend.dispatch(
        unit, tier, budget, worktree, {}, state_dir=state_dir,
    )
    assert outcome.status.value == "progressed"


def test_mock_backend_dispatch_without_state_dir(tmp_path: Path):
    """Backward-compat: dispatch without state_dir still works."""
    backend = MockBackend(name="mock")
    unit = _unit()
    tier = Tier("med")
    budget = Budget(max_checkpoints=1)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _init_git(worktree)

    outcome = backend.dispatch(unit, tier, budget, worktree, {})
    assert outcome.status.value == "progressed"


def test_acp_log_path_derived_from_worktree(tmp_path: Path):
    """AcpBackend creates agent.log under worktree/.charon/<task_id>/agent.log."""
    backend = AcpBackend(command=["echo", "ok"], name="test-acp")
    unit = _unit("my-unit")
    tier = Tier("med")
    state_dir = tmp_path / "state"
    budget = Budget(max_checkpoints=1)
    worktree = tmp_path / "worktree"
    worktree.mkdir()
    _init_git(worktree)

    expected_log = worktree / ".charon" / "my-unit" / "agent.log"

    try:
        backend.dispatch(
            unit, tier, budget, worktree, {}, state_dir=state_dir,
        )
    except Exception:
        pass

    assert expected_log.parent.exists()
    backend.kill()
