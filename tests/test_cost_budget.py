"""Tier 3 — Ledger-native cost & budget accounting (re-scoped, REVIEW-LOG
2026-06-24). Proves the accounting CONTRACT against deterministic mock usage:

- per-dispatch usage spans are recorded and summed (cumulative cost is derived
  truth, INV-1 extended to cost);
- a cumulative cost/token cap stops the run (bounded — never unbounded spend);
- cumulative cost re-derives identically after a reload and survives a
  cross-vendor handoff (H3-for-cost — spend does not reset per vendor);
- a backend reporting no usage costs nothing and trips no cap (backward compat).

Live token/cost come from real ACP `session/usage` (gated on `charon doctor`);
the mock proves the accounting, not the numbers.
"""
from __future__ import annotations

from pathlib import Path

from charon import coordinator, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend
from charon.fence import Fence
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, Budget, Usage, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _checks(n: int) -> list[AcceptanceCheck]:
    return [AcceptanceCheck(f"a{i}", f"test -f f{i}.txt") for i in range(n)]


def _ledger(state_dir: Path, repo: Path, checks) -> Ledger:
    return Ledger.create(state_dir, "t1", "goal", checks, str(repo),
                         gitutil.head(repo))


def test_usage_spans_recorded_and_summed(state_dir: Path, git_repo: Path) -> None:
    checks = _checks(2)
    backend = MockBackend(creates=["f0.txt", "f1.txt"],
                          usage=Usage(tokens_in=10, tokens_out=5, cost_usd=0.5))
    led = _ledger(state_dir, git_repo, checks)
    res = coordinator.run(_unit(), {backend.name: backend}, led,
                          Fence(Autonomy.L1), StaticRouter(backends=[backend.name]))
    assert res.status == "complete"
    # 2 dispatches × (cost 0.5, 15 tokens) summed from the spans.
    spent = led.cumulative_usage()
    assert spent.cost_usd == 1.0
    assert spent.tokens == 30
    assert res.cost_usd == 1.0 and res.tokens == 30
    # every checkpoint carries its span.
    assert all(cp.usage is not None for cp in led.checkpoints())


def test_cost_cap_stops_the_run_bounded(state_dir: Path, git_repo: Path) -> None:
    checks = _checks(4)  # would take 4 checkpoints to complete
    backend = MockBackend(creates=[f"f{i}.txt" for i in range(4)],
                          usage=Usage(cost_usd=1.0))
    led = _ledger(state_dir, git_repo, checks)
    budget = Budget(max_checkpoints=8, max_cost_usd=2.5)
    res = coordinator.run(_unit(), {backend.name: backend}, led,
                          Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                          budget=budget)
    assert res.status == "budget"
    assert "cost cap" in res.note
    # stopped after crossing the cap — bounded, not unbounded; not complete.
    assert "a3" in res.remaining
    assert led.cumulative_usage().cost_usd <= 4.0  # bounded overshoot


def test_token_cap_stops_the_run(state_dir: Path, git_repo: Path) -> None:
    checks = _checks(4)
    backend = MockBackend(creates=[f"f{i}.txt" for i in range(4)],
                          usage=Usage(tokens_in=100, tokens_out=0))
    led = _ledger(state_dir, git_repo, checks)
    budget = Budget(max_tokens=250)
    res = coordinator.run(_unit(), {backend.name: backend}, led,
                          Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                          budget=budget)
    assert res.status == "budget"
    assert "token cap" in res.note


def test_no_usage_costs_nothing_and_trips_no_cap(state_dir: Path, git_repo: Path) -> None:
    # Backward compat: a backend reporting no usage (the Tier-1/2 default) has
    # zero cumulative cost and a cost cap never triggers.
    checks = _checks(1)
    backend = MockBackend.satisfying(checks)  # no usage configured
    led = _ledger(state_dir, git_repo, checks)
    res = coordinator.run(_unit(), {backend.name: backend}, led,
                          Fence(Autonomy.L1), StaticRouter(backends=[backend.name]),
                          budget=Budget(max_cost_usd=0.01))
    assert res.status == "complete"
    assert led.cumulative_usage().cost_usd == 0.0


def test_h3_cost_survives_handoff_and_reload(state_dir: Path, git_repo: Path) -> None:
    # H3-for-cost: cumulative spend is derived from the ledger, so it does not
    # reset across a vendor handoff and is identical after a reload.
    checks = _checks(2)
    mock_a = MockBackend(name="mock-a", creates=["f0.txt"], exhaust_after=1,
                         usage=Usage(cost_usd=1.0, tokens_in=10))
    mock_b = MockBackend(name="mock-b", creates=["f1.txt"],
                         usage=Usage(cost_usd=2.0, tokens_in=20))
    led = _ledger(state_dir, git_repo, checks)
    res = coordinator.run(_unit(), {"mock-a": mock_a, "mock-b": mock_b}, led,
                          Fence(Autonomy.L1),
                          StaticRouter(backends=["mock-a", "mock-b"]))
    assert res.status == "complete"
    assert led.provider_history == ["mock-a", "mock-b"]
    # A's 1.0 + B's 2.0 = 3.0, summed across the vendor boundary.
    assert led.cumulative_usage().cost_usd == 3.0
    # A fresh reader ("vendor B" reopening) derives the same total.
    reloaded = Ledger.load(state_dir, "t1")
    assert reloaded.cumulative_usage().cost_usd == 3.0
    assert reloaded.cumulative_usage().tokens == 30
