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

from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from pathlib import Path
from typing import TYPE_CHECKING

from . import api, gitutil
from .coordinator import CostGate, RunResult, _consult_reviewer
from .fence import Fence, detect_escape, snapshot_outside
from .ledger import Checkpoint, Ledger
from .parallel import ParallelResult, Unit, run_parallel
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .router import StaticRouter
from .types import Autonomy, PrivilegedOp, WorkUnit
from .validate import validate as _run_validate

if TYPE_CHECKING:  # type-only — no runtime import cycle (intake imports decompose)
    from .intake import Plan, PlanUnit

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
            outcome = backend.dispatch(su, route.tier, route.budget, worktree, env,
                                       state_dir=ledger.root.parent)
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

            # D12: quality gate at the Validate stage. After the backend exercises
            # the product, run executable acceptance. On fail: hold + propose fix.
            _validate_fix = ""
            _cp_note = rnote
            if stage.role == "validate":
                _vr = _run_validate(ledger.acceptance, str(worktree))
                cp_passed = _vr.passed
                _validate_fix = _vr.fix_proposal
                _cp_note = _vr.note

            ledger.append_checkpoint(
                Checkpoint(seq, route.backend, outcome.commit, verified, remaining,
                           note=outcome.note, usage=outcome.usage, role=stage.role,
                           reviewer_passed=cp_passed,
                           reviewer_note=_cp_note if cp_passed is not None else "")
            )
            ledger.record_provider(route.backend)
            if cost_gate is not None and outcome.usage is not None:
                cost_gate.add(outcome.usage.cost_usd, outcome.usage.tokens)

            if stage.role == "validate" and cp_passed is False:
                gitutil.reset_hard(worktree, ledger.lkg_ref)
                return _result("validate-failed", seq, ledger,
                               note=f"validate-failed: {_validate_fix}")

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


# ===================================================================== Phase 2
# ADR-0008 Phase 2 / ADR-0013 — autonomous decompose→run. The decomposition
# itself stays mechanical (intake.analyze); what is new here is the **confidence
# gate** that decides whether a plan may run WITHOUT a per-plan human review, and
# the **wave runner** that drives a runnable plan through the parallel engine
# under a shared budget. Honesty (ADR-0007 D10-C): we never claim the splitter is
# smart — we only auto-run a plan the failure contract already proved disjoint,
# acceptance-checked, and bounded; anything else falls back to the Phase-1 human
# gate (ADR-0013 D2). Input is DATA, never instructions (D3); nothing in this file
# interprets input text — it consumes the already-analysed Plan.

# Bounded unit count (ADR-0008 #5 scope-explosion / ADR-0013 D5). A plan with more
# units than this is treated as too-vague-to-trust and falls back to the human.
DEFAULT_MAX_UNITS = 24


@dataclass(frozen=True)
class Confidence:
    """Verdict of the autonomous-run gate (ADR-0013 D2). ``runnable`` is the only
    field callers act on; ``score``/``reasons`` are for the audit + plain-language
    surfacing to the human on fallback."""

    runnable: bool
    score: float
    reasons: list[str] = field(default_factory=list)


def assess_plan(plan: Plan, *, max_units: int = DEFAULT_MAX_UNITS) -> Confidence:
    """Decide whether ``plan`` may run autonomously (ADR-0013 D2). Conservative by
    construction: runnable ONLY if the failure contract left nothing unproven —
    the plan is ready, carries no propose-only review item, no flagged (un-proven)
    unit, and is within the unit cap. Any failing condition → not runnable → the
    caller falls back to the Phase-1 human gate (never runs blind)."""
    reasons: list[str] = []
    if not plan.ready:
        reasons.append(
            "plan is not ready (missing product acceptance, no runnable unit, or a "
            "blocking need-more-detail issue) — human gate"
        )
    if plan.review_items:
        reasons.append(
            f"{len(plan.review_items)} unit(s) have no executable acceptance "
            "(propose-only) — cannot auto-land, human gate"
        )
    n = len(plan.units)
    if n > max_units:
        reasons.append(
            f"too many units ({n} > cap {max_units}) — possible scope explosion, "
            "human gate"
        )
    flagged = [u for u in plan.units if u.flags]
    if flagged:
        reasons.append(
            f"{len(flagged)} unit(s) flagged (inferred scope / unprovable "
            "independence) — low confidence, human gate"
        )
    runnable = not reasons
    score = 1.0 if runnable else round(max(0.0, 1.0 - 0.25 * len(reasons)), 2)
    return Confidence(runnable=runnable, score=score, reasons=reasons)


# A wave runner has run_parallel's shape; injectable so the gate/wave logic is
# testable without spinning real backends (the default IS run_parallel).
WaveRunner = Callable[..., ParallelResult]


@dataclass
class AutonomousRunResult:
    """Aggregate outcome of an autonomous wave-by-wave run (ADR-0013 D4/D5)."""

    ran: bool
    units: list[dict] = field(default_factory=list)  # per-unit engine outputs
    waves_run: int = 0
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    budget_capped: bool = False
    note: str = ""


def _to_unit(
    pu: PlanUnit, *, repo: str | None, autonomy: str, max_cost_usd: float | None,
    decompose_units: bool,
) -> Unit:
    """Map one analysed ``PlanUnit`` to a parallel-engine ``Unit``. Acceptance and
    goal are carried verbatim (input-as-data); ownership/wave already shaped the
    plan, so the engine only needs the runnable fields."""
    return Unit(
        goal=pu.goal,
        accept=list(pu.accept),
        repo=repo,
        autonomy=autonomy,
        max_cost_usd=max_cost_usd,
        decompose=decompose_units,
    )


def run_plan(
    plan: Plan,
    *,
    runner: WaveRunner | None = None,
    max_parallel: int = 4,
    state_dir: str = api.DEFAULT_STATE_DIR,
    max_cost_usd: float | None = None,
    max_tokens: int | None = None,
    repo: str | None = None,
    autonomy: str = "L0",
    per_unit_max_cost_usd: float | None = None,
    decompose_units: bool = False,
) -> AutonomousRunResult:
    """Run a runnable ``plan`` through the engine **wave by wave** (ADR-0013 D4).
    ADR-0008 #1 guarantees units sharing a path are serialized into different
    waves, so every wave is a set of file-disjoint independent units — exactly
    what ``run_parallel`` requires. Later waves run only after earlier ones,
    honouring inferred dependencies (#2).

    The cumulative cost/token budget threads across waves (ADR-0013 D5): each wave
    is given the REMAINING budget and the run halts at the first wave that
    exhausts it (``SharedBudget`` bounded-overshoot). Callers MUST gate with
    ``assess_plan`` first — this assumes a runnable plan."""
    run = runner or run_parallel

    by_wave: dict[int, list[PlanUnit]] = defaultdict(list)
    for u in plan.units:
        by_wave[u.wave].append(u)

    out = AutonomousRunResult(ran=True)
    for wave in sorted(by_wave):
        if max_cost_usd is not None:
            remaining_cost = max_cost_usd - out.total_cost_usd
            if remaining_cost <= 0:
                out.budget_capped = True
                out.note = f"shared budget exhausted before wave {wave}"
                break
        else:
            remaining_cost = None
        if max_tokens is not None:
            remaining_tokens = max_tokens - out.total_tokens
            if remaining_tokens <= 0:
                out.budget_capped = True
                out.note = f"shared token budget exhausted before wave {wave}"
                break
        else:
            remaining_tokens = None

        wave_units = [
            _to_unit(u, repo=repo, autonomy=autonomy,
                     max_cost_usd=per_unit_max_cost_usd,
                     decompose_units=decompose_units)
            for u in by_wave[wave]
        ]
        res = run(
            wave_units,
            max_parallel,
            state_dir=state_dir,
            max_cost_usd=remaining_cost,
            max_tokens=remaining_tokens,
        )
        out.units.extend(res.units)
        out.total_cost_usd += res.total_cost_usd
        out.total_tokens += res.total_tokens
        out.waves_run += 1
        if res.budget_capped:
            out.budget_capped = True
            out.note = f"shared budget cap reached at wave {wave}"
            break
    return out


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
