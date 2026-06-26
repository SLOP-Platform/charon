"""PERF-4 (ADR-0006, ticket T1) — parallel independent units + the race-free
shared budget.

Proven-red first (PLAN-tier4 §5): the binding properties are
  - N independent units complete concurrently (run_parallel fans out);
  - one unit's failure / escape never corrupts a sibling (per-unit isolation);
  - the SHARED budget bounds the SET — atomic check-claim-slot + add-actual under
    one lock, with the honest **bounded-overshoot** guarantee (≤ one in-flight
    checkpoint per active unit over the cap, NOT "never exceeds to the cent").
"""
from __future__ import annotations

import threading
from pathlib import Path

from charon import coordinator, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend
from charon.adapters.review_mock import MockReviewer, ReviewMode
from charon.fence import Fence
from charon.ledger import Ledger
from charon.parallel import SharedBudget, Unit, run_parallel
from charon.router import StaticRouter
from charon.types import Autonomy, Usage, WorkUnit

# --------------------------------------------------------- SharedBudget (D3/CONC-2)

def test_shared_budget_allows_until_cap_then_halts() -> None:
    b = SharedBudget(max_cost_usd=1.0)
    assert b.allow()  # nothing spent yet
    b.add(0.6, 0)
    assert b.allow()  # 0.6 < 1.0 — a new dispatch may proceed
    b.add(0.6, 0)  # now 1.2 ≥ cap (this was the one allowed in-flight checkpoint)
    assert not b.allow()  # cap reached — NEW dispatches halted


def test_shared_budget_token_cap() -> None:
    b = SharedBudget(max_tokens=100)
    assert b.allow()
    b.add(0.0, 100)
    assert not b.allow()


def test_shared_budget_uncapped_axis_never_halts() -> None:
    b = SharedBudget(max_cost_usd=None, max_tokens=None)
    b.add(9_999.0, 9_999)
    assert b.allow()  # no cap configured on either axis


def test_shared_budget_is_race_free_under_threads() -> None:
    """CONC-2: the check-claim/add path is atomic under one lock — concurrent
    adders never lose an increment (the read-modify-write race the ADR names)."""
    b = SharedBudget(max_cost_usd=None)
    n = 50

    def worker() -> None:
        for _ in range(100):
            b.add(0.01, 1)

    threads = [threading.Thread(target=worker) for _ in range(n)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()
    assert b.tokens == n * 100
    assert round(b.cost_usd, 2) == round(n * 100 * 0.01, 2)


def test_cost_gate_halts_coordinator_before_dispatch(state_dir: Path, git_repo: Path) -> None:
    """The coordinator consults the shared gate before EACH dispatch and stops at
    'budget' once the shared running total has reached the cap — even on a unit
    that has itself spent nothing yet (a sibling exhausted the shared cap)."""
    gate = SharedBudget(max_cost_usd=1.0)
    gate.add(1.0, 0)  # a sibling already reached the cap
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend.satisfying(checks)
    led = Ledger.create(state_dir, "t1", "g", checks, str(git_repo), gitutil.head(git_repo))
    res = coordinator.run(WorkUnit(task_id="t1", goal="g"), {backend.name: backend},
                          led, Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                          cost_gate=gate)
    assert res.status == "budget"
    assert "shared" in res.note.lower()
    assert led.lkg_ref == led.base_ref  # nothing applied


def test_cost_gate_accumulates_actuals_across_units(state_dir: Path, git_repo: Path) -> None:
    """add-actual after each checkpoint feeds the shared total, so a second unit
    sharing the gate sees the first unit's spend."""
    gate = SharedBudget(max_cost_usd=10.0)
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend(creates=["hello.txt"], usage=Usage(cost_usd=2.0, tokens_in=5))
    led = Ledger.create(state_dir, "t1", "g", checks, str(git_repo), gitutil.head(git_repo))
    coordinator.run(WorkUnit(task_id="t1", goal="g"), {backend.name: backend},
                    led, Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                    cost_gate=gate)
    assert gate.cost_usd == 2.0
    assert gate.tokens == 5


# ------------------------------------------------------------- run_parallel (D1/D6)

def _unit(goal: str, fname: str) -> Unit:
    return Unit(goal=goal, accept=[f"test -f {fname}"], autonomy="L1")


def test_run_parallel_completes_n_independent_units(tmp_path: Path) -> None:
    state = tmp_path / "state"
    units = [_unit(f"unit {i}", f"f{i}.txt") for i in range(5)]
    res = run_parallel(units, max_parallel=3, state_dir=str(state))
    assert len(res.units) == 5
    assert all(u["status"] == "complete" for u in res.units)
    # distinct task ids → distinct ledgers → distinct sandboxes (isolation).
    ids = {u["task_id"] for u in res.units}
    assert len(ids) == 5


def test_run_parallel_one_unit_escape_does_not_corrupt_siblings(tmp_path: Path) -> None:
    """Per-unit isolation: an ESCAPE unit is rejected on its own ledger while the
    well-behaved siblings still complete."""
    state = tmp_path / "state"
    good = [_unit(f"good {i}", f"g{i}.txt") for i in range(3)]
    bad = Unit(goal="escaper", accept=["test -f never.txt"], autonomy="L1",
               backend_mode="escape")
    res = run_parallel([*good, bad], max_parallel=4, state_dir=str(state))
    by_goal = {u["goal"]: u for u in res.units}
    assert by_goal["escaper"]["status"] == "escaped"
    for i in range(3):
        assert by_goal[f"good {i}"]["status"] == "complete"


def test_run_parallel_shared_cap_bounds_the_set(tmp_path: Path) -> None:
    """The aggregate cap bounds the whole SET with bounded overshoot — the final
    total never runs away, even across many concurrent units."""
    state = tmp_path / "state"
    # 8 units, each costing 1.0 per checkpoint over 3 checkpoints (3.0 each if
    # unbounded = 24.0). A shared 4.0 cap must stop the set far below that.
    units = [
        Unit(goal=f"u{i}", accept=[f"test -f a{i}.txt", f"test -f b{i}.txt",
                                    f"test -f c{i}.txt"],
             autonomy="L1", creates=[f"a{i}.txt", f"b{i}.txt", f"c{i}.txt"],
             unit_cost_usd=1.0)
        for i in range(8)
    ]
    res = run_parallel(units, max_parallel=8, state_dir=str(state), max_cost_usd=4.0)
    # bounded-overshoot: ≤ cap + one in-flight checkpoint per active unit. With 8
    # units at $1 each that ceiling is 4 + 8 = 12; unbounded would be 24.
    assert res.total_cost_usd <= 12.0
    assert res.total_cost_usd < 24.0
    assert res.budget_capped  # at least one unit stopped at the shared cap


def test_run_parallel_real_repo_units_never_share_a_guard_dir(tmp_path: Path) -> None:
    """D2/CONC-1 (ADR-0007): N units pointed at ONE real ``--repo`` each get their
    own per-unit ``git worktree`` off base, so their guard_dirs are distinct — no
    two real-repo units share a working tree (the gap D2 closes).

    Proven-red: before D2 a real repo was used AS-IS, so every unit's
    ``target_repo`` was the same shared repo → one shared guard_dir."""
    repo = tmp_path / "repo"
    repo.mkdir()
    gitutil.init_repo(repo)
    state = tmp_path / "state"
    units = [Unit(goal=f"u{i}", accept=[f"test -f f{i}.txt"], autonomy="L1",
                  repo=str(repo), creates=[f"f{i}.txt"]) for i in range(3)]
    res = run_parallel(units, max_parallel=3, state_dir=str(state))
    assert all(u["status"] == "complete" for u in res.units)
    targets = [Path(u["target_repo"]) for u in res.units]
    # no unit operates in the shared real repo itself …
    assert all(t != repo.resolve() for t in targets)
    # … and every unit's guard_dir (worktree.parent) is unique to that unit.
    guard_dirs = {str(t.parent) for t in targets}
    assert len(guard_dirs) == len(units)


def test_run_parallel_real_repo_one_unit_escape_does_not_corrupt_siblings(
    tmp_path: Path,
) -> None:
    """The per-unit real-repo worktree carries the isolation invariant end-to-end:
    an ESCAPE unit is rejected on its own ledger while real-repo siblings still
    complete — one unit's escape is invisible to the others."""
    repo = tmp_path / "repo"
    repo.mkdir()
    gitutil.init_repo(repo)
    state = tmp_path / "state"
    good = [Unit(goal=f"good {i}", accept=[f"test -f g{i}.txt"], autonomy="L1",
                 repo=str(repo), creates=[f"g{i}.txt"]) for i in range(3)]
    bad = Unit(goal="escaper", accept=["test -f never.txt"], autonomy="L1",
               repo=str(repo), backend_mode="escape")
    res = run_parallel([*good, bad], max_parallel=4, state_dir=str(state))
    by_goal = {u["goal"]: u for u in res.units}
    assert by_goal["escaper"]["status"] == "escaped"
    for i in range(3):
        assert by_goal[f"good {i}"]["status"] == "complete"


# ------------------------------------------------- parallel + decomposition (D6 §3)

def test_run_parallel_decomposed_units_fan_out(tmp_path: Path) -> None:
    """Each unit runs its own sequential role-DAG; run_parallel fans out ACROSS
    the units (parallelism between units, sequential within each)."""
    state = tmp_path / "state"
    units = [Unit(goal=f"ticket {i}", accept=[f"test -f t{i}.txt"], autonomy="L1",
                  decompose=True, creates=[f"t{i}.txt"]) for i in range(4)]
    res = run_parallel(units, max_parallel=4, state_dir=str(state))
    assert all(u["status"] == "complete" for u in res.units)


def test_run_parallel_decomposed_l2_consensus_gates_each_unit(
    tmp_path: Path, monkeypatch
) -> None:
    """D6 step 3: parallel + L2 — the decomposed Review stage gates each unit's
    apply, INDEPENDENTLY, with a PER-UNIT reviewer instance (globals audit: a
    stateful reviewer is never shared across units). A blocked unit fails
    consensus while its siblings still apply."""
    monkeypatch.setenv("CHARON_CONTAINER_VERIFIED", "1")  # L2 honest in-container
    state = tmp_path / "state"
    pass_reviewers = [MockReviewer(ReviewMode.PASS) for _ in range(3)]
    block_reviewer = MockReviewer(ReviewMode.BLOCK)
    passing = [Unit(goal=f"ok {i}", accept=[f"test -f ok{i}.txt"], autonomy="L2",
                    decompose=True, creates=[f"ok{i}.txt"], reviewer=pass_reviewers[i])
               for i in range(3)]
    blocked = Unit(goal="nope", accept=["test -f nope.txt"], autonomy="L2",
                   decompose=True, creates=["nope.txt"], reviewer=block_reviewer)
    res = run_parallel([*passing, blocked], max_parallel=4, state_dir=str(state))
    by_goal = {u["goal"]: u for u in res.units}
    for i in range(3):
        assert by_goal[f"ok {i}"]["status"] == "complete"
    assert by_goal["nope"]["status"] == "blocked-consensus"
    # each unit's OWN reviewer was consulted exactly once (per-unit, not shared).
    assert block_reviewer.calls == 1
    assert all(r.calls == 1 for r in pass_reviewers)
