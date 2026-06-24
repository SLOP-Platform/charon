"""Control-plane fence & autonomy ladder (ADR-0001 §6 / ADR-0003 §7).

Privileged actions default-deny; the operator sets the level. Tier 1 default is
**L0 (propose-only)** — nothing is applied (reconciliation BR-2).

Honesty register: the fence is a *policy* gate plus subprocess hardening and a
post-run escape scan. It is NOT, by itself, OS-level isolation. The structural
boundary for a live skip-permissions agent is the Mode B container (ADR-0002
§2.3). This module makes escapes *detectable and refusable*; the container makes
them *impossible*.
"""
from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from .types import Autonomy, PrivilegedOp

# Minimal env passed to spawned agents. Everything else is scrubbed so a backend
# cannot inherit credentials, LD_PRELOAD, JAVA_TOOL_OPTIONS, etc.
_ENV_ALLOW = ("PATH", "TERM", "LANG", "LC_ALL", "TZ")

# Operations that stay denied at every Tier-1 level — destructive and
# irreversible (ADR-0003 §7: destructive ops always gated by predicate).
_ALWAYS_DENIED = {PrivilegedOp.DELETE, PrivilegedOp.DEPLOY}

# L2+ (apply-with-consensus / full-auto) is only honestly safe inside the Mode-B
# container — the in-process fence detects escapes but does not bound a live
# agent (ADR-0002 §2.3 / INV-B4). These env vars gate it structurally (Tier 4).
_CONTAINER_ENV = "CHARON_CONTAINER_VERIFIED"  # set =1 by the Mode-B image
_UNCONTAINED_OVERRIDE = "CHARON_ALLOW_UNCONTAINED_AUTONOMY"  # explicit, loud opt-out


class FenceDenied(PermissionError):
    """Raised when a privileged op is refused by the fence."""


@dataclass
class Fence:
    autonomy: Autonomy = Autonomy.L0

    def assert_environment(self) -> None:
        """Refuse L2+ autonomy outside the Mode-B container (ADR-0002 §2.3 /
        INV-B4): unattended apply-with-consensus and full-auto must run where the
        container is the real boundary, not the in-process fence. An operator may
        opt out explicitly and loudly (``CHARON_ALLOW_UNCONTAINED_AUTONOMY=1``)
        for testing — never silently."""
        if self.autonomy < Autonomy.L2:
            return
        if os.environ.get(_CONTAINER_ENV) == "1":
            return
        if os.environ.get(_UNCONTAINED_OVERRIDE) == "1":
            return
        raise FenceDenied(
            f"autonomy {self.autonomy.name} requires the Mode-B container "
            f"(it sets {_CONTAINER_ENV}=1) — the in-process fence does not bound a "
            f"live agent (ADR-0002 §2.3). To run uncontained anyway, set "
            f"{_UNCONTAINED_OVERRIDE}=1 (dangerous; you accept the blast radius)."
        )

    def authorize(self, op: PrivilegedOp, *, consensus: bool = False) -> bool:
        """Default-deny predicate. Returns True iff the op is permitted at the
        current autonomy level."""
        if op in _ALWAYS_DENIED:
            return False
        if op is PrivilegedOp.PROPOSE:
            return True  # producing a diff is always allowed; applying is not
        if op is PrivilegedOp.APPLY_REVERSIBLE:
            if self.autonomy >= Autonomy.L2:
                return consensus or self.autonomy >= Autonomy.L3
            return self.autonomy >= Autonomy.L1
        return False

    def require(self, op: PrivilegedOp, *, consensus: bool = False) -> None:
        if not self.authorize(op, consensus=consensus):
            raise FenceDenied(
                f"{op.value} denied at autonomy {self.autonomy.name}"
                + ("" if consensus else " (no consensus)")
            )

    @staticmethod
    def scrubbed_env(worktree: Path) -> dict[str, str]:
        """Build the minimal, hardened environment for a spawned agent."""
        env = {k: os.environ[k] for k in _ENV_ALLOW if k in os.environ}
        env["HOME"] = str(worktree)
        # Block git global/system config poisoning from inside the agent.
        env["GIT_CONFIG_GLOBAL"] = os.devnull
        env["GIT_CONFIG_SYSTEM"] = os.devnull
        env["CHARON_FENCED"] = "1"
        return env


def snapshot_outside(worktree: Path, guard_dir: Path) -> dict[str, float]:
    """Record mtimes of everything under ``guard_dir`` that is OUTSIDE the
    worktree, so a post-run scan can detect writes that escaped (BR-2)."""
    worktree = worktree.resolve()
    guard_dir = guard_dir.resolve()
    snap: dict[str, float] = {}
    for p in guard_dir.rglob("*"):
        rp = p.resolve()
        if worktree in rp.parents or rp == worktree:
            continue
        try:
            snap[str(rp)] = rp.stat().st_mtime
        except OSError:
            continue
    return snap


def detect_escape(
    worktree: Path, guard_dir: Path, before: dict[str, float]
) -> list[str]:
    """Return paths outside the worktree that were created or modified since the
    ``before`` snapshot. A non-empty result means the run escaped the fence and
    MUST be rejected, not applied."""
    after = snapshot_outside(worktree, guard_dir)
    escaped: list[str] = []
    for path, mtime in after.items():
        if path not in before or before[path] != mtime:
            escaped.append(path)
    return sorted(escaped)
