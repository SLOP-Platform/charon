"""Tier 2a — cross-vendor handoff, proven against two MOCK vendors.

These are the re-shaped, non-tautological proofs the adversarial review demanded
(REVIEW-LOG 2026-06-24, OOB2-2 / OOB2-8 / BR2-4):

- the handoff loop excludes the FULL exhausted set, never re-picks a dead backend;
- progress truth lives in the ledger+disk, so a LYING backend's claim does not
  survive a vendor switch (the real H3 content, not two well-behaved mocks
  agreeing);
- a killed coordinator rehydrates without replaying committed work (H5);
- exhaustion (H4) routes to a *different* vendor, which finishes from the ledger.

Live ACP-to-ACP handoff still needs two real agents (not in this env); that is
gated behind `charon doctor`. What is proven here is the vendor-agnostic
contract, honestly.
"""
from __future__ import annotations

from pathlib import Path

from charon import coordinator, gitutil, handoff
from charon.acceptance import AcceptanceCheck
from charon.adapters.mock import MockBackend, MockMode
from charon.fence import Fence
from charon.ledger import Ledger
from charon.router import StaticRouter
from charon.types import Autonomy, WorkUnit


def _unit() -> WorkUnit:
    return WorkUnit(task_id="t1", goal="goal")


def _two_file_checks() -> list[AcceptanceCheck]:
    return [
        AcceptanceCheck("a0", "test -f file1.txt"),
        AcceptanceCheck("a1", "test -f file2.txt"),
    ]


# --------------------------------------------------------------- BR2-4 fix
def test_exclude_accumulation_never_repicks_exhausted() -> None:
    """3 backends, 2 already exhausted → the router returns the third and never
    a repeat. Pre-fix, choose_next_backend excluded only the latest one."""
    router = StaticRouter(backends=["alpha", "beta", "gamma"])
    route = handoff.choose_next_backend(router, "codegen", exclude={"alpha", "beta"})
    assert route.backend == "gamma"


def test_all_excluded_raises_clean() -> None:
    router = StaticRouter(backends=["alpha", "beta"])
    try:
        handoff.choose_next_backend(router, "codegen", exclude={"alpha", "beta"})
    except RuntimeError as exc:
        assert "no backend" in str(exc).lower()
    else:  # pragma: no cover
        raise AssertionError("expected RuntimeError when every backend excluded")


# ------------------------------------------------------------ H4 + completion
def test_crossvendor_handoff_completes_and_records_both(
    state_dir: Path, git_repo: Path
) -> None:
    """Vendor A makes partial progress then exhausts (H4); the loop re-routes to
    vendor B (H6), which finishes. provider_history shows both, in order."""
    checks = _two_file_checks()
    # A: creates file1 on its one dispatch, then self-reports exhausted.
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    # B: a different vendor; creates the remaining file.
    mock_b = MockBackend(name="mock-b", creates=["file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    assert res.status == "complete"
    assert res.remaining == []
    assert led.provider_history == ["mock-a", "mock-b"]  # H4/H6: handed off
    assert (git_repo / "file1.txt").exists()
    assert (git_repo / "file2.txt").exists()
    assert led.lkg_ref != led.base_ref  # advanced only at full verification (INV-2)


def test_h5_no_progress_replay_across_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """H5: vendor B does only the remaining delta — it never re-creates the file
    vendor A already committed. We prove it by making B's create list disjoint
    and checking A's file is the SAME content A wrote (not overwritten)."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    mock_b = MockBackend(name="mock-b", creates=["file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    # A's committed artifact survives the handoff and still carries A's mark.
    assert (git_repo / "file1.txt").read_text() == "created by mock-a\n"
    assert (git_repo / "file2.txt").read_text() == "created by mock-b\n"
    # And B was dispatched exactly once (the remaining delta), not re-doing A.
    assert mock_b._dispatches == 1


def test_h3_rehydration_is_provider_independent_after_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """H3: after A's checkpoint, `remaining` derived from the ledger+disk is the
    same set no matter which backend (or a fresh reload) computes it — because
    acceptance is executable (INV-6), not a vendor's opinion."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", creates=["file1.txt"], exhaust_after=1)
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a}  # only A; it exhausts with no target -> stops
    router = StaticRouter(backends=["mock-a"])
    coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router)

    # file1 done, file2 not. Any reader derives {a1}.
    from_a = handoff.rehydrate_remaining(led)
    reloaded = Ledger.load(state_dir, "t1")  # "vendor B" opening the ledger fresh
    from_b = handoff.rehydrate_remaining(reloaded)
    assert from_a == from_b == {"a1"}


# --------------------------------------------------- OOB2-8 adversarial handoff
def test_lying_vendor_claim_does_not_survive_handoff(
    state_dir: Path, git_repo: Path
) -> None:
    """A LIES (claims PROGRESSED + a commit, satisfies nothing) then exhausts.
    The ledger derives progress from disk, so the lie is invisible to vendor B:
    B rehydrates and still sees everything remaining, and must actually do it.
    The forged claim never advances lkg past an unverified commit (INV-2)."""
    checks = _two_file_checks()
    mock_a = MockBackend(name="mock-a", mode=MockMode.LIE, exhaust_after=1)
    mock_b = MockBackend(name="mock-b", creates=["file1.txt", "file2.txt"])
    led = Ledger.create(state_dir, "t1", "goal", checks, str(git_repo),
                        gitutil.head(git_repo))
    backends = {"mock-a": mock_a, "mock-b": mock_b}
    router = StaticRouter(backends=["mock-a", "mock-b"])

    res = coordinator.run(_unit(), backends, led, Fence(Autonomy.L1), router,
                         max_checkpoints=8)

    # A's checkpoint recorded NOTHING verified despite its bogus success claim.
    a_checkpoint = led.checkpoints()[0]
    assert a_checkpoint.provider == "mock-a"
    assert a_checkpoint.verified == []  # the lie did not register as progress
    assert sorted(a_checkpoint.remaining) == ["a0", "a1"]
    # The run still completes — but only because B did the real work.
    assert res.status == "complete"
    assert led.provider_history[0] == "mock-a"
    assert "mock-b" in led.provider_history
