"""Actuals ledger — append-only record of real charon-run outcomes.

Each row represents one headless sub-session, keyed by (model, work_class).
Deterministic byproducts are stored: run result, packet-parses, fail-on-revert
+ gate pass/fail, failover hops, tokens, wall-clock. A low-weight
manager_accept column (D2) records human accept/reject separately so it never
dominates the deterministic signal.
"""
from __future__ import annotations

import json
import os
import time
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ActualRow:
    """One recorded actual outcome from a headless sub-session."""

    model: str
    work_class: str
    run_result: str  # pass / fail / error
    packet_parses: int
    fail_on_revert_pass: bool
    gate_pass: bool
    failover_hops: int
    tokens: int
    wall_clock_ms: int
    manager_accept: bool | None = None  # D2: separate low-weight column
    timestamp: float | None = None

    def to_dict(self) -> dict:
        d: dict = {
            "model": self.model,
            "work_class": self.work_class,
            "run_result": self.run_result,
            "packet_parses": self.packet_parses,
            "fail_on_revert_pass": self.fail_on_revert_pass,
            "gate_pass": self.gate_pass,
            "failover_hops": self.failover_hops,
            "tokens": self.tokens,
            "wall_clock_ms": self.wall_clock_ms,
        }
        if self.manager_accept is not None:
            d["manager_accept"] = self.manager_accept
        if self.timestamp is not None:
            d["timestamp"] = self.timestamp
        return d

    @classmethod
    def from_dict(cls, d: dict) -> ActualRow:
        return cls(
            model=str(d["model"]),
            work_class=str(d["work_class"]),
            run_result=str(d.get("run_result", "error")),
            packet_parses=int(d.get("packet_parses", 0)),
            fail_on_revert_pass=bool(d.get("fail_on_revert_pass", False)),
            gate_pass=bool(d.get("gate_pass", False)),
            failover_hops=int(d.get("failover_hops", 0)),
            tokens=int(d.get("tokens", 0)),
            wall_clock_ms=int(d.get("wall_clock_ms", 0)),
            manager_accept=d.get("manager_accept"),
            timestamp=d.get("timestamp"),
        )


class ActualsLedger:
    """Append-only JSONL store of real outcomes, keyed by (model, work_class).

    Crash-safe: a torn trailing line is skipped on read, never misinterpreted.
    A corrupt line in the middle of the file is skipped (and counted in
    ``skipped_corrupt``) so later valid rows are not lost.
    """

    def __init__(self, path: Path) -> None:
        self._path = path
        self.skipped_corrupt = 0
        path.parent.mkdir(parents=True, exist_ok=True)

    def append(self, row: ActualRow) -> None:
        """Durably append one row (fsync'd)."""
        if row.timestamp is None:
            row.timestamp = time.time()
        line = json.dumps(row.to_dict(), separators=(",", ":")) + "\n"
        with open(self._path, "a", encoding="utf-8") as fh:
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())

    def read(self) -> list[ActualRow]:
        """Read all rows; a torn trailing line is skipped, not misread.

        A corrupt line in the MIDDLE of the file is skipped and reading
        continues so later valid rows are not lost; the count is left in
        ``self.skipped_corrupt``.
        """
        if not self._path.exists():
            self.skipped_corrupt = 0
            return []
        skipped = 0
        out: list[ActualRow] = []
        lines = self._path.read_text().splitlines()
        n = len(lines)
        for idx, raw in enumerate(lines):
            raw = raw.strip()
            if not raw:
                continue
            try:
                d = json.loads(raw)
            except json.JSONDecodeError:
                # Last line torn during write -> tolerate silently, stop.
                if idx == n - 1:
                    break
                # Mid-file corruption -> skip it, keep later rows.
                skipped += 1
                continue
            out.append(ActualRow.from_dict(d))
        self.skipped_corrupt = skipped
        return out

    def query(
        self,
        model: str | None = None,
        work_class: str | None = None,
    ) -> list[ActualRow]:
        """Filter rows by optional model and/or work_class."""
        rows = self.read()
        if model is not None:
            rows = [r for r in rows if r.model == model]
        if work_class is not None:
            rows = [r for r in rows if r.work_class == work_class]
        return rows

    def clear(self) -> None:
        """Remove all rows (testing only)."""
        try:
            self._path.unlink()
        except FileNotFoundError:
            pass
