"""Tier 4 — L2 consensus gate + container enforcement (REVIEW-LOG 2026-06-24).

Non-tautological: the tests assert CROSS-CUTTING properties, not that an
if-statement fires — a BLOCK leaves lkg unadvanced and nothing applied; an ERROR
fails CLOSED; L2 with no reviewer fails closed; L1 ignores the reviewer entirely;
L3 (full-auto) applies despite a block but records the verdict; and L2+ is refused
outside the Mode-B container.
"""
from __future__ import annotations

from pathlib import Path

import pytest

from charon import coordinator, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend
from charon.adapters.review_mock import MockReviewer, ReviewMode
from charon.fence import Fence, FenceDenied
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _setup(state_dir: Path, repo: Path):
    checks = [AcceptanceCheck("a0", "test -f hello.txt")]
    backend = MockBackend.satisfying(checks)
    led = Ledger.create(state_dir, "t1", "goal", checks, str(repo), gitutil.head(repo))
    return led, {backend.name: backend}, StaticRouter(backends=[backend.name])


@pytest.fixture
def in_container(monkeypatch):
    """Simulate running inside the Mode-B container so L2+ is permitted."""
    monkeypatch.setenv("CHARON_CONTAINER_VERIFIED", "1")


# --------------------------------------------------------- container enforcement
def test_l2_refused_outside_container(state_dir: Path, git_repo: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHARON_CONTAINER_VERIFIED", raising=False)
    monkeypatch.delenv("CHARON_ALLOW_UNCONTAINED_AUTONOMY", raising=False)
    led, backends, router = _setup(state_dir, git_repo)
    with pytest.raises(FenceDenied):
        coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                        reviewer=MockReviewer(ReviewMode.PASS))


def test_uncontained_override_allows_l2(state_dir: Path, git_repo: Path, monkeypatch) -> None:
    monkeypatch.delenv("CHARON_CONTAINER_VERIFIED", raising=False)
    monkeypatch.setenv("CHARON_ALLOW_UNCONTAINED_AUTONOMY", "1")
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=MockReviewer(ReviewMode.PASS))
    assert res.status == "complete"  # explicit opt-out works (loudly)


# ---------------------------------------------------------------- the L2 gate
def test_l2_reviewer_pass_applies(state_dir: Path, git_repo: Path, in_container) -> None:
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=MockReviewer(ReviewMode.PASS))
    assert res.status == "complete"
    assert led.lkg_ref != led.base_ref  # applied
    # the verdict is recorded on the completion checkpoint (INV-1 audit)
    last = led.checkpoints()[-1]
    assert last.reviewer_passed is True


def test_l2_reviewer_block_not_applied(state_dir: Path, git_repo: Path, in_container) -> None:
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=MockReviewer(ReviewMode.BLOCK))
    assert res.status == "blocked-consensus"
    assert led.lkg_ref == led.base_ref  # NOT applied — lkg never advanced
    assert led.checkpoints()[-1].reviewer_passed is False


def test_l2_reviewer_error_fails_closed(state_dir: Path, git_repo: Path, in_container) -> None:
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=MockReviewer(ReviewMode.ERROR))
    assert res.status == "blocked-consensus"  # error ⇒ fail CLOSED, not applied
    assert led.lkg_ref == led.base_ref
    assert "fail-closed" in res.note


def test_l2_no_reviewer_fails_closed(state_dir: Path, git_repo: Path, in_container) -> None:
    # apply-with-consensus but no reviewer configured ⇒ cannot establish consensus.
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=None)
    assert res.status == "blocked-consensus"
    assert led.lkg_ref == led.base_ref


def test_l2_flaky_reviewer_fails_closed(state_dir: Path, git_repo: Path, in_container) -> None:
    # FLAKY errors on the first call; the gate is consulted once per run and does
    # NOT retry (honest scope, D-GATE-5) ⇒ this run fails closed.
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=MockReviewer(ReviewMode.FLAKY, flaky_k=1))
    assert res.status == "blocked-consensus"


# ----------------------------------------------------- L1 unaffected, L3 full-auto
def test_l1_ignores_reviewer(state_dir: Path, git_repo: Path) -> None:
    # L1 does not require the container and does not consult the reviewer at all:
    # a BLOCK reviewer is irrelevant, the unit still applies (backward compat).
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router,
                          reviewer=MockReviewer(ReviewMode.BLOCK))
    assert res.status == "complete"
    assert led.lkg_ref != led.base_ref
    assert led.checkpoints()[-1].reviewer_passed is None  # never consulted


def test_l3_full_auto_applies_despite_block(state_dir: Path, git_repo: Path, in_container) -> None:
    # L3 = full-auto within the fence: it applies regardless of the reviewer, but
    # records the blocking verdict for audit (honest).
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L3), router,
                          reviewer=MockReviewer(ReviewMode.BLOCK))
    assert res.status == "complete"
    assert led.lkg_ref != led.base_ref  # applied (full-auto)
    assert led.checkpoints()[-1].reviewer_passed is False  # but the block is recorded
