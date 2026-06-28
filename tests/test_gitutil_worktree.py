"""Tests for add_worktree resilience to stale registrations."""
from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

from charon.gitutil import add_worktree, init_repo, remove_worktree


def _make_repo(tmp_path: Path) -> Path:
    repo = tmp_path / "repo"
    repo.mkdir()
    init_repo(repo)
    return repo


def test_add_worktree_clean(tmp_path: Path) -> None:
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    add_worktree(repo, dest, "HEAD")
    assert dest.exists()
    assert (dest / ".git").exists()


def test_add_worktree_stale_registration(tmp_path: Path) -> None:
    """Recover when a stale .git/worktrees entry exists but the dir is gone."""
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    add_worktree(repo, dest, "HEAD")
    # Simulate stale: nuke the worktree dir without telling git.
    shutil.rmtree(dest)
    # Re-run must succeed, not crash with exit 128.
    add_worktree(repo, dest, "HEAD")
    assert dest.exists()


def test_add_worktree_leftover_dir(tmp_path: Path) -> None:
    """Recover when dest already exists from a prior interrupted run."""
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    add_worktree(repo, dest, "HEAD")
    # Re-add without removing first (interrupted-run scenario).
    add_worktree(repo, dest, "HEAD")
    assert dest.exists()


def test_add_worktree_idempotent_repeated(tmp_path: Path) -> None:
    """Multiple sequential re-runs to the same path all succeed."""
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    for _ in range(3):
        add_worktree(repo, dest, "HEAD")
        assert dest.exists()


def test_add_worktree_locked_raises(tmp_path: Path) -> None:
    """A git-locked worktree is NOT silently stomped — the real error surfaces."""
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    add_worktree(repo, dest, "HEAD")
    subprocess.run(
        ["git", "worktree", "lock", str(dest)], cwd=str(repo), check=True
    )
    try:
        with pytest.raises(subprocess.CalledProcessError):
            add_worktree(repo, dest, "HEAD")
    finally:
        subprocess.run(
            ["git", "worktree", "unlock", str(dest)], cwd=str(repo), check=False
        )
        remove_worktree(repo, dest)


def test_remove_worktree_best_effort(tmp_path: Path) -> None:
    """remove_worktree never raises even when worktree is already gone."""
    repo = _make_repo(tmp_path)
    dest = tmp_path / "wt" / "unit1"
    add_worktree(repo, dest, "HEAD")
    remove_worktree(repo, dest)
    # Calling again on an already-removed worktree must not raise.
    remove_worktree(repo, dest)
