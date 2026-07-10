"""Freeze-ring scorecard — records ranked capability snapshots with a
last-known-good fallback reader.

Each freeze cycle writes a versioned, timestamped artifact. The reader returns
the LATEST FROZEN artifact but falls back to the last-known-good if the latest
is missing or corrupt. This module must NOT import the rig grader
(fleet/benchmark) — it only reads/writes artifacts by path.
"""
from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

SCORECARD_PREFIX = "scorecard."
LATEST_FILENAME = "latest"
LKG_FILENAME = "lkg"


class ScorecardCorruption(RuntimeError):
    """Raised when a scorecard artifact is unreadable."""


@dataclass
class ScorecardRow:
    """One model's capability snapshot at a freeze point."""

    model: str
    work_class: str
    score: float
    samples: int
    metadata: dict = field(default_factory=dict)


@dataclass
class ScorecardArtifact:
    """A frozen scorecard at a point in time."""

    seq: int
    timestamp: float
    rows: list[ScorecardRow]
    metadata: dict = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "seq": self.seq,
            "timestamp": self.timestamp,
            "rows": [
                {
                    "model": r.model,
                    "work_class": r.work_class,
                    "score": r.score,
                    "samples": r.samples,
                    "metadata": r.metadata,
                }
                for r in self.rows
            ],
            "metadata": self.metadata,
        }

    @classmethod
    def from_dict(cls, d: dict) -> ScorecardArtifact:
        rows_data = d.get("rows", [])
        if not isinstance(rows_data, list):
            raise ScorecardCorruption("scorecard rows is not a list")
        rows = [
            ScorecardRow(
                model=str(r["model"]),
                work_class=str(r["work_class"]),
                score=float(r["score"]),
                samples=int(r.get("samples", 0)),
                metadata=dict(r.get("metadata", {})),
            )
            for r in rows_data
        ]
        return cls(
            seq=int(d["seq"]),
            timestamp=float(d["timestamp"]),
            rows=rows,
            metadata=dict(d.get("metadata", {})),
        )


class ScorecardStore:
    """Freeze-ring store: writes versioned artifacts, reads latest with LKG fallback.

    Directory layout::

        <root>/
            scorecard.0000001.json   # artifact 1
            scorecard.0000002.json   # artifact 2 (latest)
            latest                   # symlink or file containing "0000002"
            lkg                      # symlink or file containing "0000001"
    """

    def __init__(self, root: Path) -> None:
        self._root = root
        root.mkdir(parents=True, exist_ok=True)

    # --------------------------------------------------------------- writers

    def freeze(self, artifact: ScorecardArtifact) -> ScorecardArtifact:
        """Write a scorecard artifact and update latest + lkg pointers."""
        seq_str = str(artifact.seq).zfill(7)
        payload = json.dumps(artifact.to_dict(), indent=2)
        artifact_path = self._root / f"{SCORECARD_PREFIX}{seq_str}.json"
        tmp = artifact_path.with_suffix(artifact_path.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(payload, encoding="utf-8")
        tmp.replace(artifact_path)

        self._write_pointer(LATEST_FILENAME, seq_str)
        self._write_pointer(LKG_FILENAME, seq_str)
        return artifact

    # --------------------------------------------------------------- readers

    def read_latest(self) -> ScorecardArtifact | None:
        """Return the latest frozen scorecard, with LKG fallback.

        RED-TEAM FIX #2: if the latest artifact is missing or corrupt, returns
        the last-known-good artifact. If LKG also fails (e.g. both point at the
        same corrupt artifact), scans backward from LKG-1 for any readable
        artifact. Returns None only when ALL artifacts are absent or corrupt.
        """
        latest = self._read_pointer(LATEST_FILENAME)
        if latest is not None:
            artifact = self._read_artifact(latest)
            if artifact is not None:
                return artifact

        lkg = self._read_pointer(LKG_FILENAME)
        if lkg is not None:
            artifact = self._read_artifact(lkg)
            if artifact is not None:
                return artifact
            # Scan backward from LKG-1 until we find a readable artifact.
            lkg_int = int(lkg)
            for candidate in range(lkg_int - 1, 0, -1):
                art = self._read_artifact(str(candidate).zfill(7))
                if art is not None:
                    return art

        return None

    def read_at_seq(self, seq: int) -> ScorecardArtifact | None:
        """Read a specific artifact by sequence number, or None."""
        seq_str = str(seq).zfill(7)
        return self._read_artifact(seq_str)

    def latest_seq(self) -> int | None:
        """Return the latest sequence number from the latest pointer, or None."""
        raw = self._read_pointer(LATEST_FILENAME)
        if raw is None:
            return None
        return int(raw)

    def lkg_seq(self) -> int | None:
        """Return the last-known-good sequence number, or None."""
        raw = self._read_pointer(LKG_FILENAME)
        if raw is None:
            return None
        return int(raw)

    # -------------------------------------------------------------- internal

    def _artifact_path(self, seq_str: str) -> Path:
        return self._root / f"{SCORECARD_PREFIX}{seq_str}.json"

    def _write_pointer(self, name: str, seq_str: str) -> None:
        p = self._root / name
        tmp = p.with_suffix(p.suffix + f".tmp.{os.getpid()}")
        tmp.write_text(seq_str + "\n", encoding="utf-8")
        tmp.replace(p)

    def _read_pointer(self, name: str) -> str | None:
        p = self._root / name
        if not p.exists():
            return None
        try:
            return p.read_text(encoding="utf-8").strip()
        except OSError:
            return None

    def _read_artifact(self, seq_str: str) -> ScorecardArtifact | None:
        p = self._artifact_path(seq_str)
        if not p.exists():
            return None
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return None
        try:
            return ScorecardArtifact.from_dict(data)
        except (KeyError, TypeError, ScorecardCorruption):
            return None
