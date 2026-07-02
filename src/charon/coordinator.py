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
from typing import Protocol, runtime_checkable

from . import gitutil
from .fence import Fence, detect_escape, snapshot_outside
from .handoff import choose_next_backend
from .ledger import Checkpoint, Ledger
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .router import StaticRouter
from .types import Autonomy, Budget, Outcome, OutcomeStatus, PrivilegedOp, WorkUnit


@runtime_checkable
class CostGate(Protocol):
    """The shared, race-free budget seam (D3/CONC-2, ADR-0006).

    The coordinator consults ``allow()`` before EACH dispatch (atomic
    check-claim-slot) and reports the dispatch's actual spend via ``add()`` after
    each costed checkpoint (atomic add-actual). Both happen under the gate's own
    lock. Honest guarantee = **bounded overshoot**: ≤ one in-flight checkpoint per
    active unit over the cap (NOT "never exceeds to the cent"). A single-unit run
    passes ``cost_gate=None``; ``parallel.SharedBudget`` is the parallel impl."""

    def allow(self) -> bool:
        """True iff a new dispatch may proceed (shared running total < cap)."""
        ...

    def add(self, cost_usd: float, tokens: int) -> None:
        """Atomically fold one checkpoint's actual spend into the shared total."""
        ...


@dataclass
class RunResult:
    status: str  # complete | exhausted | escaped | blocked | blocked-consensus | budget
    checkpoints: int
    verified: list[str] = field(default_factory=list)
    remaining: list[str] = field(default_factory=list)
    lkg_ref: str = ""
    note: str = ""
    cost_usd: float = 0.0  # cumulative spend, derived from ledger spans (Tier 3)
    tokens: int = 0


def run(
    unit: WorkUnit,
    backends: Mapping[str, AgentBackend],
    ledger: Ledger,
    fence: Fence,
    router: StaticRouter,
    *,
    reviewer: Reviewer | None = None,
    max_checkpoints: int = 8,
    budget: Budget | None = None,
    cost_gate: CostGate | None = None,
) -> RunResult:
    """Drive ``unit`` to acceptance or a bounded stop. One Ledger, one lock.

    ``budget`` (Tier 3) adds cumulative cost/token caps on top of
    ``max_checkpoints``. ``reviewer`` (Tier 4) is the consensus gate: at autonomy
    **L2** a completed unit is applied only if the reviewer passes (fail-closed);
    at L1 the reviewer is not consulted; at L3 (full-auto, unattended) it is
    consulted for the record but does not block. The escalation gate
    (``Fence.assert_environment``, ADR-0009) is enforced once up front: L2+ needs
    the Mode-B container (INV-B4) and L3 needs its own distinct unattended opt-in
    on top — a requested level over the environment's ceiling fails LOUD here, not
    silently clamped."""
    fence.assert_environment()  # escalation gate: L2+ container, L3 unattended opt-in
    worktree = Path(ledger.target_repo)
    # D2/CONC-1 (ADR-0007): guard_dir is the worktree's parent. For parallel units
    # this MUST be unique per unit or one unit's escape scan would see a sibling's
    # writes. `api._prepare_repo` guarantees this by nesting EVERY unit's worktree
    # one level down — `sandbox/<task_id>/repo` for the demo path, and a per-unit
    # `git worktree add work/<task_id>/repo` off base for a real `--repo` (so N
    # units never share one real working tree + guard_dir). The parent is therefore
    # the unit-unique `…/<task_id>/` dir in both cases.
    guard_dir = worktree.parent
    # "propose-only" = this level applies nothing even with consensus (L0 only);
    # L1+ keeps changes, and the consensus gate (L2+) decides the final advance.
    propose_only = not fence.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=True)
    # BR2-11: every backend the router may pick must be wired in, or a route
    # would KeyError mid-run. Catch it as a config error before the loop.
    missing = set(router.backends) - set(backends)
    if missing:
        raise KeyError(
            f"router may route to backends not provided: {sorted(missing)}"
        )
    exhausted: set[str] = set()
    seq = 0

    with ledger.lock():
        if ledger.is_complete():
            return _result("complete", seq, ledger)

        while seq < max_checkpoints:
            # D3/CONC-2: the SHARED budget is the cross-unit safety net. Consult
            # it before every dispatch (atomic check-claim-slot) so NEW dispatches
            # halt once the running total of the whole SET has reached the cap —
            # even a unit that has itself spent nothing (a sibling exhausted it).
            # Bounded overshoot: the dispatch we let through is the ≤1 in-flight
            # checkpoint per active unit the honest guarantee permits.
            if cost_gate is not None and not cost_gate.allow():
                return _result("budget", seq, ledger,
                               note="shared budget cap reached (set-level, bounded overshoot)")
            # Tier 3: stop before starting a dispatch once cumulative spend
            # (derived from the ledger spans) has reached a budget cap. The cap
            # binds at checkpoint boundaries — like max_checkpoints bounds count.
            if budget is not None and seq > 0:
                spent = ledger.cumulative_usage()
                if budget.max_cost_usd is not None and spent.cost_usd >= budget.max_cost_usd:
                    return _result("budget", seq, ledger,
                                   note=f"cost cap reached: ${spent.cost_usd:.4f} "
                                        f">= ${budget.max_cost_usd:.4f}")
                if budget.max_tokens is not None and spent.tokens >= budget.max_tokens:
                    return _result("budget", seq, ledger,
                                   note=f"token cap reached: {spent.tokens} "
                                        f">= {budget.max_tokens}")
            try:
                route = router.route(unit.task_class, exclude=exhausted)
            except RuntimeError as exc:
                return _result("exhausted", seq, ledger, note=str(exc))
            backend = backends[route.backend]

            # H4: exhaustion is detected via health(), not inferred from failure.
            # Re-route excluding the FULL exhausted set (BR2-4), not just this one.
            if backend.health().exhausted:
                exhausted.add(route.backend)
                try:
                    route = choose_next_backend(router, unit.task_class, exhausted)
                    backend = backends[route.backend]
                except RuntimeError as exc:
                    return _result("exhausted", seq, ledger, note=str(exc))

            before = snapshot_outside(worktree, guard_dir)
            env = Fence.scrubbed_env(worktree)
            outcome = backend.dispatch(unit, route.tier, route.budget, worktree, env,
                                       state_dir=ledger.root.parent)
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
            # A completion checkpoint = acceptance fully passes against disk now
            # (re-derived, BR2-5) and there is a commit to bless.
            is_completion = bool(not remaining and outcome.commit and not ledger.remaining())

            # Consensus gate (Tier 4): consult the reviewer ONCE, at completion,
            # at L2+ — before advancing lkg (D-GATE-1). Verdict recorded on the
            # checkpoint for audit (INV-1).
            reviewer_passed: bool | None = None
            rnote = ""
            if is_completion and fence.autonomy >= Autonomy.L2:
                reviewer_passed, rnote = _consult_reviewer(reviewer, unit, outcome)

            ledger.append_checkpoint(
                Checkpoint(seq, route.backend, outcome.commit, verified, remaining,
                           note=outcome.note, usage=outcome.usage,
                           reviewer_passed=reviewer_passed, reviewer_note=rnote)
            )
            ledger.record_provider(route.backend)
            # D3/CONC-2: add-actual after the checkpoint — fold this dispatch's
            # real spend into the shared total so sibling units see it on their
            # next allow() check. Under the gate's own lock (race-free).
            if cost_gate is not None and outcome.usage is not None:
                cost_gate.add(outcome.usage.cost_usd, outcome.usage.tokens)

            if propose_only:
                # L0 propose-only: discard the worktree changes.
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                return _result("blocked", seq, ledger,
                               note="L0 propose-only: proposal recorded, not applied")

            # L1+: keep changes; advance lkg only when fully verified (INV-2) AND
            # the consensus gate passes (Tier 4). The reviewer verdict is supplied
            # as the fence's consensus signal — but it is an AUTOMATED reviewer,
            # not human approval, and not a security boundary (D-GATE-3/6).
            if is_completion and outcome.commit is not None:
                consensus_signal = reviewer_passed if reviewer_passed is not None else True
                if fence.authorize(PrivilegedOp.APPLY_REVERSIBLE, consensus=consensus_signal):
                    ledger.advance_lkg(outcome.commit)
                    # L3 disclosure (ADR-0009): full-auto applies with no consensus
                    # gate — record that on the result so the audit trail is honest.
                    note = rnote
                    if fence.autonomy >= Autonomy.L3:
                        note = (note + "; " if note else "") + \
                            "L3 unattended: applied full-auto without consensus"
                    return _result("complete", seq, ledger, note=note)
                # L2 fail-closed: reviewer blocked / errored / absent. Do not apply.
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                return _result("blocked-consensus", seq, ledger,
                               note=rnote or "apply-with-consensus: reviewer did not pass")

            if outcome.status is OutcomeStatus.EXHAUSTED:
                exhausted.add(route.backend)
            elif outcome.status is OutcomeStatus.BLOCKED:
                return _result("blocked", seq, ledger, note=outcome.note)

        return _result("budget", seq, ledger, note="max_checkpoints reached")


def _consult_reviewer(
    reviewer: Reviewer | None, unit: WorkUnit, outcome: Outcome
) -> tuple[bool, str]:
    """Tier-4 consensus consult, FAIL-CLOSED (D-GATE-4): an absent reviewer, a
    blocking finding, or ANY error all yield 'not passed', so unreviewed work is
    never applied at L2.

    Honest scope (D-GATE-5): there is no stateful cross-run circuit breaker — a
    reviewer error fails this run closed and does not retry; persisting trip state
    across CLI runs is out of scope (it would live in the ledger). And the
    reviewer is an automated check that can be wrong or gamed — NOT a security
    boundary (D-GATE-6)."""
    if reviewer is None:
        return False, "apply-with-consensus requires a reviewer; none configured (fail-closed)"
    try:
        findings = reviewer.review(unit, outcome)
    except Exception as exc:  # timeout / unavailable / crash ⇒ fail closed
        return False, f"reviewer error (fail-closed): {exc}"
    if findings.passes:
        return True, "reviewer passed"
    return False, f"reviewer blocked: {findings.blocking}"


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
