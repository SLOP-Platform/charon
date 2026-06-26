from __future__ import annotations

import os
import time
from pathlib import Path

import pytest

from charon.acceptance import AcceptanceCheck
from charon.gitutil import head
from charon.ledger import (
    Checkpoint,
    Ledger,
    LedgerCorruption,
    LedgerLocked,
    validate_task_id,
)


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


@pytest.mark.parametrize(
    "bad", ["../etc", "..", "a/b", "/abs", "x/../../etc", "-leading", "UPPER", "x" * 65]
)
def test_task_id_traversal_rejected(bad: str, state_dir: Path, git_repo: Path) -> None:
    # BR2-9: a crafted task id must never escape the state dir, on any surface.
    checks = [AcceptanceCheck("a0", "test -f done.txt")]
    with pytest.raises(LedgerCorruption):
        Ledger.create(state_dir, bad, "g", checks, str(git_repo), head(git_repo))
    with pytest.raises(LedgerCorruption):
        Ledger.load(state_dir, bad)


def test_valid_task_ids_accepted() -> None:
    for ok in ["t1", "create-hello-abc12345", "a", "0", "x" * 64]:
        assert validate_task_id(ok) == ok


def test_concurrent_coordinator_lock(state_dir: Path, git_repo: Path) -> None:
    led = _mk(state_dir, git_repo)
    led2 = Ledger.load(state_dir, "t1")
    with led.lock():
        with pytest.raises(LedgerLocked):
            with led2.lock():
                pass


def test_live_holder_lock_is_not_reclaimed(state_dir: Path, git_repo: Path) -> None:
    """CONC-4: a lock held by a LIVE pid within TTL still blocks — a real
    concurrent coordinator is never stolen from."""
    led = _mk(state_dir, git_repo)
    # write a lock owned by THIS process (alive), fresh.
    led._lock_path.write_text(f"pid={os.getpid()} t={int(time.time())}")
    with pytest.raises(LedgerLocked):
        led._acquire_lock()


def test_dead_holder_stale_lock_is_reclaimed_by_liveness(state_dir: Path, git_repo: Path) -> None:
    """CONC-4: a stale lock whose holder PID is DEAD is reclaimed by liveness even
    when younger than the TTL — so a crashed unit on a shared `.charon` does not
    wedge a fresh coordinator until the 15-minute TTL elapses."""
    led = _mk(state_dir, git_repo)
    dead_pid = _a_dead_pid()
    led._lock_path.write_text(f"pid={dead_pid} t={int(__import__('time').time())}")
    # younger than TTL, but the holder is gone → reclaimable immediately.
    led._acquire_lock()  # must NOT raise
    led._release_lock()


def _a_dead_pid() -> int:
    """Find a PID that is not currently alive (best-effort, deterministic-ish)."""
    for pid in range(2_000_000, 2_000_050):
        try:
            os.kill(pid, 0)
        except ProcessLookupError:
            return pid
        except PermissionError:
            continue
    return 2_000_000
