"""Board substrate tests (ADR-0010 D2): schema round-trip, state transitions,
depends_on gating, and the disjoint-``owns`` collision rule."""
from __future__ import annotations

from pathlib import Path

import pytest

import charon.engine.board as B
from charon.engine.board import BLOCKED, CLAIMED, DONE, READY, Board, BoardError, Unit
from charon.ledger import LedgerCorruption


def _board(tmp_path: Path) -> Board:
    return Board.create(tmp_path / "board.json")


# --------------------------------------------------------------- schema / CRUD
def test_create_and_roundtrip(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a", tier="opus", owns=["src/a.py"], depends_on=[], goal="g", accept=["t"]))
    b.add(Unit(id="b", tier="opus", owns=["src/b.py"], depends_on=["a"]))

    reloaded = Board.load(tmp_path / "board.json")
    a = reloaded.get("a")
    assert a.tier == "opus" and a.owns == ["src/a.py"] and a.goal == "g"
    assert reloaded.get("b").depends_on == ["a"]
    assert [u.id for u in reloaded.units()] == ["a", "b"]  # stable id order


def test_create_refuses_existing(tmp_path: Path) -> None:
    _board(tmp_path)
    with pytest.raises(BoardError):
        Board.create(tmp_path / "board.json")


def test_add_duplicate_refused(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a"))
    with pytest.raises(BoardError):
        b.add(Unit(id="a"))


def test_bad_unit_id_rejected() -> None:
    with pytest.raises(LedgerCorruption):
        Unit(id="../etc")


def test_bad_state_rejected() -> None:
    with pytest.raises(BoardError):
        Unit(id="a", state="weird")


# ----------------------------------------------------------- state transitions
def test_legal_transitions(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a"))
    assert b.get("a").state == READY
    b.mark_claimed("a")
    assert Board.load(tmp_path / "board.json").get("a").state == CLAIMED
    b.mark_done("a")
    assert b.get("a").state == DONE


def test_illegal_transition_refused(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a"))
    b.mark_done("a")  # ready->... need claimed first? ready->done is allowed
    with pytest.raises(BoardError):
        b.mark_ready("a")  # done is terminal


def test_claimed_can_release_to_ready(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a"))
    b.mark_claimed("a")
    b.mark_ready("a")  # stale-claim reclaim path
    assert b.get("a").state == READY


# ------------------------------------------------------------ depends_on gating
def test_depends_on_gating(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a", owns=["src/a"]))
    b.add(Unit(id="b", owns=["src/b"], depends_on=["a"]))

    assert b.claimable("a") is True
    assert b.claimable("b") is False  # a not done

    b.mark_claimed("a")
    b.mark_done("a")
    assert b.claimable("b") is True


def test_depends_on_missing_unit_is_loud(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="b", depends_on=["nope"]))
    with pytest.raises(BoardError):
        b.claimable("b")


def test_only_ready_is_claimable(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a"))
    b.mark_blocked("a")
    assert b.claimable("a") is False


# --------------------------------------------------------- owned-path collision
def test_overlap_helper() -> None:
    assert B._overlap(["src/x"], ["src/x/y.py"]) is True   # nested
    assert B._overlap(["src/x/y.py"], ["src/x"]) is True   # nested (other way)
    assert B._overlap(["src/a"], ["src/b"]) is False       # disjoint


def test_colliding_ready_units_serialize_deterministically(tmp_path: Path) -> None:
    b = _board(tmp_path)
    # a and b both own the same path -> they collide; only the lowest id (a) is
    # claimable, b waits. Disjoint c is independently claimable.
    b.add(Unit(id="a", owns=["src/shared"]))
    b.add(Unit(id="b", owns=["src/shared/inner.py"]))
    b.add(Unit(id="c", owns=["src/other"]))

    assert b.claimable("a") is True
    assert b.claimable("b") is False   # collides with lower-id ready unit a
    assert b.claimable("c") is True
    assert [u.id for u in b.claimable_units()] == ["a", "c"]


def test_claimed_unit_blocks_overlapping_ready(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a", owns=["src/shared"]))
    b.add(Unit(id="b", owns=["src/shared"]))
    b.mark_claimed("a")
    assert b.claimable("b") is False  # never run concurrently with claimed overlap
    b.mark_done("a")
    assert b.claimable("b") is True   # collision clears once a is done


def test_blocked_collider_does_not_gate(tmp_path: Path) -> None:
    b = _board(tmp_path)
    b.add(Unit(id="a", owns=["src/shared"]))
    b.add(Unit(id="b", owns=["src/shared"]))
    b.mark_blocked("a")  # a is not ready/claimed -> does not block b
    assert b.claimable("b") is True
    _ = BLOCKED  # state constant exported
