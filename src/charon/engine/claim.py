"""Atomic unit claim with an epoch fencing token (ADR-0010 D2, DTC Lens-4).

A *claim* is a thin generalization of ``ledger.py``'s PID-liveness file lock
(CONC-4) from one task to N units. The atomic test-and-set is an exclusive create
(``O_CREAT | O_EXCL``) — only one creator wins per unit, so there are never two
live holders under contention. Staleness reuses ``ledger``'s exact liveness/TTL
logic (imported, not reimplemented): a claim is dead when its recorded PID is gone
or it has aged past the lock TTL.

Each successful (re)claim allocates a strictly increasing **epoch** from a durable
per-unit ``<id>.epoch`` file that survives release and crash. The epoch is the
double-execution fencing token: a reclaim's epoch always exceeds the stale
holder's, and ``release`` is epoch-fenced so a stale worker cannot release the
fresh holder's claim. A stale claim is reclaimable only onto a FRESH worktree,
never the in-flight one.

NOT in v1 (per D2): heartbeat, remote-lease, or any second lock implementation.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from ..ledger import _LOCK_TTL_SECONDS, _pid_alive, validate_task_id


class ClaimContended(RuntimeError):
    """Raised when a unit is already held by a live worker (or is mid-claim)."""


class StaleReclaim(RuntimeError):
    """Raised on an illegal reclaim: targeting the in-flight worktree, or a
    stale-epoch ``release`` that would fence out the fresh holder."""


@dataclass(frozen=True)
class Claim:
    """A live claim record. ``epoch`` is the monotonic fencing token; ``worktree``
    is the absolute path of the worktree this unit is executing in."""

    unit_id: str
    pid: int
    epoch: int
    worktree: str
    t: int

    def to_dict(self) -> dict[str, Any]:
        return {
            "unit_id": self.unit_id,
            "pid": self.pid,
            "epoch": self.epoch,
            "worktree": self.worktree,
            "t": self.t,
        }


def _claim_path(claims_dir: Path, unit_id: str) -> Path:
    return Path(claims_dir) / f"{unit_id}.claim"


def _epoch_path(claims_dir: Path, unit_id: str) -> Path:
    return Path(claims_dir) / f"{unit_id}.epoch"


def _norm_worktree(worktree: str | os.PathLike[str]) -> str:
    return os.path.abspath(os.fspath(worktree))


def _read_claim(path: Path) -> Claim | None:
    """Parse a claim file; ``None`` if absent, empty, or torn (never a guess)."""
    try:
        raw = path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    raw = raw.strip()
    if not raw:
        return None
    try:
        d = json.loads(raw)
        return Claim(
            unit_id=d["unit_id"],
            pid=int(d["pid"]),
            epoch=int(d["epoch"]),
            worktree=d["worktree"],
            t=int(d["t"]),
        )
    except (json.JSONDecodeError, KeyError, TypeError, ValueError):
        return None


def _is_live(claim_rec: Claim | None, now: float) -> bool:
    """Mirror ``ledger._acquire_lock``: a holder is live iff it is within the TTL
    AND its PID is still alive. Otherwise the claim is reclaimable."""
    if claim_rec is None:
        return False
    if now - claim_rec.t >= _LOCK_TTL_SECONDS:
        return False
    return _pid_alive(claim_rec.pid)


def _next_epoch(claims_dir: Path, unit_id: str) -> int:
    """Allocate the next monotonic epoch from the durable per-unit counter. Only
    ever called by the exclusive-create winner, so it is race-free per unit."""
    path = _epoch_path(claims_dir, unit_id)
    try:
        cur = int(path.read_text(encoding="utf-8").strip())
    except (FileNotFoundError, ValueError):
        cur = 0
    nxt = cur + 1
    # atomic temp + fsync + replace (same primitive as the ledger)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(str(nxt))
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)
    return nxt


def _write_claim_fd(fd: int, claim_rec: Claim) -> None:
    payload = json.dumps(claim_rec.to_dict(), separators=(",", ":"))
    os.write(fd, payload.encode("utf-8"))
    os.fsync(fd)


def _create_exclusive(
    claims_dir: Path, unit_id: str, pid: int, worktree: str, now: float
) -> Claim:
    """Atomically create the claim file (``O_EXCL``) and stamp a fresh epoch.
    Raises ``FileExistsError`` if a claim file already exists (the loser path)."""
    path = _claim_path(claims_dir, unit_id)
    path.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(path, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
    try:
        epoch = _next_epoch(claims_dir, unit_id)
        rec = Claim(unit_id=unit_id, pid=pid, epoch=epoch, worktree=worktree, t=int(now))
        _write_claim_fd(fd, rec)
        return rec
    finally:
        os.close(fd)


def claim(
    claims_dir: Path,
    unit_id: str,
    worktree: str | os.PathLike[str],
    *,
    pid: int | None = None,
    now: float | None = None,
) -> Claim:
    """Atomically claim ``unit_id`` for execution in ``worktree``.

    Wins via an exclusive create. If a claim already exists: a *live* holder
    raises :class:`ClaimContended`; a *stale* holder is reclaimable, but only onto
    a FRESH ``worktree`` (reclaiming onto the stale in-flight worktree raises
    :class:`StaleReclaim`). The reclaim re-creates the file exclusively, so two
    racing reclaimers cannot both become holders.
    """
    validate_task_id(unit_id)
    pid = os.getpid() if pid is None else pid
    now = time.time() if now is None else now
    worktree = _norm_worktree(worktree)
    path = _claim_path(claims_dir, unit_id)

    try:
        return _create_exclusive(claims_dir, unit_id, pid, worktree, now)
    except FileExistsError:
        pass

    existing = _read_claim(path)
    if _is_live(existing, now):
        assert existing is not None
        raise ClaimContended(
            f"unit {unit_id!r} is held by pid {existing.pid} "
            f"(epoch {existing.epoch}, worktree {existing.worktree})"
        )

    # Stale (dead/aged) or torn/empty. A torn file with no recoverable record is
    # only reclaimable once it too has aged past the TTL (else it may be a claim
    # mid-write — never steal an in-flight one).
    if existing is None:
        try:
            age = now - path.stat().st_mtime
        except FileNotFoundError:
            age = _LOCK_TTL_SECONDS  # vanished under us; treat as reclaimable
        if age < _LOCK_TTL_SECONDS:
            raise ClaimContended(
                f"unit {unit_id!r} has an in-flight or unreadable claim; not stealing"
            )
    elif _norm_worktree(existing.worktree) == worktree:
        raise StaleReclaim(
            f"unit {unit_id!r}: refusing to reclaim onto the in-flight worktree "
            f"{worktree!r} — a stale claim is reclaimable only onto a FRESH worktree"
        )

    # Reclaim: drop the stale file, then re-create exclusively. If another worker
    # wins the race, we lose loudly (never two holders).
    try:
        os.unlink(path)
    except FileNotFoundError:
        pass
    try:
        return _create_exclusive(claims_dir, unit_id, pid, worktree, now)
    except FileExistsError:
        raise ClaimContended(
            f"unit {unit_id!r}: lost the reclaim race to another worker"
        ) from None


def release(
    claims_dir: Path, unit_id: str, *, epoch: int, now: float | None = None
) -> bool:
    """Release the claim on ``unit_id`` held under ``epoch``.

    Epoch-fenced: if the on-disk claim carries a *different* epoch, the caller's
    token is stale (a reclaim has occurred) and the release is refused with
    :class:`StaleReclaim` — a double-executing zombie cannot drop the fresh
    holder's claim. Returns ``True`` if a claim was removed, ``False`` if none
    existed.
    """
    validate_task_id(unit_id)
    path = _claim_path(claims_dir, unit_id)
    existing = _read_claim(path)
    if existing is None:
        # Nothing well-formed to release. Clean up a torn/empty remnant only if it
        # has no live owner is impossible to prove; leave it for TTL reclaim.
        return False
    if existing.epoch != epoch:
        raise StaleReclaim(
            f"unit {unit_id!r}: epoch {epoch} is stale (current claim holds "
            f"epoch {existing.epoch}); release fenced out"
        )
    try:
        os.unlink(path)
    except FileNotFoundError:
        return False
    return True


def current(claims_dir: Path, unit_id: str) -> Claim | None:
    """The current well-formed claim record for ``unit_id``, or ``None``."""
    return _read_claim(_claim_path(claims_dir, unit_id))


def is_held(claims_dir: Path, unit_id: str, *, now: float | None = None) -> bool:
    """True iff ``unit_id`` is currently held by a LIVE worker."""
    now = time.time() if now is None else now
    return _is_live(_read_claim(_claim_path(claims_dir, unit_id)), now)
