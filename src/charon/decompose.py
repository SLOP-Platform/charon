"""Work-decomposition as a thin, native role-DAG (ADR-0006 D5 / ADR-0004 D6/D8).

One ticket → a fixed, ORDERED pipeline of role stages
(Triage→Plan→Implement→Review→Validate→Close). The stages are *dependent* — each
builds on the last — so they run **strictly sequentially within the ticket**.
This is NOT a general dependency scheduler (out of scope, PLAN-tier4 §3); it is
the one fixed pipeline. **Parallelism is between independent units (run_parallel),
never between the stages of one unit** (binding rule, REVIEW-LOG 2026-06-26).

Binding constraints carried (ADR-0004 R4/D6, ADR-0006 D5):
  - ONE Ledger per task — stages are checkpoint METADATA (each checkpoint carries
    its ``role``) appended to the single ledger, never a ledger-per-stage and no
    external graph checkpointer (INV-1). The Ledger IS the checkpointer.
  - Native, zero new deps (no LangGraph/LangSmith — egress + a competing
    checkpointer). Reuses the existing fence/escape-scan/ledger/gitutil atoms.
  - The L2 reviewer gate generalizes to D6's "interrupt before commit": consulted
    at the **Review** stage, fail-closed, before lkg advances.

It produces the *independent* units that ``parallel.run_parallel`` fans out; true
dependencies serialize as the stages here.
"""
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, replace
from pathlib import Path

from . import gitutil
from .coordinator import CostGate, RunResult, _consult_reviewer
from .fence import Fence, detect_escape, snapshot_outside
from .ledger import Checkpoint, Ledger
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .router import StaticRouter
from .types import Autonomy, PrivilegedOp, WorkUnit

# The fixed Triage→…→Close pipeline (ADR-0004 D8). Order IS the dependency graph.
ROLE_DAG = ["triage", "plan", "implement", "review", "validate", "close"]

# Each role routes through its cost-ranked tier via the router's task-class policy
# (diagnosis/review/test-authoring/codegen map to high/high/med/med by default).
_ROLE_TASK_CLASS = {
    "triage": "diagnosis",
    "plan": "diagnosis",
    "implement": "codegen",
    "review": "review",
    "validate": "test-authoring",
    "close": "codegen",
}


@dataclass(frozen=True)
class Stage:
    """One dependent step of the role-DAG — a dispatch unit WITH a role. Stages
    are not isolation atoms: they share the ticket's one Ledger + worktree."""

    role: str
    task_class: str
    instruction: str
    terminal: bool = False


def decompose(goal: str, accept: list[str]) -> list[Stage]:
    """Turn one ticket into the fixed, ordered role pipeline. The structure is
    deterministic (the DAG is fixed); a live Triage stage may later refine the
    work, but the *shape* is the pipeline — that is what keeps this thin."""
    accept_note = f" (acceptance: {', '.join(accept)})" if accept else ""
    stages: list[Stage] = []
    for role in ROLE_DAG:
        stages.append(Stage(
            role=role,
            task_class=_ROLE_TASK_CLASS[role],
            instruction=f"[{role}] {goal}{accept_note}",
            terminal=(role == ROLE_DAG[-1]),
        ))
    return stages


def run_decomposed(
    unit: WorkUnit,
    backends: Mapping[str, AgentBackend],
    ledger: Ledger,
    fence: Fence,
    router: StaticRouter,
    *,
    reviewer: Reviewer | None = None,
    cost_gate: CostGate | None = None,
) -> RunResult:
    """Drive ``unit`` through the role-DAG sequentially against ONE ledger. Each
    stage dispatches once, is escape-scanned, and appends a role-tagged checkpoint
    to the single ledger. After the pipeline, acceptance is evaluated against disk
    and the result is applied per autonomy (L0 proposes only; L1 applies; L2
    applies only if the Review-stage reviewer passed, fail-closed).

    Honours the shared ``cost_gate`` (D3/CONC-2) so a decomposed unit composes
    under ``run_parallel`` — bounded overshoot, halting NEW stage dispatches once
    the set-level total reaches the cap."""
    fence.assert_environment()  # L2+ refused outside the container (INV-B4)
    worktree = Path(ledger.target_repo)
    guard_dir = worktree.parent  # per-unit (CONC-1); see coordinator.run
    propose_only = not fence.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=True)
    missing = set(router.backends) - set(backends)
    if missing:
        raise KeyError(f"router may route to backends not provided: {sorted(missing)}")

    stages = decompose(unit.goal, [c.cmd for c in ledger.acceptance])
    seq = 0
    reviewer_passed: bool | None = None
    rnote = ""

    with ledger.lock():
        if ledger.is_complete():
            return _result("complete", seq, ledger)

        for stage in stages:
            # D3/CONC-2: consult the shared gate before each stage dispatch.
            if cost_gate is not None and not cost_gate.allow():
                return _result("budget", seq, ledger,
                               note="shared budget cap reached (set-level, bounded overshoot)")

            su = replace(unit, task_class=stage.task_class, role=stage.role)
            route = router.route(stage.task_class)
            backend = backends[route.backend]

            before = snapshot_outside(worktree, guard_dir)
            env = Fence.scrubbed_env(worktree)
            outcome = backend.dispatch(su, route.tier, route.budget, worktree, env)
            seq += 1

            escaped = detect_escape(worktree, guard_dir, before)
            if escaped:
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                ledger.append_checkpoint(
                    Checkpoint(seq, route.backend, None, [], _ids(ledger),
                               note=f"REJECTED: escape {escaped}", role=stage.role)
                )
                return _result("escaped", seq, ledger, note=f"escape: {escaped}")

            verified = sorted(ledger.verified())
            remaining = sorted(ledger.remaining())

            # D5: the Review stage is D6's "interrupt before commit". At L2+, once
            # the implement work is done (nothing remaining), consult the reviewer
            # and record the verdict on the Review checkpoint (audit, INV-1).
            cp_passed: bool | None = None
            if stage.role == "review" and not remaining and fence.autonomy >= Autonomy.L2:
                reviewer_passed, rnote = _consult_reviewer(reviewer, su, outcome)
                cp_passed = reviewer_passed

            ledger.append_checkpoint(
                Checkpoint(seq, route.backend, outcome.commit, verified, remaining,
                           note=outcome.note, usage=outcome.usage, role=stage.role,
                           reviewer_passed=cp_passed,
                           reviewer_note=rnote if cp_passed is not None else "")
            )
            ledger.record_provider(route.backend)
            if cost_gate is not None and outcome.usage is not None:
                cost_gate.add(outcome.usage.cost_usd, outcome.usage.tokens)

        # Pipeline finished — evaluate acceptance once, then apply per autonomy.
        remaining = sorted(ledger.remaining())
        if propose_only:
            gitutil.reset_hard(worktree, ledger.lkg_ref)
            return _result("blocked", seq, ledger,
                           note="L0 propose-only: role-DAG recorded, not applied")
        if remaining:
            return _result("blocked", seq, ledger,
                           note=f"role-DAG completed but acceptance unmet: {remaining}")

        head = gitutil.head(worktree)
        if fence.autonomy >= Autonomy.L2:
            consensus_signal = reviewer_passed if reviewer_passed is not None else False
            if fence.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=consensus_signal):
                ledger.advance_lkg(head)
                return _result("complete", seq, ledger, note=rnote)
            gitutil.reset_hard(worktree, ledger.lkg_ref)
            return _result("blocked-consensus", seq, ledger,
                           note=rnote or "apply-with-consensus: reviewer did not pass")
        # L1: apply reversibly.
        ledger.advance_lkg(head)
        return _result("complete", seq, ledger)


def _ids(ledger: Ledger) -> list[str]:
    return [c.id for c in ledger.acceptance]


def _result(status: str, seq: int, ledger: Ledger, note: str = "") -> RunResult:
    spent = ledger.cumulative_usage()
    return RunResult(
        status=status,
        checkpoints=seq,
        verified=sorted(ledger.verified()),
        remaining=sorted(ledger.remaining()),
        lkg_ref=ledger.lkg_ref,
        note=note,
        cost_usd=spent.cost_usd,
        tokens=spent.tokens,
    )
