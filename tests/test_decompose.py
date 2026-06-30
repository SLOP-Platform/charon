"""PERF-4 / D5 (ADR-0006) — work-decomposition as a thin, sequential role-DAG.

Binding rules under test (REVIEW-LOG 2026-06-26):
  - WITHIN one ticket the role-DAG (Triage→Plan→Implement→Review→Validate→Close)
    runs SEQUENTIALLY — stages depend on each other (the fixed pipeline, NOT a
    general dependency scheduler). Parallelism is between units, never stages.
  - ONE Ledger per task — roles/stages are checkpoint METADATA appended to the
    single ledger (INV-1), never a ledger-per-stage and no external graph state.
"""
from __future__ import annotations

from pathlib import Path

from charon import decompose, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend, MockMode
from charon.fence import Fence
from charon.ledger import Ledger
from charon.parallel import SharedBudget
from charon.router import StaticRouter
from charon.types import Autonomy, Usage, WorkUnit


def _led(state_dir: Path, repo: Path, checks) -> Ledger:
    return Ledger.create(state_dir, "t1", "goal", checks, str(repo), gitutil.head(repo))


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="build the thing")


# ------------------------------------------------------------------ the planner

def test_role_dag_is_the_fixed_ordered_pipeline() -> None:
    assert decompose.ROLE_DAG == [
        "triage", "plan", "implement", "review", "validate", "close",
    ]


def test_decompose_emits_stages_in_dag_order_each_with_a_role() -> None:
    stages = decompose.decompose("build the thing", ["test -f out.txt"])
    assert [s.role for s in stages] == decompose.ROLE_DAG
    # every stage carries a routable task_class (role → cost-ranked tier).
    assert all(s.task_class for s in stages)
    # the dependent pipeline is linear — exactly one terminal (close).
    assert sum(1 for s in stages if s.terminal) == 1
    assert stages[-1].role == "close" and stages[-1].terminal


# --------------------------------------------------------------- the executor

def test_run_decomposed_completes_with_one_ledger_and_role_tagged_checkpoints(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(creates=["out.txt"])
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(
        _unit(), {backend.name: backend}, led, Fence(Autonomy.L1),
        StaticRouter(backends=[backend.name]),
    )
    assert res.status == "complete"
    assert (state_dir / "t1" / "ledger.json").exists()
    assert not (state_dir / "t1" / "stages").exists()
    roles = [cp.role for cp in led.checkpoints()]
    assert roles == decompose.ROLE_DAG
    assert led.lkg_ref != led.base_ref
    seqs = [(cp.seq, cp.role) for cp in led.checkpoints()]
    assert seqs == list(enumerate(decompose.ROLE_DAG, start=1))


def test_run_decomposed_escape_in_a_stage_is_rejected_and_rolled_back(
    state_dir: Path, git_repo: Path
) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(mode=MockMode.ESCAPE)
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(_unit(), {backend.name: backend}, led,
                                   Fence(Autonomy.L1), StaticRouter(backends=[backend.name]))
    assert res.status == "escaped"
    assert led.lkg_ref == led.base_ref  # not applied


def test_run_decomposed_l0_proposes_only(state_dir: Path, git_repo: Path) -> None:
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(creates=["out.txt"])
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(_unit(), {backend.name: backend}, led,
                                   Fence(Autonomy.L0), StaticRouter(backends=[backend.name]))
    assert res.status == "blocked"  # propose-only records, applies nothing
    assert led.lkg_ref == led.base_ref
    assert not (git_repo / "out.txt").exists()  # rolled back


def test_cli_run_decompose_flag_drives_the_role_dag(tmp_path: Path, capsys) -> None:
    """`charon run --decompose` drives the goal through the role-DAG end to end."""
    import json

    from charon.cli import main

    state = tmp_path / "state"
    rc = main(["run", "--goal", "make hello", "--accept", "test -f hello.txt",
               "--backend", "mock", "--autonomy", "L1", "--decompose",
               "--state-dir", str(state)])
    out = json.loads(capsys.readouterr().out)
    assert rc == 0 and out["status"] == "complete"
    # the single ledger carries role-tagged checkpoints for the whole pipeline.
    led = Ledger.load(state, out["task_id"])
    assert [cp.role for cp in led.checkpoints()] == decompose.ROLE_DAG


def test_run_decomposed_respects_shared_cost_gate(state_dir: Path, git_repo: Path) -> None:
    """A decomposed unit honours the shared budget too — so it composes under
    run_parallel. A gate already at cap halts the pipeline before any stage."""
    gate = SharedBudget(max_cost_usd=1.0)
    gate.add(1.0, 0)
    checks = [AcceptanceCheck("a0", "test -f out.txt")]
    backend = MockBackend(creates=["out.txt"], usage=Usage(cost_usd=0.5))
    led = _led(state_dir, git_repo, checks)
    res = decompose.run_decomposed(_unit(), {backend.name: backend}, led,
                                   Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                                   cost_gate=gate)
    assert res.status == "budget"
    assert led.checkpoints() == []  # halted before the first stage dispatched
