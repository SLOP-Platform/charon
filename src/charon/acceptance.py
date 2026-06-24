"""Executable acceptance — the first artifact Tier 1 needs (ADR-0003 §12).

An acceptance criterion is an *executable check*, never prose. ``verified`` is
derived by running the check against the current disk; ``remaining`` is then
``acceptance \\ verified`` (INV-6, machine-decidable).

Structural anti-prose property (reconciliation BR-5): there is no prose field.
Prose passed as a command is simply *run* and will not exit 0, so it can never
become falsely "done" — it surfaces as loud, permanent incompletion.
"""
from __future__ import annotations

import shlex
import subprocess
import warnings
from dataclasses import dataclass

# Words that strongly suggest a human wrote a sentence, not a command.
_PROSE_HINTS = {"add", "ensure", "should", "make", "improve", "fix", "the", "comprehensive"}


@dataclass(frozen=True)
class AcceptanceCheck:
    """A single executable acceptance criterion.

    ``cmd`` is run via the shell in the target worktree; exit 0 == verified.
    """

    id: str
    cmd: str

    def __post_init__(self) -> None:
        if not self.cmd or not self.cmd.strip():
            raise ValueError(f"acceptance check {self.id!r} has an empty command")
        # Heuristic nudge only — the structural guarantee is that it is executed.
        try:
            tokens = [t.lower() for t in shlex.split(self.cmd)]
        except ValueError:
            tokens = self.cmd.lower().split()
        prose = sum(1 for t in tokens if t in _PROSE_HINTS)
        if len(tokens) >= 4 and prose >= 2:
            warnings.warn(
                f"acceptance check {self.id!r} looks like prose, not a command: "
                f"{self.cmd!r}. It will be executed verbatim and (almost certainly) "
                f"never pass. Use an executable check, e.g. 'pytest tests/test_x.py'.",
                stacklevel=2,
            )

    def verify(self, cwd: str, timeout: int = 600) -> bool:
        """Run the check against ``cwd``. True iff exit code 0."""
        try:
            proc = subprocess.run(
                self.cmd,
                shell=True,
                cwd=cwd,
                timeout=timeout,
                capture_output=True,
            )
        except subprocess.TimeoutExpired:
            return False
        return proc.returncode == 0

    def to_dict(self) -> dict:
        return {"id": self.id, "cmd": self.cmd}

    @classmethod
    def from_dict(cls, d: dict) -> AcceptanceCheck:
        return cls(id=d["id"], cmd=d["cmd"])


def derive_verified(checks: list[AcceptanceCheck], cwd: str) -> set[str]:
    """Return the ids of checks that currently pass against disk (GROUND)."""
    return {c.id for c in checks if c.verify(cwd)}


def derive_remaining(checks: list[AcceptanceCheck], cwd: str) -> set[str]:
    """``acceptance \\ verified`` — machine-derived, never stored as truth (INV-6)."""
    verified = derive_verified(checks, cwd)
    return {c.id for c in checks} - verified
