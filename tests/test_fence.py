from __future__ import annotations

import os
from pathlib import Path

from charon.fence import Fence, detect_escape, snapshot_outside
from charon.types import Autonomy, PrivilegedOp


def test_default_deny_l0_propose_only() -> None:
    f = Fence(autonomy=Autonomy.L0)
    assert f.authorize(PrivilegedOp.PROPOSE) is True
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is False
    assert f.authorize(PrivilegedOp.DELETE) is False
    assert f.authorize(PrivilegedOp.DEPLOY) is False


def test_l1_allows_apply_reversible_only() -> None:
    f = Fence(autonomy=Autonomy.L1)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is True
    assert f.authorize(PrivilegedOp.DELETE) is False  # always denied


def test_l2_requires_consensus() -> None:
    f = Fence(autonomy=Autonomy.L2)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=False) is False
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=True) is True


def test_l3_full_auto_within_fence_but_destructive_still_denied() -> None:
    f = Fence(autonomy=Autonomy.L3)
    assert f.authorize(PrivilegedOp.APPLY_REVERSIBLE) is True
    assert f.authorize(PrivilegedOp.DELETE) is False


def test_scrubbed_env_blocks_global_git_and_drops_secrets() -> None:
    os.environ["AWS_SECRET_ACCESS_KEY"] = "leak-me"
    try:
        env = Fence.scrubbed_env(Path("/tmp/wt"))
        assert "AWS_SECRET_ACCESS_KEY" not in env
        assert env["GIT_CONFIG_GLOBAL"] == os.devnull
        assert env["HOME"] == "/tmp/wt"
    finally:
        del os.environ["AWS_SECRET_ACCESS_KEY"]


def test_escape_detection(tmp_path: Path) -> None:
    worktree = tmp_path / "repo"
    worktree.mkdir()
    guard = tmp_path
    before = snapshot_outside(worktree, guard)
    # write OUTSIDE the worktree (sibling) -> must be detected
    (tmp_path / "escaped.txt").write_text("pwned")
    escaped = detect_escape(worktree, guard, before)
    assert any("escaped.txt" in e for e in escaped)
    # a write INSIDE the worktree is fine
    before2 = snapshot_outside(worktree, guard)
    (worktree / "ok.txt").write_text("fine")
    assert detect_escape(worktree, guard, before2) == []
