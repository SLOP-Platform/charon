"""Coordinator — loop authority (ADR-0001 §2, the only-new-code glue).

dispatch a unit → observe the checkpoint → evaluate executable acceptance →
decide continue / handoff / stop. Stays off the hot path (PERF-1): the backend
edits the worktree directly; the coordinator observes checkpoints, not tokens.

Autonomy semantics (reconciliation BR-2):
- L0 (propose-only, the Tier-1 default): the agent works in the worktree, we
  evaluate the proposal, record it, then **roll the worktree back to lkg** —
  nothing is applied.
- L1+ (apply-reversible): worktree changes are kept; ``lkg_ref`` advances only
  when ALL acceptance passes (INV-2). On a detected escape, the run is rejected
  and rolled back — never applied.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path

from . import gitutil
from .fence import Fence, detect_escape, snapshot_outside
from .handoff import choose_next_backend
from .ledger import Checkpoint, Ledger
from .ports.backend import AgentBackend
from .router import StaticRouter
from .types import Autonomy, OutcomeStatus, PrivilegedOp, WorkUnit


@dataclass
class RunResult:
    status: str  # complete | exhausted | escaped | blocked | budget
    checkpoints: int
    verified: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    lkg_ref: str = ""
    note: str = ""


def run(
    unit: WorkUnit,
    backends: Mapping[str, AgentBackend],
    ledger: Ledger,
    fence: Fence,
    router: StaticRouter,
    *,
    max_checkpoints: int = 8,
) -> RunResult:
    """Drive ``unit`` to acceptance or a bounded stop. One Ledger, one lock."""
    worktree = Path(ledger.target_repo)
    guard_dir = worktree.parent
    apply_allowed = fence.authorize(
        PrivilegedOp.APPLY_REVERSIBLE, consensus=fence.autonomy >= Autonomy.L3
    )
    exhausted: set[str] = set()
    seq = 0

    with ledger.lock():
        if ledger.is_complete():
            return _result("complete", seq, ledger)

        while seq < max_checkpoints:
            try:
                route = router.route(unit.task_class, exclude=exhausted)
            except RuntimeError as exc:
                return _result("exhausted", seq, ledger, note=str(exc))
            backend = backends[route.backend]

            # H4: exhaustion is detected via health(), not inferred from failure.
            if backend.health().exhausted:
                exhausted.add(route.backend)
                try:
                    route = choose_next_backend(router, unit.task_class, route.backend)
                    backend = backends[route.backend]
                except RuntimeError as exc:
                    return _result("exhausted", seq, ledger, note=str(exc))

            before = snapshot_outside(worktree, guard_dir)
            env = Fence.scrubbed_env(worktree)
            outcome = backend.dispatch(unit, route.tier, route.budget, worktree, env)
            seq += 1

            # Fence escape scan: any write outside the worktree ⇒ reject + roll back.
            escaped = detect_escape(worktree, guard_dir, before)
            if escaped:
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                ledger.append_checkpoint(
                    Checkpoint(seq, route.backend, None, [], _ids(ledger),
                               note=f"REJECTED: escape {escaped}")
                )
                return _result("escaped", seq, ledger, note=f"escape: {escaped}")

            # Evaluate the proposal against disk BEFORE any rollback.
            verified = sorted(ledger.verified())
            remaining = sorted(ledger.remaining())
            ledger.append_checkpoint(
                Checkpoint(seq, route.backend, outcome.commit, verified, remaining,
                           note=outcome.note)
            )
            ledger.record_provider(route.backend)

            if not apply_allowed:
                # L0 propose-only: discard the worktree changes.
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                return _result("blocked", seq, ledger,
                               note="L0 propose-only: proposal recorded, not applied")

            # L1+: keep changes; advance lkg only when fully verified (INV-2).
            if not remaining and outcome.commit:
                ledger.advance_lkg(outcome.commit)
                return _result("complete", seq, ledger)

            if outcome.status is OutcomeStatus.EXHAUSTED:
                exhausted.add(route.backend)
            elif outcome.status is OutcomeStatus.BLOCKED:
                return _result("blocked", seq, ledger, note=outcome.note)

        return _result("budget", seq, ledger, note="max_checkpoints reached")


def _ids(ledger: Ledger) -> list[str]:
    return [c.id for c in ledger.acceptance]


def _result(status: str, seq: int, ledger: Ledger, note: str = "") -> RunResult:
    return RunResult(
        status=status,
        checkpoints=seq,
        verified=sorted(ledger.verified()),
        remaining=sorted(ledger.remaining()),
        lkg_ref=ledger.lkg_ref,
        note=note,
    )
