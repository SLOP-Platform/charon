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
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from .config import SandboxPolicy, load_sandbox_policy
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
# UNCONTAINED L3 (full-auto, unattended, consensus gate REMOVED, no container
# boundary) needs its OWN distinct opt-in ON TOP of the uncontained override — the
# flag that unlocks L2 testing must not also reach the highest rung uncontained
# (ADR-0009 D-ESC-1). Inside the verified container L3 is already the blessed,
# bounded behaviour (PLAN-tier4 §6); this token only gates the uncontained climb.
_UNATTENDED_OPT_IN = "CHARON_ALLOW_UNATTENDED"  # explicit, loud, uncontained-L3-only

# Every env token the escalation gate reads. Kept here so callers (and tests) can
# assert the scrubbed agent env never carries them (ADR-0009 D-ESC-5): a fenced
# backend must not be able to read — let alone forge — the parent's autonomy.
ESCALATION_TOKENS = (_CONTAINER_ENV, _UNCONTAINED_OVERRIDE, _UNATTENDED_OPT_IN)


class FenceDenied(PermissionError):
    """Raised when a privileged op is refused by the fence."""


@dataclass(frozen=True)
class EscalationDecision:
    """The escalation gate's verdict for a requested autonomy level (ADR-0009).

    ``granted`` is the highest rung permitted by the environment that is also
    ``<= requested``; ``ceiling`` is the environment's hard cap regardless of the
    request. ``clamped`` means the environment forbids the requested level."""

    requested: Autonomy
    granted: Autonomy
    ceiling: Autonomy
    reason: str

    @property
    def clamped(self) -> bool:
        return self.granted < self.requested


@dataclass(frozen=True)
class AutonomyPolicy:
    """Per-rung, default-deny autonomy escalation gate (ADR-0009 D-ESC-1/2).

    Resolves a *requested* level against the environment. Each rung above L1 has
    its own precondition and a rung is grantable only if every lower rung's
    precondition also holds (monotone, non-skipping) — so the gate can never grant
    a rung over a forbidden one. This is a *policy*, not OS isolation: the Mode-B
    container stays the only real boundary for a live agent (INV-B4 / D-ESC-4).

    ``sandbox`` (D013): selects which precondition set is applied.
      ``hybrid``    — default; byte-for-byte current behavior.
      ``container`` — ALL rungs ≥L1 require the container; override refused.
      ``host``      — L0/L1 free; L2+ requires the loud override (container alone
                      insufficient — explicit acknowledgement required)."""

    contained: bool  # Mode-B container verified
    uncontained_override: bool  # loud opt-out: run L2+ uncontained anyway
    unattended_opt_in: bool  # distinct, loud opt-in required for L3 full-auto
    sandbox: SandboxPolicy = SandboxPolicy.HYBRID  # D013 posture selector

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> AutonomyPolicy:
        e = os.environ if env is None else env
        return cls(
            contained=e.get(_CONTAINER_ENV) == "1",
            uncontained_override=e.get(_UNCONTAINED_OVERRIDE) == "1",
            unattended_opt_in=e.get(_UNATTENDED_OPT_IN) == "1",
            sandbox=load_sandbox_policy(e),
        )

    def _rung_ok(self, level: Autonomy) -> bool:
        """Precondition for a SINGLE rung (no climb implied)."""
        if self.sandbox == SandboxPolicy.CONTAINER:
            # ALL rungs ≥L1 require the verified container; the uncontained
            # override path is refused (D013: container is the trust boundary).
            return self.contained
        if self.sandbox == SandboxPolicy.HOST:
            # Host is the declared environment. L0/L1 always OK. L2+ requires
            # the loud uncontained override — the container flag alone is not
            # sufficient; the operator must explicitly acknowledge the uncontained
            # blast radius even when containerized (D013).
            if level <= Autonomy.L1:
                return True
            if level is Autonomy.L2:
                return self.uncontained_override
            # L3: override PLUS the distinct unattended opt-in (D-ESC-1).
            return self.uncontained_override and self.unattended_opt_in
        # HYBRID (default): byte-for-byte current behavior (D013 regression gate).
        if level <= Autonomy.L1:
            return True  # L0 propose / L1 apply-reversible: always grantable
        # L2 (apply-with-consensus): container or the loud uncontained override.
        if level is Autonomy.L2:
            return self.contained or self.uncontained_override
        # L3 (full-auto, consensus removed): inside the verified container it is the
        # blessed, bounded behaviour. UNCONTAINED it is the highest-blast-radius
        # surface, so the uncontained override alone is NOT enough — it also needs
        # the distinct unattended opt-in (D-ESC-1).
        return self.contained or (self.uncontained_override and self.unattended_opt_in)

    def ceiling(self) -> Autonomy:
        """Highest *contiguous* grantable rung (monotone climb, D-ESC-2)."""
        top = Autonomy.L0
        for level in (Autonomy.L1, Autonomy.L2, Autonomy.L3):
            if not self._rung_ok(level):
                break
            top = level
        return top

    def resolve(self, requested: Autonomy) -> EscalationDecision:
        """Non-raising query (for diagnostics / ``doctor``): what the environment
        would grant for ``requested``. Enforcement uses ``Fence.assert_environment``
        which RAISES rather than silently clamping (D-ESC-3)."""
        cap = self.ceiling()
        granted = requested if requested <= cap else cap
        if granted >= requested:
            reason = f"{requested.name} permitted (ceiling {cap.name})"
        else:
            reason = self._deny_reason(requested)
        return EscalationDecision(requested, granted, cap, reason)

    def _deny_reason(self, requested: Autonomy) -> str:
        if self.sandbox == SandboxPolicy.CONTAINER:
            return (
                f"{requested.name} denied: sandbox=container requires "
                f"{_CONTAINER_ENV}=1 for ALL rungs — the uncontained override "
                f"path is refused in this policy (D013)."
            )
        if self.sandbox == SandboxPolicy.HOST:
            # In host policy L2+ needs the override; L3 additionally needs the
            # distinct unattended opt-in.  Container alone is not sufficient.
            if (
                requested is Autonomy.L3
                and self.uncontained_override
                and not self.unattended_opt_in
            ):
                return (
                    f"{requested.name} (full-auto, unattended) UNCONTAINED needs its "
                    f"own explicit opt-in {_UNATTENDED_OPT_IN}=1 on top of "
                    f"{_UNCONTAINED_OVERRIDE}=1 — it removes the consensus gate AND the "
                    f"container boundary, so the flag that unlocks L2 testing does NOT "
                    f"reach it (ADR-0009 D-ESC-1; dangerous, you accept the blast "
                    f"radius)."
                )
            return (
                f"{requested.name} requires {_UNCONTAINED_OVERRIDE}=1 "
                f"(sandbox=host: the loud override is required for L2+; the "
                f"container flag alone is not sufficient — you must explicitly "
                f"acknowledge the uncontained blast radius, D013)."
            )
        # HYBRID (default).
        # Uncontained L3 with the override but no distinct opt-in: the specific
        # hole this gate closes (D-ESC-1).
        if (
            requested is Autonomy.L3
            and self.uncontained_override
            and not self.contained
        ):
            return (
                f"{requested.name} (full-auto, unattended) UNCONTAINED needs its "
                f"own explicit opt-in {_UNATTENDED_OPT_IN}=1 on top of "
                f"{_UNCONTAINED_OVERRIDE}=1 — it removes the consensus gate AND the "
                f"container boundary, so the flag that unlocks L2 testing does NOT "
                f"reach it (ADR-0009 D-ESC-1; dangerous, you accept the blast "
                f"radius)."
            )
        return (
            f"{requested.name} requires the Mode-B container (it sets "
            f"{_CONTAINER_ENV}=1) — the in-process fence does not bound a live "
            f"agent (ADR-0002 §2.3). To run uncontained anyway, set "
            f"{_UNCONTAINED_OVERRIDE}=1 (dangerous; you accept the blast radius)."
        )


@dataclass
class Fence:
    autonomy: Autonomy = Autonomy.L0

    def assert_environment(self, env: Mapping[str, str] | None = None) -> None:
        """Enforce the autonomy escalation gate (ADR-0009 D-ESC-3): fail LOUD when
        the requested level exceeds what the environment authorizes, rather than
        silently clamping to a lower level the operator did not ask for.

        - L0/L1: always permitted.
        - L2 (apply-with-consensus): needs the Mode-B container
          (``CHARON_CONTAINER_VERIFIED=1``) or the loud uncontained override
          (``CHARON_ALLOW_UNCONTAINED_AUTONOMY=1``) — ADR-0002 §2.3 / INV-B4.
        - L3 (full-auto, unattended, consensus gate REMOVED): the L2 precondition
          AND its own distinct opt-in ``CHARON_ALLOW_UNATTENDED=1``. The flag that
          unlocks L2 testing does NOT silently grant L3 (D-ESC-1)."""
        decision = AutonomyPolicy.from_env(env).resolve(self.autonomy)
        if decision.clamped:
            raise FenceDenied(decision.reason)

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
