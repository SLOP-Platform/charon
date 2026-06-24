from __future__ import annotations

from pathlib import Path

import pytest

from charon import gitutil


@pytest.fixture
def git_repo(tmp_path: Path) -> Path:
    """A fresh git repo (the 'target' worktree) with an empty base commit."""
    repo = tmp_path / "repo"
    repo.mkdir()
    gitutil.init_repo(repo)
    return repo


@pytest.fixture
def state_dir(tmp_path: Path) -> Path:
    d = tmp_path / "state"
    d.mkdir()
    return d
