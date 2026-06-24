from __future__ import annotations

from pathlib import Path

import pytest

from charon.acceptance import AcceptanceCheck
from charon.gitutil import head
from charon.ledger import Checkpoint, Ledger, LedgerCorruption, LedgerLocked


def _mk(state_dir: Path, repo: Path) -> Ledger:
    checks = [AcceptanceCheck("a0", "test -f done.txt")]
    return Ledger.create(state_dir, "t1", "goal", checks, str(repo), head(repo))


def test_create_and_load_roundtrip(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    led.append_checkpoint(Checkpoint(1, "mock", None, [], ["a0"]))
    again = Ledger.load(state_dir, "t1")
    assert again.goal == "goal"
    assert again.schema_version == 1
    assert len(again.checkpoints()) == 1


def test_remaining_derived_from_disk(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    assert led.remaining() == {"a0"}
    (git_repo / "done.txt").write_text("x")
    assert led.remaining() == set()
    assert led.is_complete()


def test_inv2_lkg_refuses_to_advance_past_unverified(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    # remaining is non-empty -> advancing lkg must raise (INV-2).
    with pytest.raises(LedgerCorruption):
        led.advance_lkg("deadbeef")
    # once verified, advance is allowed.
    (git_repo / "done.txt").write_text("x")
    led.advance_lkg("cafef00d")
    assert led.lkg_ref == "cafef00d"


def test_malformed_metadata_is_loud(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    led._meta_path.write_text("{ this is not json")
    with pytest.raises(LedgerCorruption):
        Ledger.load(state_dir, "t1")


def test_torn_checkpoint_line_is_skipped_not_misread(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    led.append_checkpoint(Checkpoint(1, "mock", None, [], ["a0"]))
    # simulate a torn trailing write (crash mid-append).
    with open(led._checkpoints_path, "a") as fh:
        fh.write('{"seq": 2, "provider": "mock", "veri')  # no newline, truncated
    cps = led.checkpoints()
    assert len(cps) == 1  # the good record, torn one dropped — not misread
    assert cps[0].seq == 1


def test_concurrent_coordinator_lock(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    led2 = Ledger.load(state_dir, "t1")
    with led.lock():
        with pytest.raises(LedgerLocked):
            with led2.lock():
                pass
