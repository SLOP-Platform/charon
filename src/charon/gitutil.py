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
