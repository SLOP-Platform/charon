"""The work-engine scheduler (ADR-0010 D2 / E2) — a COORDINATION layer.

It assigns claimed board units to warm ACP-agent workers and runs them
concurrently, honoring ``depends_on`` waves, the disjoint-``owns`` collision rule
(both already mechanized by :mod:`charon.engine.board`), a per-tier capacity cap
(:mod:`charon.engine.capacity`), and the shared aggregate budget
(:class:`charon.parallel.SharedBudget`).

It is **NOT** an executor. Workers are warm ACP agents driven by the EXISTING
``AgentBackend`` + ``coordinator.run`` loop over a ``ThreadPoolExecutor`` — the
same substrate :mod:`charon.parallel` uses. The scheduler spawns no processes and
manages no PIDs.

THE FENCE CHOKE-POINT (DTC Lens-2 R1 / DECISIONS D008): every unit is driven
through the SINGLE fenced execution unit, ``coordinator.run``
(``assert_environment`` + ``scrubbed_env`` + escape-scan + lkg/rollback). The
scheduler is **never** a second, unfenced dispatch path and **never** calls a
backend directly. The default :class:`CoordinatorRunner` wires ``coordinator.run``
exactly as :mod:`charon.api` does; the ``runner`` seam exists for test injection
and for supplying the warm-ACP ``backend_factory``, not for a parallel dispatch
path.

Concurrency discipline: worker threads run only the (fenced) runner and return a
status string; ALL board mutations + claim/release happen on the scheduler's main
thread once a future completes, so the board file is never written concurrently
and the atomic on-disk claim stays the only cross-process exclusion.

Liveness = ACP-deadline + checkpoint-kill, enforced *inside* ``coordinator.run``
(ADR-0007 D8). No process-group/zombie machinery here.

Stdlib-only core (ADR-0005 R3 / ADR-0010 D2): only stdlib + ``charon.*`` imports.
"""
from __future__ import annotations

import enum
from collections.abc import Callable, Mapping
from concurrent.futures import FIRST_COMPLETED, Future, ThreadPoolExecutor, wait
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol, runtime_checkable

from .. import coordinator, gitutil
from ..acceptance import AcceptanceCheck
from ..coordinator import CostGate, RunResult
from ..fence import Fence
from ..ledger import Ledger, LedgerCorruption
from ..ports.backend import AgentBackend
from ..router import StaticRouter
from ..types import Autonomy, Budget, WorkUnit
from .board import CLAIMED, Board, Unit
from .capacity import CapacityLimiter, select_limiter
from .claim import Claim, ClaimContended, StaleReclaim
from .claim import claim as claim_unit
from .claim import release as release_claim

# ----------------------------------------------------------------- dispositions


class Disposition(enum.Enum):
    """How a finished unit's run status maps to a board move."""

    DONE = "done"  # concluded + applied → advance the board
    RETRY = "retry"  # transient failure → release, back to ready for a future drain
    BLOCKED = "blocked"  # concluded but needs a human (propose-default / rejected)
    SUPERSEDED = "superseded"  # a reclaim fenced this run out — log-and-skip, never advance


# Transient statuses worth a retry; everything not here and not "complete" is a
# terminal conclusion that awaits a human (propose-default D3 / a rejection).
_RETRYABLE = frozenset({"error", "exhausted", "budget"})


def default_classify(status: str) -> Disposition:
    """Map a terminal ``coordinator.run`` status to a :class:`Disposition`.

    ``complete`` → DONE; ``error``/``exhausted``/``budget`` → RETRY; everything
    else (``escaped``, ``blocked``, ``blocked-consensus``) → BLOCKED — a concluded
    proposal/rejection that a human resolves (D3 propose-default), never silently
    advanced and never auto-retried.
    """
    if status == "complete":
        return Disposition.DONE
    if status in _RETRYABLE:
        return Disposition.RETRY
    return Disposition.BLOCKED


# --------------------------------------------------------------------- runner


@runtime_checkable
class FencedRunner(Protocol):
    """Drive ONE unit through the fenced ``coordinator.run`` and return its
    result. The lone execution-unit seam — a real runner reuses
    ``coordinator.run``; tests may inject a fake to assert coordination behavior
    without a live agent. It must NEVER call a backend directly."""

    def __call__(
        self, unit: Unit, worktree: str, *, cost_gate: CostGate | None
    ) -> RunResult:
        ...


BackendFactory = Callable[[Unit, "list[AcceptanceCheck]"], Mapping[str, AgentBackend]]

# A sink for human-readable lifecycle lines (WORK-OBSERVABILITY). The scheduler
# emits one short line per unit transition (claimed / started / checkpoint N /
# done|blocked|retry|superseded); the caller routes it to stderr so stdout stays
# the machine-readable final JSON. Lines carry ONLY unit ids + acceptance-check
# ids + status words — never the note, env, or any credential.
ProgressFn = Callable[[str], None]


@dataclass
class CoordinatorRunner:
    """The default :class:`FencedRunner`: build the per-unit ledger + fence +
    router and drive the unit through ``coordinator.run`` — the SAME fenced wiring
    :mod:`charon.api` uses. ``backend_factory`` yields the warm-ACP backend(s) for
    a unit (a fresh instance per unit — CONC-3); the runner kills them on the way
    out. It does not call ``backend.dispatch`` — ``coordinator.run`` does, behind
    the fence."""

    state_dir: str
    backend_factory: BackendFactory
    autonomy: str = "L0"
    max_checkpoints: int = 8

    def __call__(
        self, unit: Unit, worktree: str, *, cost_gate: CostGate | None
    ) -> RunResult:
        checks = [
            AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(unit.accept)
        ]
        sdir = Path(self.state_dir).resolve()
        base_ref = gitutil.head(Path(worktree))
        try:
            ledger = Ledger.create(
                sdir, unit.id, unit.goal, checks, str(worktree), base_ref
            )
        except LedgerCorruption:
            # The ledger already exists — this is a RETRY of the unit. Resume the
            # durable ledger (D2) instead of re-failing at creation, which made
            # Disposition.RETRY dead (every retry looped to the attempt cap).
            ledger = Ledger.load(sdir, unit.id)
        backends = self.backend_factory(unit, checks)
        router = StaticRouter(backends=list(backends))
        fence = Fence(autonomy=Autonomy[self.autonomy])
        budget = Budget(max_checkpoints=self.max_checkpoints)
        # Carry the ticket's full bearings (body + the SAME accept checks the gate
        # runs, joined) into the dispatched unit so `acp._build_prompt` emits goal +
        # body + acceptance — not the title alone. One source of truth: `accept_text`
        # is the gate's `checks`, so what the agent is shown can never diverge from
        # what is judged.
        work_unit = WorkUnit(
            task_id=unit.id,
            goal=unit.goal,
            body=unit.body,
            accept_text="\n".join(unit.accept),
        )
        try:
            return coordinator.run(
                work_unit,
                backends,
                ledger,
                fence,
                router,
                max_checkpoints=self.max_checkpoints,
                budget=budget,
                cost_gate=cost_gate,
            )
        finally:
            for b in backends.values():
                try:
                    b.kill()
                except Exception:
                    pass


# --------------------------------------------------------------------- results


@dataclass(frozen=True)
class UnitResult:
    """The outcome of one launched unit within a drain."""

    unit_id: str
    status: str  # the coordinator.run status, or "error"
    disposition: Disposition
    note: str = ""


@dataclass(frozen=True)
class DrainResult:
    """Aggregate outcome of a :meth:`Scheduler.drain`."""

    results: tuple[UnitResult, ...] = ()
    rounds: int = 0
    budget_capped: bool = False


# A unit handed to a worker thread, paired with the claim the main thread holds.
@dataclass
class _InFlight:
    unit: Unit
    claim: Claim


# Worker-thread return payload: (status, note, checkpoints, verified-check-ids).
_Outcome = tuple[str, str, int, tuple[str, ...]]


# --------------------------------------------------------------------- scheduler


class Scheduler:
    """Drain a :class:`Board` of claimable units onto warm ACP workers.

    Each launchable unit is claimed (atomic, on disk), then driven concurrently
    through the fenced ``runner`` in a bounded thread pool. On completion the main
    thread releases the claim (epoch-fenced) and advances the board per the
    :class:`Disposition`. The board's own ``claimable`` predicate enforces the
    wave order and the disjoint-``owns`` rule, so the scheduler just keeps
    launching whatever is claimable until nothing is left and nothing is running.
    """

    def __init__(
        self,
        board: Board,
        claims_dir: Path,
        runner: FencedRunner,
        *,
        worktree_factory: Callable[[Unit], str] | None = None,
        state_dir: str | None = None,
        limiter: CapacityLimiter | None = None,
        max_parallel: int = 4,
        max_cost_usd: float | None = None,
        max_tokens: int | None = None,
        max_attempts: int = 1,
        classify: Callable[[str], Disposition] = default_classify,
        progress: ProgressFn | None = None,
    ) -> None:
        if max_parallel < 1:
            raise ValueError("max_parallel must be >= 1")
        if max_attempts < 1:
            raise ValueError("max_attempts must be >= 1")
        self._progress = progress
        self.board = board
        self.claims_dir = Path(claims_dir)
        self._runner = runner
        self._state_dir = state_dir
        self._worktree_factory = worktree_factory or self._default_worktree_factory
        self.limiter = select_limiter(limiter)
        self.max_parallel = max_parallel
        self.max_cost_usd = max_cost_usd
        self.max_tokens = max_tokens
        self.max_attempts = max_attempts
        self._classify = classify
        self._attempts: dict[str, int] = {}

    # ----------------------------------------------------------------- progress
    def _emit(self, line: str) -> None:
        """Send one lifecycle line to the optional progress sink (no-op when the
        caller wired none — e.g. ``--quiet`` or redirected stdout). Emission is
        only ever from the scheduler's main thread, so lines never interleave."""
        if self._progress is not None:
            self._progress(line)

    # ------------------------------------------------------------- worktree seam
    def _default_worktree_factory(self, unit: Unit) -> str:
        """A fresh, unit-unique sandbox git worktree under ``state_dir`` (the demo
        path, mirroring ``api._prepare_repo``: ``…/sandbox/<id>/repo`` so the
        fence's ``guard_dir = worktree.parent`` is unique per unit). A real
        consumer injects a factory that cuts a linked worktree off ``--repo``."""
        if self._state_dir is None:
            raise ValueError(
                "the default worktree factory needs state_dir; pass state_dir= "
                "or a worktree_factory="
            )
        # Unique per ATTEMPT (not just per unit): a retry / stale-reclaim must land
        # on a FRESH worktree (claim.py refuses reclaim onto the in-flight one), so
        # the path must differ each attempt. ``_attempts[id]`` is the 0-based index
        # of the attempt about to start (incremented only after a successful claim).
        attempt = self._attempts.get(unit.id, 0)
        repo = (
            Path(self._state_dir).resolve()
            / "sandbox" / unit.id / f"a{attempt}" / "repo"
        )
        repo.mkdir(parents=True, exist_ok=True)
        gitutil.init_repo(repo)
        return str(repo)

    # ----------------------------------------------------------------- the drain
    def drain(self) -> DrainResult:
        """Run the board to quiescence: launch every claimable unit (respecting
        capacity + budget), then advance the board as each finishes, until nothing
        is claimable and nothing is in flight."""
        from ..parallel import SharedBudget  # local: avoid import cycle at top

        # Scope the attempt counter to THIS drain: the cap bounds re-launch within
        # one drain, but a fresh drain must be able to relaunch a unit left READY by
        # a prior drain (otherwise a once-failed unit can never be retried again).
        self._attempts = {}
        gate = SharedBudget(max_cost_usd=self.max_cost_usd, max_tokens=self.max_tokens)
        results: list[UnitResult] = []
        budget_capped = False
        rounds = 0

        with ThreadPoolExecutor(max_workers=self.max_parallel) as pool:
            in_flight: dict[Future[_Outcome], _InFlight] = {}
            while True:
                launched = self._launch_round(pool, gate, in_flight)
                if launched:
                    rounds += 1  # one launch wave (a new wave of claimable units)
                if not in_flight:
                    break  # nothing claimable and nothing running → quiescent
                done, _ = wait(in_flight, return_when=FIRST_COMPLETED)
                for fut in done:
                    info = in_flight.pop(fut)
                    res = self._settle(fut, info)
                    results.append(res)
                    if res.status == "budget":
                        budget_capped = True
        return DrainResult(
            results=tuple(results), rounds=rounds, budget_capped=budget_capped
        )

    # --------------------------------------------------------------- internals
    def _launch_round(
        self,
        pool: ThreadPoolExecutor,
        gate: CostGate,
        in_flight: dict[Future[_Outcome], _InFlight],
    ) -> int:
        """Claim + submit every unit that is claimable, under its attempt cap, and
        admitted by the capacity limiter. Skipped units are simply retried on the
        next round once a slot frees up (the limiter is non-blocking). Returns the
        number of units launched this round."""
        launched = 0
        for unit in self.board.claimable_units():
            if self._attempts.get(unit.id, 0) >= self.max_attempts:
                continue
            if not self.limiter.try_acquire(unit.tier):
                continue
            # The capacity slot is acquired; it MUST be released on every path that
            # does not hand a unit to a worker, or the slot leaks and the drain
            # eventually starves (the limiter is the only admission control).
            launched_unit = False
            try:
                claim = self._claim(unit)
            except ClaimContended:
                # A live holder beat us to it — not an attempt; retry next round.
                continue
            except Exception:
                # Any other failure to launch (worktree factory mkdir/init, a stale
                # reclaim, a board error) is counted as an attempt so a persistent
                # error cannot spin the drain, then isolated so the drain continues.
                self._attempts[unit.id] = self._attempts.get(unit.id, 0) + 1
                continue
            else:
                self._attempts[unit.id] = self._attempts.get(unit.id, 0) + 1
                fut = pool.submit(self._execute, unit, claim, gate)
                in_flight[fut] = _InFlight(unit=unit, claim=claim)
                self._emit(f"{unit.id}: started")
                launched_unit = True
                launched += 1
            finally:
                if not launched_unit:
                    self.limiter.release(unit.tier)
        return launched

    def _claim(self, unit: Unit) -> Claim:
        """Create the unit's worktree, atomically claim it, and mark the board
        ``claimed``. Done on the main thread so the board write is serial."""
        worktree = self._worktree_factory(unit)
        claim = claim_unit(self.claims_dir, unit.id, worktree)
        self.board.mark_claimed(unit.id)
        self._emit(f"{unit.id}: claimed")
        return claim

    def _execute(
        self, unit: Unit, claim: Claim, gate: CostGate
    ) -> _Outcome:
        """Worker-thread body: drive the unit through the fenced runner. Returns
        ``(status, note, checkpoints, verified)``; an exception becomes
        ``("error", …, 0, ())`` so one unit can never tear the pool down. The
        checkpoint/verified fields feed the progress line emitted on the (serial)
        main thread in :meth:`_settle` — never from here."""
        try:
            res = self._runner(unit, claim.worktree, cost_gate=gate)
            return res.status, res.note, res.checkpoints, tuple(res.verified)
        except Exception as exc:  # isolation: a unit's crash is its own result
            return "error", f"{type(exc).__name__}: {exc}", 0, ()

    def _settle(
        self, fut: Future[_Outcome], info: _InFlight
    ) -> UnitResult:
        """Main-thread completion: release the claim (epoch-fenced so a stale run
        can never land), free the capacity slot, and advance the board."""
        status, note, checkpoints, verified = fut.result()
        disposition = self._classify(status)
        # Release the claim under THIS run's epoch. Epoch-fencing guarantees a
        # stale double-runner cannot drop the fresh holder's claim (DTC Lens-4).
        superseded = False
        try:
            release_claim(self.claims_dir, info.unit.id, epoch=info.claim.epoch)
        except StaleReclaim as exc:
            # A reclaim bumped the epoch while this run was in flight: the fence has
            # detected the exact double-execution case it exists for. Log-and-skip —
            # do NOT advance the board (the fresh holder owns the unit now) and do
            # NOT let it abort settlement of the in-flight siblings in this batch.
            superseded = True
            disposition = Disposition.SUPERSEDED
            note = f"superseded (epoch {info.claim.epoch} fenced out): {exc}"
        finally:
            self.limiter.release(info.unit.tier)
        if not superseded:
            self._advance(info.unit.id, disposition)
        # Lifecycle lines (main thread, serial): the checkpoint summary then the
        # terminal disposition. Only ids + check ids + status words — no note.
        if checkpoints:
            self._emit(
                f"{info.unit.id}: checkpoint {checkpoints} "
                f"(verified {', '.join(verified) or 'none'})"
            )
        self._emit(f"{info.unit.id}: {disposition.value}")
        return UnitResult(
            unit_id=info.unit.id,
            status=status,
            disposition=disposition,
            note=note,
        )

    def _advance(self, unit_id: str, disposition: Disposition) -> None:
        """Move a ``claimed`` unit to its next board state per the disposition."""
        unit = self.board.get(unit_id)
        if unit.state != CLAIMED:  # defensive: only ever advance our own claim
            return
        if disposition is Disposition.DONE:
            self.board.mark_done(unit_id)
        elif disposition is Disposition.RETRY:
            self.board.mark_ready(unit_id)  # released for a future drain
        else:
            self.board.mark_blocked(unit_id)


__all__ = [
    "Scheduler",
    "CoordinatorRunner",
    "FencedRunner",
    "Disposition",
    "UnitResult",
    "DrainResult",
    "default_classify",
    "ProgressFn",
]
