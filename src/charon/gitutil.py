"""Tiny git helpers. The target repo's git history is the ground truth for
``lkg_ref`` and rollback (reconciliation OOB-C4: git is the source of truth)."""
from __future__ import annotations

import subprocess
from pathlib import Path


def _run(args: list[str], cwd: Path) -> str:
    proc = subprocess.run(
        ["git", *args], cwd=str(cwd), capture_output=True, text=True, check=True
    )
    return proc.stdout.strip()


def is_repo(cwd: Path) -> bool:
    try:
        _run(["rev-parse", "--git-dir"], cwd)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False


def head(cwd: Path) -> str:
    return _run(["rev-parse", "HEAD"], cwd)


def init_repo(cwd: Path) -> str:
    """Init a repo with an empty root commit; return the base SHA."""
    _run(["init", "-q"], cwd)
    _run(["config", "user.email", "charon@localhost"], cwd)
    _run(["config", "user.name", "charon"], cwd)
    _run(["commit", "--allow-empty", "-q", "-m", "charon: base"], cwd)
    return head(cwd)


def commit_all(cwd: Path, message: str) -> str | None:
    """Stage and commit everything; return the new SHA, or None if nothing
    changed."""
    _run(["add", "-A"], cwd)
    status = _run(["status", "--porcelain"], cwd)
    if not status:
        return None
    _run(["commit", "-q", "-m", message], cwd)
    return head(cwd)


def reset_hard(cwd: Path, ref: str) -> None:
    _run(["reset", "--hard", "-q", ref], cwd)


def add_worktree(repo: Path, dest: Path, ref: str) -> None:
    """Add a linked git worktree of ``repo`` at ``dest``, checked out (detached)
    at ``ref``. The worktree shares ``repo``'s object store but is an isolated
    working tree — the per-unit isolation primitive (ADR-0007 D2). ``dest``'s
    parent is created first so the worktree nests one level down, making that
    parent a unit-unique ``guard_dir`` for the fence escape scan.

    Re-run-resilient: prunes stale registrations (entries whose directories no
    longer exist) and removes any leftover directory from a prior interrupted
    run before adding. A git-locked worktree resists the force-remove, so the
    subsequent add surfaces the real error rather than swallowing it."""
    dest.parent.mkdir(parents=True, exist_ok=True)
    # Remove stale .git/worktrees entries whose directories are gone.
    try:
        _run(["worktree", "prune"], repo)
    except (subprocess.CalledProcessError, FileNotFoundError):
        pass
    # If dest is already present (leftover from an interrupted run), tear it
    # down so the add starts clean.  A git-locked worktree rejects the single
    # --force; in that case dest still exists and the add below raises.
    if dest.exists():
        try:
            _run(["worktree", "remove", "--force", str(dest)], repo)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
    _run(["worktree", "add", "--detach", str(dest), ref], repo)


def remove_worktree(repo: Path, dest: Path) -> None:
    """Remove the linked worktree at ``dest`` (created by ``add_worktree``) and
    prune its admin entry. Best-effort: an already-removed/missing worktree is not
    an error — teardown must never raise."""
    for args in (["worktree", "remove", "--force", str(dest)], ["worktree", "prune"]):
        try:
            _run(args, repo)
        except (subprocess.CalledProcessError, FileNotFoundError):
            pass
