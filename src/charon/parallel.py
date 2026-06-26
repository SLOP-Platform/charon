"""PERF-4 (ADR-0006, ticket T1) — run N *independent* units concurrently.

`run_parallel` is an orchestrator that sits ABOVE the existing single-unit
`coordinator.run` loop (D1). It does NOT add a new isolation primitive: each unit
keeps its own Ledger + worktree + lock + lkg machinery (INV-1), reused verbatim —
we make the existing atom safe to instantiate N times. Threads (not processes):
the loop is I/O-bound (subprocess + HTTP), and the real isolation boundary is the
per-unit worktree + the Mode-B container, not the OS process (D1, REVIEW-LOG LOW).

**Parallelism is BETWEEN units, never between stages of one unit** (binding rule,
REVIEW-LOG 2026-06-26). The role-DAG WITHIN a ticket runs sequentially — see
`decompose.py`.

Pre-code globals audit carried for T1 (ADR-0006 risk register + REVIEW-LOG MED):
  - **no `os.chdir`** anywhere in the loop — cwd is always passed explicitly to
    git (`gitutil._run(cwd=…)`) and to `backend.dispatch(worktree, …)`; safe to
    run N loops in N threads.
  - **L2 reviewer is per-unit** — `Unit.reviewer` holds a fresh reviewer instance
    per unit; a stateful reviewer (e.g. `MockReviewer.calls`) is never shared.
  - **per-unit backend** (CONC-3) — `Unit.backend_factory` builds a fresh backend
    per unit; a long-lived ACP subprocess is never shared (sticky cwd/env/model).
  - **read-only module globals only** — `GIT_CONFIG_GLOBAL=/dev/null` (scrubbed
    env) and the router's default policy are read-only / copied, safe to share.

Isolation carried (CONC-1..4):
  - CONC-1: per-unit nested guard_dir (`api._prepare_repo` nests `…/<id>/repo`).
  - CONC-2: the shared `SharedBudget` is an atomic check-claim-slot + add-actual
    counter under one lock — the race-free aggregate cap (bounded overshoot).
  - CONC-3: per-unit backend instance (above).
  - CONC-4: per-unit unique task_id → unique Ledger + lock; the lock gains a
    PID-liveness check (`ledger.py`) so a crashed unit's stale lock is reclaimed
    by liveness, not silently by TTL.
"""
from __future__ import annotations

import re
import threading
from collections.abc import Callable
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field

from . import api
from .acceptance import AcceptanceCheck
from .adapters.mock import MockBackend, MockMode
from .ports.backend import AgentBackend
from .ports.reviewer import Reviewer
from .types import Usage

_TEST_FILE_RE = re.compile(r"test\s+-[ef]\s+(\S+)")


class SharedBudget:
    """The race-free aggregate cost/token cap shared across concurrent units
    (D3/CONC-2). A naive cumulative `Budget` read across threads is a
    read-modify-write race (two units both pass the cap check, then both spend →
    overspend). This fixes it with one lock guarding both the check and the add.

    Honest guarantee = **bounded overshoot**: at most ONE in-flight checkpoint per
    active unit over the cap. Each unit calls `allow()` before each dispatch (it
    returns False once the running total has reached the cap, halting NEW
    dispatches) and `add()` after each costed checkpoint. The dispatches already
    in flight when the cap is crossed still complete — so the final total can
    exceed the cap by ≤ one checkpoint per active unit, never to the cent, and
    never unbounded. The `--max-cost-usd` help states this.
    """

    def __init__(self, max_cost_usd: float | None = None,
                 max_tokens: int | None = None) -> None:
        self.max_cost_usd = max_cost_usd
        self.max_tokens = max_tokens
        self._lock = threading.Lock()
        self._cost = 0.0
        self._tokens = 0

    def allow(self) -> bool:
        """True iff a NEW dispatch may proceed — the running total is still under
        every configured cap. False halts new dispatches (set-level)."""
        with self._lock:
            if self.max_cost_usd is not None and self._cost >= self.max_cost_usd:
                return False
            if self.max_tokens is not None and self._tokens >= self.max_tokens:
                return False
            return True

    def add(self, cost_usd: float, tokens: int) -> None:
        """Atomically fold one checkpoint's actual spend into the shared total."""
        with self._lock:
            self._cost += cost_usd
            self._tokens += tokens

    @property
    def cost_usd(self) -> float:
        with self._lock:
            return self._cost

    @property
    def tokens(self) -> int:
        with self._lock:
            return self._tokens


@dataclass
class Unit:
    """One independent unit of work for `run_parallel`. Each becomes its own
    Ledger + worktree + lock (the isolation atom is unchanged — D1).

    The mock knobs (``backend_mode`` / ``creates`` / ``unit_cost_usd``) drive the
    deterministic demo + test path; a real consumer (a droid fleet) supplies a
    ``backend_factory`` instead — a fresh backend per unit (CONC-3)."""

    goal: str
    accept: list[str]
    repo: str | None = None
    autonomy: str = "L0"
    max_checkpoints: int = 8
    # Per-unit sub-cap (D3 supports per-unit caps too); the SHARED cap on
    # `run_parallel` is the cross-unit safety net.
    max_cost_usd: float | None = None
    # Per-unit reviewer INSTANCE for L2 (globals audit: never shared across units).
    reviewer: Reviewer | None = None
    # Backend selection: an explicit per-unit factory (production), else the mock
    # knobs below build the deterministic demo backend.
    backend_factory: Callable[[Unit, list[AcceptanceCheck]], AgentBackend] | None = None
    backend_mode: str | None = None  # "escape" | "blocked" | None (well-behaved)
    creates: list[str] | None = None
    unit_cost_usd: float | None = None


@dataclass
class ParallelResult:
    """Aggregate outcome of a `run_parallel` fan-out."""

    units: list[dict] = field(default_factory=list)  # per-unit run_task outputs
    total_cost_usd: float = 0.0
    total_tokens: int = 0
    budget_capped: bool = False  # ≥1 unit stopped at the shared cap


def _infer_creates(checks: list[AcceptanceCheck]) -> list[str]:
    creates: list[str] = []
    for c in checks:
        creates.extend(_TEST_FILE_RE.findall(c.cmd))
    return creates


def _default_backend(unit: Unit, checks: list[AcceptanceCheck]) -> AgentBackend:
    """Build a fresh, deterministic mock backend for one unit (CONC-3: never
    shared). Honors the unit's adversarial/cost knobs so the parallel invariants
    are proven, not asserted against a well-behaved mock only."""
    if unit.backend_mode == "escape":
        return MockBackend(mode=MockMode.ESCAPE)
    if unit.backend_mode == "blocked":
        return MockBackend(mode=MockMode.BLOCKED)
    usage = Usage(cost_usd=unit.unit_cost_usd) if unit.unit_cost_usd else None
    creates = unit.creates if unit.creates is not None else (_infer_creates(checks) or None)
    if usage is not None or unit.creates is not None:
        return MockBackend(creates=creates, usage=usage)
    return MockBackend.satisfying(checks)


def _run_one(unit: Unit, gate: SharedBudget, state_dir: str) -> dict:
    """Drive ONE unit through the existing single-unit loop, wired to the shared
    budget. Exceptions are captured as an error result so one unit can never tear
    down the pool (per-unit isolation)."""
    checks = [AcceptanceCheck(id=f"a{i}", cmd=c) for i, c in enumerate(unit.accept)]
    factory = unit.backend_factory or _default_backend
    backend = factory(unit, checks)
    try:
        out = api.run_task(
            goal=unit.goal,
            accept=unit.accept,
            repo=unit.repo,
            state_dir=state_dir,
            backend=backend,
            reviewer=unit.reviewer,
            autonomy=unit.autonomy,
            max_checkpoints=unit.max_checkpoints,
            max_cost_usd=unit.max_cost_usd,
            cost_gate=gate,
        )
        out["goal"] = unit.goal  # so the consumer can map results back to units
        return out
    except Exception as exc:  # one unit's failure never corrupts a sibling
        return {"status": "error", "goal": unit.goal,
                "note": f"{type(exc).__name__}: {exc}"}


def run_parallel(
    units: list[Unit],
    max_parallel: int = 4,
    *,
    state_dir: str = api.DEFAULT_STATE_DIR,
    max_cost_usd: float | None = None,
    max_tokens: int | None = None,
) -> ParallelResult:
    """Run ``units`` concurrently in a bounded thread pool, each through its own
    single-unit `coordinator.run` loop (D1). The shared ``SharedBudget`` is the
    race-free aggregate cap over the whole SET (D3/CONC-2, bounded overshoot).

    Each unit is fully isolated: unique task_id → unique Ledger + worktree + lock
    (CONC-4) and a per-unit nested guard_dir (CONC-1). A unit that escapes or
    raises is rejected on its OWN ledger and never corrupts a sibling.

    NOTE (binding): this fans out INDEPENDENT units only — there is no inter-unit
    data dependency here. Dependent stages of one ticket serialize inside
    `decompose.py`'s role-DAG; parallelism is between units, never between stages.
    """
    if not units:
        return ParallelResult()
    gate = SharedBudget(max_cost_usd=max_cost_usd, max_tokens=max_tokens)
    workers = max(1, min(max_parallel, len(units)))
    results: list[dict] = []
    with ThreadPoolExecutor(max_workers=workers) as pool:
        futures = [pool.submit(_run_one, u, gate, state_dir) for u in units]
        for fut in as_completed(futures):
            results.append(fut.result())
    capped = any(
        r.get("status") == "budget" and "shared" in str(r.get("note", "")).lower()
        for r in results
    )
    return ParallelResult(
        units=results,
        total_cost_usd=gate.cost_usd,
        total_tokens=gate.tokens,
        budget_capped=capped,
    )
