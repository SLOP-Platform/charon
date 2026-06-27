"""Atomic-claim tests (ADR-0010 D2 / DTC Lens-4): never two holders under
contention, epoch increments on reclaim, stale reclaim targets a FRESH worktree,
and epoch-fenced release."""
from __future__ import annotations

import threading
from pathlib import Path

import pytest

from charon.engine.claim import (
    Claim,
    ClaimContended,
    StaleReclaim,
    claim,
    current,
    is_held,
    release,
)
from charon.ledger import _LOCK_TTL_SECONDS


def test_claim_then_contended(tmp_path: Path) -> None:
    rec = claim(tmp_path, "u1", tmp_path / "wt-a")
    assert isinstance(rec, Claim) and rec.epoch == 1
    assert is_held(tmp_path, "u1") is True
    # a second claim while the first is live (same pid) is refused
    with pytest.raises(ClaimContended):
        claim(tmp_path, "u1", tmp_path / "wt-b")


def test_release_then_reclaim_is_monotonic(tmp_path: Path) -> None:
    rec = claim(tmp_path, "u1", tmp_path / "wt-a")
    assert rec.epoch == 1
    assert release(tmp_path, "u1", epoch=1) is True
    assert current(tmp_path, "u1") is None
    # epoch persists across release -> next claim is strictly greater
    rec2 = claim(tmp_path, "u1", tmp_path / "wt-a")
    assert rec2.epoch == 2


def test_release_idempotent_when_absent(tmp_path: Path) -> None:
    assert release(tmp_path, "u1", epoch=1) is False


# --------------------------------------------------------------- contention
def test_never_two_holders_under_contention(tmp_path: Path) -> None:
    holders: list[Claim] = []
    errors: list[Exception] = []
    barrier = threading.Barrier(16)

    def worker(i: int) -> None:
        barrier.wait()
        try:
            holders.append(claim(tmp_path, "hot", tmp_path / f"wt-{i}"))
        except ClaimContended as exc:
            errors.append(exc)

    threads = [threading.Thread(target=worker, args=(i,)) for i in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert len(holders) == 1            # exactly one winner
    assert len(errors) == 15            # everyone else refused
    assert holders[0].epoch == 1


# ----------------------------------------------------- stale reclaim / fencing
def test_stale_reclaim_requires_fresh_worktree(tmp_path: Path) -> None:
    t0 = 1_000_000.0
    claim(tmp_path, "u1", tmp_path / "wt-a", now=t0)
    stale_now = t0 + _LOCK_TTL_SECONDS + 1  # age the claim past the TTL

    # reclaiming onto the SAME (in-flight) worktree is refused
    with pytest.raises(StaleReclaim):
        claim(tmp_path, "u1", tmp_path / "wt-a", now=stale_now)

    # reclaiming onto a FRESH worktree succeeds and bumps the epoch
    rec = claim(tmp_path, "u1", tmp_path / "wt-b", now=stale_now)
    assert rec.epoch == 2
    assert rec.worktree.endswith("wt-b")


def test_release_is_epoch_fenced(tmp_path: Path) -> None:
    t0 = 2_000_000.0
    first = claim(tmp_path, "u1", tmp_path / "wt-a", now=t0)
    assert first.epoch == 1
    stale_now = t0 + _LOCK_TTL_SECONDS + 1
    second = claim(tmp_path, "u1", tmp_path / "wt-b", now=stale_now)
    assert second.epoch == 2

    # the stale holder (epoch 1) cannot release the fresh claim (epoch 2)
    with pytest.raises(StaleReclaim):
        release(tmp_path, "u1", epoch=1)
    assert current(tmp_path, "u1") is not None  # fresh claim survives
    # the fresh holder releases with its own token
    assert release(tmp_path, "u1", epoch=2) is True


def test_live_claim_not_reclaimable_even_with_fresh_worktree(tmp_path: Path) -> None:
    # within the TTL and pid alive -> contended, not reclaimable, regardless of wt
    claim(tmp_path, "u1", tmp_path / "wt-a")
    with pytest.raises(ClaimContended):
        claim(tmp_path, "u1", tmp_path / "wt-fresh")


def test_in_flight_unreadable_claim_not_stolen(tmp_path: Path) -> None:
    # an empty (mid-write) claim file within the TTL must not be stolen
    (tmp_path / "u1.claim").write_text("")
    with pytest.raises(ClaimContended):
        claim(tmp_path, "u1", tmp_path / "wt-a")
