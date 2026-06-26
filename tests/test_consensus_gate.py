"""Tier 4 — L2 consensus gate + container enforcement (REVIEW-LOG 2026-06-24).

Non-tautological: the tests assert CROSS-CUTTING properties, not that an
if-statement fires — a BLOCK leaves lkg unadvanced and nothing applied; an ERROR
fails CLOSED; L2 with no reviewer fails closed; L1 ignores the reviewer entirely;
L3 (full-auto) applies despite a block but records the verdict; and L2+ is refused
outside the Mode-B container.

T8 extension: circuit breaker integration (breaker wrapping gate; half-open
recovery) + GatewayReviewer parsing (unit-tested without a live gateway).
"""
from __future__ import annotations

from pathlib import Path

import pytest

from charon import coordinator, gitutil
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend
from charon.adapters.review import GatewayReviewer, _parse_findings
from charon.adapters.review_mock import MockReviewer, ReviewMode
from charon.failover import ReviewerCircuitBreaker
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


# ------------------------------------------------ circuit breaker integration
def test_breaker_tripped_reviewer_fails_closed(
    state_dir: Path, git_repo: Path, in_container
) -> None:
    # an already-tripped circuit breaker (threshold=0 means it opens on first call)
    # must cause the gate to fail closed, not pass
    inner = MockReviewer(ReviewMode.ERROR)
    # threshold=1: breaker opens after the first error, then subsequent calls are
    # rejected with "circuit open" — the coordinator's fail-closed path handles both
    breaker = ReviewerCircuitBreaker(inner, threshold=1, cooldown_s=999.0)
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=breaker)
    assert res.status == "blocked-consensus"
    assert led.lkg_ref == led.base_ref


def test_breaker_half_open_recovery_allows_gate(
    state_dir: Path, git_repo: Path, in_container
) -> None:
    # breaker opens, cools down (cooldown_s=0), then a passing probe closes it;
    # the *next* coordinator run then succeeds.  We simulate by tripping then
    # directly recovering via a zero-cooldown in a separate review call before
    # the coordinator run.
    inner = MockReviewer(ReviewMode.FLAKY, flaky_k=2)
    breaker = ReviewerCircuitBreaker(inner, threshold=2, cooldown_s=0.0)

    # trip the breaker (first two calls to inner error; breaker opens)
    from charon.ports.reviewer import ReviewerError
    from charon.types import Outcome, OutcomeStatus, WorkUnit
    u = WorkUnit(task_id="t1", goal="goal")
    o = Outcome(status=OutcomeStatus.PROGRESSED, provider="mock")
    for _ in range(2):
        with pytest.raises(ReviewerError):
            breaker.review(u, o)
    assert breaker.state == "open"

    # cooldown_s=0 → next call goes half-open; inner's 3rd call passes → closes
    result = breaker.review(u, o)
    assert result.passes
    assert breaker.state == "closed"

    # now a coordinator run through the (now-closed) breaker should succeed
    led, backends, router = _setup(state_dir, git_repo)
    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L2), router,
                          reviewer=breaker)
    assert res.status == "complete"
    assert led.lkg_ref != led.base_ref


# ------------------------------------------------ GatewayReviewer unit (parse)
def test_gateway_reviewer_parses_empty_blocking() -> None:
    findings = _parse_findings('{"blocking": []}')
    assert findings.passes


def test_gateway_reviewer_parses_blocking_list() -> None:
    findings = _parse_findings('{"blocking": ["issue A", "issue B"]}')
    assert not findings.passes
    assert "issue A" in findings.blocking


def test_gateway_reviewer_fails_closed_on_bad_json() -> None:
    findings = _parse_findings("not json at all")
    assert not findings.passes
    assert any("unparseable" in b for b in findings.blocking)


def test_gateway_reviewer_fails_closed_on_wrong_shape() -> None:
    findings = _parse_findings('{"blocking": "should be a list"}')
    assert not findings.passes


def test_gateway_reviewer_reads_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARON_REVIEW_BASE_URL", "http://example.invalid:9999/v1")
    monkeypatch.setenv("CHARON_REVIEW_MODEL", "my-model")
    monkeypatch.setenv("CHARON_GATEWAY_TOKEN", "tok123")
    r = GatewayReviewer()
    assert r._base_url == "http://example.invalid:9999/v1"
    assert r._model == "my-model"
    assert r._token == "tok123"


def test_gateway_reviewer_explicit_args_override_env(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("CHARON_REVIEW_BASE_URL", "http://should-be-ignored/v1")
    r = GatewayReviewer(base_url="http://override:1234/v1", model="m", token="t")
    assert r._base_url == "http://override:1234/v1"
    assert r._model == "m"
    assert r._token == "t"
