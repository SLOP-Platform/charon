"""Tests for DECOMPOSE-SIZING-OPTIMIZER (decompose_sizing) — pick N* and a
balanced surface->chunk assignment for a decomposition, replacing the
decomposer's hardcoded "2-4 sub-tickets" guidance with a real wall-clock
(makespan) cost model.

Each fixture below breaks a DISTINCT load-bearing rule from the design doc
(DECOMPOSE-SIZING-DESIGN.md ยง5): balanced assignment, the capacity ceiling,
the atomic floor, and dependency-chain serialization. Each carries a
FAIL-ON-REVERT companion that monkeypatches the exact mechanism away and
shows the assertion flips — proving the guarantee comes from the real
computation, not a hardcode or a coincidence of the test numbers.

Overhead is fixed at (2, 2, 1) = 5 total throughout, matching the operator's
worked example in the design doc.
"""
from __future__ import annotations

import json
import subprocess
import sys

import pytest

from charon import decompose_sizing as ds
from charon.decompose_sizing import (
    Overhead,
    atomic_surfaces,
    makespan,
    plan_to_dict,
    size_decomposition,
)
from charon.intake import PlanUnit, assert_disjoint_waves

OVERHEAD = Overhead(2.0, 2.0, 1.0)  # total 5, matches the operator's example


def _components(effort_map: dict[str, float], deps: dict[str, list[str]] | None = None) -> dict:
    deps = deps or {}
    return {
        "components": [
            {"id": sid, "files": [f"{sid}.py"], "effort": eff, "depends_on": deps.get(sid, [])}
            for sid, eff in effort_map.items()
        ]
    }


# --------------------------------------------------------------- operator example

def test_operators_worked_example_n_star_4_wallclock_15():
    """40 total effort, 4 equal atomic surfaces of 10, overhead=5, W=4:
    N*=4, wallclock=15 — NOT the 2-chunk "very-large" split (25), and N=5 is
    refused (capacity + would require splitting an atomic unit)."""
    surface = _components({f"s{i}": 10.0 for i in range(4)})
    plan = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert plan.n_star == 4
    assert plan.wallclock_parallel == pytest.approx(15.0)
    assert plan.wallclock_serial == pytest.approx(45.0)
    assert plan.stop_reason == "atomic-floor"
    assert plan.atomic_floor_hit is True
    # The 2-chunk "very-large" split is a real candidate along the way but is
    # NOT the answer — 4 moderate chunks beats 2 very-large chunks.
    assert plan.wallclock_parallel < 25.0
    # N* can never exceed the number of atomic surfaces (here 4) regardless
    # of how much capacity is offered.
    generous = size_decomposition(
        surface, review_capacity=10, provider_concurrency=10, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert generous.n_star == 4


# ------------------------------------------------------------- (a) balancing

def test_a_balances_one_huge_and_three_tiny_not_lopsided():
    surface = _components({"huge": 30.0, "tiny1": 3.0, "tiny2": 3.0, "tiny3": 3.0})
    plan = size_decomposition(
        surface, review_capacity=2, provider_concurrency=2, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    # The three tiny surfaces are coalesced together, leaving huge alone —
    # this IS the balanced answer (huge cannot be split; grouping the tinies
    # elsewhere is the only way to minimize the max chunk).
    assert plan.chunk_efforts == pytest.approx({"c1": 30.0, "c2": 9.0}, abs=1e-6) or \
        plan.chunk_efforts == pytest.approx({"c1": 9.0, "c2": 30.0}, abs=1e-6)
    assert max(plan.chunk_efforts.values()) == pytest.approx(30.0)


def test_a_fail_on_revert_naive_packing_produces_a_lopsided_split(monkeypatch):
    """FAIL-ON-REVERT: swap the real LPT/exact balancing for a naive
    round-robin-in-input-order packer (as if someone reverted the balancing
    to "just fill chunks in order") and disable the exact fallback. The SAME
    1-huge+3-tiny input now produces a WORSE (lopsided) max chunk effort —
    proving the balance comes from LPT, not luck."""
    surface = _components({"huge": 30.0, "tiny1": 3.0, "tiny2": 3.0, "tiny3": 3.0})
    real = size_decomposition(
        surface, review_capacity=2, provider_concurrency=2, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    real_max = max(real.chunk_efforts.values())

    def _naive_assign(surfaces, n):
        chunk_ids = [f"c{i + 1}" for i in range(n)]
        assignment = {c: [] for c in chunk_ids}
        for i, s in enumerate(surfaces):
            assignment[chunk_ids[i % n]].append(s.id)
        return assignment

    monkeypatch.setattr(ds, "lpt_assign", _naive_assign)
    monkeypatch.setattr(ds, "exact_assign", lambda surfaces, n: None)

    reverted = size_decomposition(
        surface, review_capacity=2, provider_concurrency=2, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    reverted_max = max(reverted.chunk_efforts.values())
    assert reverted_max > real_max
    assert reverted_max != pytest.approx(30.0)  # no longer the clean atomic-floor balance


# --------------------------------------------------------- (b) capacity ceiling

def test_b_over_split_past_capacity_is_rejected():
    """8 equal surfaces "want" N=8, but W=4: n_star must never exceed W."""
    surface = _components({f"s{i}": 5.0 for i in range(8)})
    plan = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert plan.n_star <= 4
    assert plan.n_star == 4
    assert plan.stop_reason == "capacity"


def test_b_fail_on_revert_removing_the_capacity_clamp_over_splits(monkeypatch):
    """FAIL-ON-REVERT: bypass the parallel-width clamp (as if ``W`` were
    never computed from review/provider capacity) and the optimizer happily
    recommends splitting into all 8 surfaces — past the real capacity of 4."""
    surface = _components({f"s{i}": 5.0 for i in range(8)})
    real = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert real.n_star == 4

    monkeypatch.setattr(ds, "_parallel_width", lambda rc, pc, n: n)
    reverted = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert reverted.n_star > 4


def test_b_diminishing_returns_stops_before_capacity_is_reached():
    """20 equal tiny surfaces, epsilon=0.05, but capacity capped at 13: the
    marginal wall-clock gain per extra chunk falls below epsilon before the
    loop exhausts its capacity budget — a genuinely DIFFERENT stop reason
    from plain capacity exhaustion (n_star ends up < W)."""
    surface = _components({f"s{i}": 5.0 for i in range(20)})
    plan = size_decomposition(
        surface, review_capacity=13, provider_concurrency=13, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert plan.stop_reason == "diminishing-returns"
    assert plan.n_star < 13
    assert plan.atomic_floor_hit is False


# ------------------------------------------------------------ (c) atomic floor

def test_c_single_huge_atomic_surface_cannot_split_below_itself():
    surface = _components({"monolith": 50.0})
    plan = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert plan.n_star == 1
    assert plan.atomic_floor_hit is True
    assert plan.stop_reason == "atomic-floor"
    assert plan.wallclock_parallel == pytest.approx(plan.wallclock_serial)
    assert "atomic surface" in plan.rationale


def test_c_fail_on_revert_disabling_the_atomic_floor_guard_misreports_the_ceiling(monkeypatch):
    """FAIL-ON-REVERT: the atomic-floor detector is what turns a trivial
    single-surface ticket into an honest "cannot split below this" report.
    Stub it out (as if the guard were reverted to always-False) and the same
    monolithic ticket silently loses its atomic-floor flag and stop reason —
    proving the ceiling is detected, not assumed."""
    surface = _components({"monolith": 50.0})
    real = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert real.atomic_floor_hit is True
    assert real.stop_reason == "atomic-floor"

    monkeypatch.setattr(ds, "_atomic_floor_hit", lambda *a, **k: False)
    reverted = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert reverted.atomic_floor_hit is False
    assert reverted.stop_reason != "atomic-floor"


# --------------------------------------------------------- (d) dependency chain

def test_d_dependency_chain_serializes_regardless_of_capacity():
    """A -> B -> C, each effort 10, ample capacity (W could fit all 3 at
    once): the chain must be fully serialized, so wall-clock is the SUM of
    the (single, unsplit) chunk's duration, not shortened by extra chunks."""
    surface = _components(
        {"a": 10.0, "b": 10.0, "c": 10.0},
        deps={"b": ["a"], "c": ["b"]},
    )
    plan = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    # Splitting the chain into more chunks only pays overhead more times for
    # zero parallel benefit, so the optimizer must stay at N=1.
    assert plan.n_star == 1
    assert plan.wallclock_parallel == pytest.approx(plan.wallclock_serial)
    assert plan.wallclock_parallel == pytest.approx(OVERHEAD.total + 30.0)


def test_d_makespan_primitive_serializes_a_dependency_chain_even_with_spare_workers():
    """Direct test of the scheduling primitive: 3 equal-duration chunks in a
    strict A->B->C chain, given 3 free workers (no capacity constraint at
    all), must still take the SUM of durations (critical path), not the max
    (which would imply false parallelism)."""
    durations = {"a": 15.0, "b": 15.0, "c": 15.0}
    deps = {"a": [], "b": ["a"], "c": ["b"]}
    wc = makespan(durations, deps, workers=3)
    assert wc == pytest.approx(45.0)
    assert wc != pytest.approx(15.0)  # would be the (wrong) all-parallel answer


def test_d_fail_on_revert_dropping_dependency_lifting_underestimates_wallclock(monkeypatch):
    """FAIL-ON-REVERT: stub the chunk-DAG lifting to always report "no
    dependencies" (as if the surface->chunk dependency lift were dropped).
    The SAME 3-chunk dependency chain now looks fully parallel, the
    optimizer wrongly "discovers" a big win from splitting, and the reported
    wall-clock silently UNDERESTIMATES the true (serial) time."""
    surface = _components(
        {"a": 10.0, "b": 10.0, "c": 10.0},
        deps={"b": ["a"], "c": ["b"]},
    )
    real = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert real.n_star == 1
    assert real.wallclock_parallel == pytest.approx(35.0)

    monkeypatch.setattr(
        ds, "_lift_chunk_dag", lambda assignment, by_id: {c: [] for c in assignment}
    )
    reverted = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    assert reverted.n_star > 1
    assert reverted.wallclock_parallel < real.wallclock_parallel


# --------------------------------------------------------------- (e) determinism

def test_e_determinism_same_input_yields_the_same_plan():
    surface = _components({"huge": 30.0, "tiny1": 3.0, "tiny2": 3.0, "tiny3": 3.0})
    p1 = size_decomposition(surface, review_capacity=3, provider_concurrency=3,
                             exec_rate=1.0, epsilon=0.05, overhead=OVERHEAD)
    p2 = size_decomposition(surface, review_capacity=3, provider_concurrency=3,
                             exec_rate=1.0, epsilon=0.05, overhead=OVERHEAD)
    assert p1 == p2
    assert plan_to_dict(p1) == plan_to_dict(p2)


# ------------------------------------------------------- (f) disjoint-owns gate

def test_f_induced_owns_sets_satisfy_assert_disjoint_waves():
    """The chunking this module proposes must be acceptable to the REAL,
    unchanged ADR-0008 disjointness authority — this module is not a new
    collision authority, just a sizing recommendation over surfaces that are
    file-disjoint by construction."""
    surface = _components(
        {"a": 10.0, "b": 10.0, "c": 10.0, "d": 10.0},
        deps={"c": ["a"]},
    )
    plan = size_decomposition(
        surface, review_capacity=4, provider_concurrency=4, exec_rate=1.0,
        epsilon=0.05, overhead=OVERHEAD,
    )
    surfaces = atomic_surfaces(surface)
    by_id = {s.id: s for s in surfaces}
    surface_to_chunk = {sid: c for c, ids in plan.assignment.items() for sid in ids}

    units = []
    for chunk_id, surface_ids in plan.assignment.items():
        owns = sorted({f for sid in surface_ids for f in by_id[sid].files})
        depends_on = sorted(
            {
                surface_to_chunk[dep]
                for sid in surface_ids
                for dep in by_id[sid].depends_on
                if surface_to_chunk.get(dep) not in (None, chunk_id)
            }
        )
        units.append(
            PlanUnit(id=chunk_id, goal="sized sub-ticket", accept=["placeholder"],
                      owned_paths=owns, depends_on=depends_on)
        )

    assert_disjoint_waves(units)  # must not raise


# --------------------------------------------------------------------- edge cases

def test_empty_surface_yields_trivial_zero_plan():
    plan = size_decomposition({"files": []}, review_capacity=4, provider_concurrency=4)
    assert plan.n_star == 0
    assert plan.assignment == {}


def test_raw_graph_shape_derives_atomic_surfaces_via_union_find():
    """Without ``independence_groups`` or ``components``, atomic surfaces
    come from a local union-find over call_edges/blast_radius (files coupled
    by an edge land in the SAME atomic surface; unrelated files don't)."""
    surface = {
        "files": ["a.py", "b.py", "c.py"],
        "call_edges": [["a.py", "b.py"]],
        "blast_radius": {},
    }
    surfaces = atomic_surfaces(surface)
    groups = sorted(sorted(s.files) for s in surfaces)
    assert ["a.py", "b.py"] in groups
    assert ["c.py"] in groups


def test_independence_groups_are_used_directly_when_present():
    surface = {
        "files": ["a.py", "b.py"],
        "independence_groups": [["a.py"], ["b.py"]],
    }
    surfaces = atomic_surfaces(surface)
    assert sorted(s.files for s in surfaces) == [("a.py",), ("b.py",)]


# --------------------------------------------------------------------- CLI

def test_cli_json_output_matches_the_documented_contract(tmp_path):
    facts = _components({f"s{i}": 10.0 for i in range(4)})
    facts_path = tmp_path / "facts.json"
    facts_path.write_text(json.dumps(facts))

    result = subprocess.run(
        [sys.executable, "-m", "charon.decompose_sizing", "--surface", str(facts_path),
         "--review-capacity", "4", "--provider-concurrency", "4",
         "--exec-rate", "1.0", "--epsilon", "0.05", "--json"],
        capture_output=True, text=True, check=True,
        cwd=str(tmp_path.parent), env=_subprocess_env(),
    )
    payload = json.loads(result.stdout)
    assert payload["n_star"] == 4
    assert payload["est_wallclock"] == pytest.approx(15.0)
    assert payload["serial_wallclock"] == pytest.approx(45.0)
    assert "rationale" in payload
    assert "assignment" in payload


def _subprocess_env():
    import os
    import pathlib

    env = dict(os.environ)
    repo_src = str(pathlib.Path(__file__).resolve().parents[1] / "src")
    env["PYTHONPATH"] = repo_src + os.pathsep + env.get("PYTHONPATH", "")
    return env
