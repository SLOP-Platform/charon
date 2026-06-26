"""The Work Ledger — ONE per task, the single source of truth for progress
(ADR-0003 §4; INV-1). Agent sessions are satellite copies.

Crash-safety (reconciliation BR-1):
- ``ledger.json`` (metadata) is written atomically: temp file + fsync + os.replace.
- Checkpoints are append-only JSONL; a torn trailing line is skipped on read,
  never silently misinterpreted.
- A per-task lockfile (PID + mtime) prevents two coordinators corrupting one task;
  a stale lock (> TTL) is reclaimable.
- A malformed metadata file raises LOUDLY (LedgerCorruption) — never a silent
  downgrade to empty state.
- ``schema_version`` is stamped from the first commit (reconciliation OOB-C6).
"""
from __future__ import annotations

import json
import os
import re
import time
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import dataclass, field
from pathlib import Path

from .acceptance import AcceptanceCheck, derive_remaining, derive_verified
from .types import Usage

SCHEMA_VERSION = 1
_LOCK_TTL_SECONDS = 900  # a lock older than this is considered abandoned

# A task id is a single path segment under the state dir — never a path. This is
# the boundary guard against traversal (reconciliation BR2-9): `../etc`, absolute
# paths, and separators are rejected before any path join, so no surface (CLI,
# API, or a future HTTP endpoint) can escape the state dir via a crafted id.
_TASK_ID_RE = re.compile(r"^[a-z0-9][a-z0-9-]{0,63}$")


def validate_task_id(task_id: str) -> str:
    """Return ``task_id`` iff it is a safe single path segment, else raise."""
    if not _TASK_ID_RE.fullmatch(task_id):
        raise LedgerCorruption(
            f"invalid task id {task_id!r}: must match {_TASK_ID_RE.pattern} "
            f"(no path separators, no traversal)"
        )
    return task_id


class LedgerCorruption(RuntimeError):
    """Raised when the ledger on disk cannot be trusted. Always loud."""


class LedgerLocked(RuntimeError):
    """Raised when another live coordinator holds the task lock."""


@dataclass
class Checkpoint:
    """An append-only record of one dispatch's result."""

    seq: int
    provider: str
    commit: str | None
    verified: list[str]
    remaining: list[str]
    note: str = ""
    # Resource span for this dispatch (Tier 3); None if the backend reported none.
    usage: Usage | None = None
    # Consensus verdict at completion (Tier 4): True/False if a reviewer was
    # consulted, None if not (L0/L1, or no reviewer). Recorded for audit (INV-1).
    reviewer_passed: bool | None = None
    reviewer_note: str = ""
    # PERF-4 / D5 (ADR-0006): the role-DAG stage that produced this checkpoint
    # (triage/plan/…); "" for a plain single-unit run. Stages are checkpoint
    # METADATA on the ONE ledger — never a ledger per stage (INV-1).
    role: str = ""

    def to_dict(self) -> dict:
        d: dict = {
            "seq": self.seq,
            "provider": self.provider,
            "commit": self.commit,
            "verified": self.verified,
            "remaining": self.remaining,
            "note": self.note,
        }
        if self.usage is not None:
            d["usage"] = self.usage.to_dict()
        if self.reviewer_passed is not None:
            d["reviewer_passed"] = self.reviewer_passed
            d["reviewer_note"] = self.reviewer_note
        if self.role:
            d["role"] = self.role
        return d


@dataclass
class Ledger:
    """A vendor-neutral, on-disk, append-mostly record for one task."""

    root: Path  # <state_dir>/<task_id>
    task_id: str
    goal: str
    acceptance: list[AcceptanceCheck]
    target_repo: str  # worktree where acceptance checks run
    base_ref: str  # commit before any work; the floor lkg can never go below
    lkg_ref: str
    provider_history: list[str] = field(default_factory=list)
    schema_version: int = SCHEMA_VERSION

    # ------------------------------------------------------------------ paths
    @property
    def _meta_path(self) -> Path:
        return self.root / "ledger.json"

    @property
    def _checkpoints_path(self) -> Path:
        return self.root / "checkpoints.jsonl"

    @property
    def _lock_path(self) -> Path:
        return self.root / "lock"

    # --------------------------------------------------------------- creation
    @classmethod
    def create(
        cls,
        state_dir: Path,
        task_id: str,
        goal: str,
        acceptance: list[AcceptanceCheck],
        target_repo: str,
        base_ref: str,
    ) -> Ledger:
        validate_task_id(task_id)
        root = Path(state_dir) / task_id
        if (root / "ledger.json").exists():
            raise LedgerCorruption(
                f"ledger for task {task_id!r} already exists at {root}"
            )
        root.mkdir(parents=True, exist_ok=True)
        led = cls(
            root=root,
            task_id=task_id,
            goal=goal,
            acceptance=list(acceptance),
            target_repo=target_repo,
            base_ref=base_ref,
            lkg_ref=base_ref,
        )
        led._write_meta()
        led._checkpoints_path.touch()
        return led

    @classmethod
    def load(cls, state_dir: Path, task_id: str) -> Ledger:
        validate_task_id(task_id)
        root = Path(state_dir) / task_id
        meta_path = root / "ledger.json"
        if not meta_path.exists():
            raise LedgerCorruption(f"no ledger for task {task_id!r} at {root}")
        try:
            data = json.loads(meta_path.read_text())
        except (json.JSONDecodeError, OSError) as exc:
            raise LedgerCorruption(f"ledger metadata unreadable: {exc}") from exc
        if data.get("schema_version") != SCHEMA_VERSION:
            data = _migrate(data)
        try:
            return cls(
                root=root,
                task_id=data["task_id"],
                goal=data["goal"],
                acceptance=[AcceptanceCheck.from_dict(c) for c in data["acceptance"]],
                target_repo=data["target_repo"],
                base_ref=data["base_ref"],
                lkg_ref=data["lkg_ref"],
                provider_history=list(data.get("provider_history", [])),
                schema_version=SCHEMA_VERSION,
            )
        except (KeyError, TypeError) as exc:
            raise LedgerCorruption(f"ledger metadata malformed: {exc}") from exc

    # ----------------------------------------------------------------- writes
    def _write_meta(self) -> None:
        payload = {
            "schema_version": SCHEMA_VERSION,
            "task_id": self.task_id,
            "goal": self.goal,
            "acceptance": [c.to_dict() for c in self.acceptance],
            "target_repo": self.target_repo,
            "base_ref": self.base_ref,
            "lkg_ref": self.lkg_ref,
            "provider_history": self.provider_history,
        }
        _atomic_write(self._meta_path, json.dumps(payload, indent=2))

    def append_checkpoint(self, cp: Checkpoint) -> None:
        """Append a checkpoint durably (append-only JSONL, fsync'd)."""
        line = json.dumps(cp.to_dict(), separators=(",", ":")) + "\n"
        with open(self._checkpoints_path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def checkpoints(self) -> list[Checkpoint]:
        """Read checkpoints; a torn trailing line is skipped, not misread."""
        if not self._checkpoints_path.exists():
            return []
        out: list[Checkpoint] = []
        for raw in self._checkpoints_path.read_text().splitlines():
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                # torn write (only ever the last line); stop — do not guess.
                break
            out.append(
                Checkpoint(
                    seq=d["seq"],
                    provider=d["provider"],
                    commit=d.get("commit"),
                    verified=list(d.get("verified", [])),
                    remaining=list(d.get("remaining", [])),
                    note=d.get("note", ""),
                    usage=Usage.from_dict(d.get("usage")),
                    reviewer_passed=d.get("reviewer_passed"),
                    reviewer_note=d.get("reviewer_note", ""),
                    role=d.get("role", ""),
                )
            )
        return out

    def record_provider(self, name: str) -> None:
        self.provider_history.append(name)
        self._write_meta()

    # ------------------------------------------------------------ derivations
    def verified(self) -> set[str]:
        """GROUND: run acceptance checks against the target worktree."""
        return derive_verified(self.acceptance, self.target_repo)

    def remaining(self) -> set[str]:
        """``acceptance \\ verified`` — machine-derived (INV-6)."""
        return derive_remaining(self.acceptance, self.target_repo)

    def is_complete(self) -> bool:
        return not self.remaining()

    def cumulative_usage(self) -> Usage:
        """DERIVED truth: total spend re-summed from the recorded checkpoint
        spans (INV-1 extended to cost). A handoff receiver reads the same total
        from the ledger — it never resets per vendor (H3-for-cost)."""
        ti = to = ms = 0
        cost = 0.0
        for cp in self.checkpoints():
            if cp.usage is not None:
                ti += cp.usage.tokens_in
                to += cp.usage.tokens_out
                cost += cp.usage.cost_usd
                ms += cp.usage.latency_ms
        return Usage(tokens_in=ti, tokens_out=to, cost_usd=cost, latency_ms=ms)

    # -------------------------------------------------------------- lkg / INV-2
    def advance_lkg(self, ref: str) -> None:
        """Advance the last-known-good ref to ``ref``.

        INV-2: lkg_ref never points past an unverified commit. We only advance
        when *all* acceptance checks currently pass against disk. Otherwise the
        request is refused (loudly) so phantom progress cannot be recorded.
        """
        if self.remaining():
            raise LedgerCorruption(
                "refusing to advance lkg_ref past an unverified commit (INV-2): "
                f"remaining={sorted(self.remaining())}"
            )
        self.lkg_ref = ref
        self._write_meta()

    # ------------------------------------------------------------------- lock
    @contextmanager
    def lock(self) -> Iterator[None]:
        """Hold the per-task lock for the duration of a run."""
        self._acquire_lock()
        try:
            yield
        finally:
            self._release_lock()

    def _acquire_lock(self) -> None:
        if self._lock_path.exists():
            age = time.time() - self._lock_path.stat().st_mtime
            holder = self._lock_path.read_text().strip()
            # CONC-4 (ADR-0006): a stale lock is reclaimed by HOLDER LIVENESS, not
            # only by the TTL. Under parallel units a crashed unit must not wedge a
            # fresh coordinator on a shared `.charon` for the full TTL — if the
            # recorded pid is gone, the lock is dead and reclaimable now. We only
            # refuse when the holder is BOTH still alive AND within the TTL (a real
            # concurrent coordinator). An unparseable holder falls back to TTL.
            holder_pid = _holder_pid(holder)
            if age < _LOCK_TTL_SECONDS and (holder_pid is None or _pid_alive(holder_pid)):
                raise LedgerLocked(
                    f"task {self.task_id!r} is locked by {holder} "
                    f"({int(age)}s old); another coordinator is running"
                )
        _atomic_write(self._lock_path, f"pid={os.getpid()} t={int(time.time())}")

    def _release_lock(self) -> None:
        try:
            self._lock_path.unlink()
        except FileNotFoundError:
            pass


def _holder_pid(holder: str) -> int | None:
    """Parse the pid out of a ``pid=<n> t=<n>`` lockfile body, or None if the
    format is unrecognized (then liveness can't be checked → fall back to TTL)."""
    for tok in holder.split():
        if tok.startswith("pid="):
            try:
                return int(tok[4:])
            except ValueError:
                return None
    return None


def _pid_alive(pid: int) -> bool:
    """True iff ``pid`` is a live process. ``kill(pid, 0)`` probes existence
    without signalling; a PermissionError means it exists but is not ours (alive),
    ProcessLookupError means it is gone."""
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _atomic_write(path: Path, text: str) -> None:
    """Write ``text`` to ``path`` atomically (temp + fsync + replace)."""
    path.parent.mkdir(parents=True, exist_ok=True)
    tmp = path.with_suffix(path.suffix + f".tmp.{os.getpid()}")
    with open(tmp, "w", encoding="utf-8") as fh:
        fh.write(text)
        fh.flush()
        os.fsync(fh.fileno())
    os.replace(tmp, path)


def _migrate(data: dict) -> dict:
    """Forward-migrate an older ledger payload. Loud on unknown versions."""
    version = data.get("schema_version")
    # No prior versions exist yet; an unknown version must not be silently used.
    raise LedgerCorruption(
        f"ledger schema_version {version!r} is not migratable by this build "
        f"(expected {SCHEMA_VERSION})"
    )
