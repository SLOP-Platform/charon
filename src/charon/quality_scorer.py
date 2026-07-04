"""Per-provider quality scoring for gateway routing (PROPOSAL-1 F1).

Tracks latency EWMA, cumulative success rate, and a composite reliability score.
Thread-safe; persists to ``quality.json`` in the config dir.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from charon import secrets
from charon.types import QualityRecord

_QUALITY_FILE = "quality.json"
_ALPHA = 0.34

_LATENCY_WEIGHT = 0.3
_SUCCESS_WEIGHT = 0.4
_NO_DOWNGRADE_WEIGHT = 0.3
_LATENCY_THRESHOLD_MS = 30_000


class QualityScorer:
    def __init__(self, state_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._dir = state_dir or secrets.config_dir()
        self._records: dict[str, QualityRecord] = {}
        self._load()

    def record(self, provider: str, latency_ms: int, success: bool, tokens: int) -> None:
        with self._lock:
            rec = self._ensure(provider)
            rec.latency_ewma_ms = _ALPHA * latency_ms + (1 - _ALPHA) * rec.latency_ewma_ms
            rec.calls += 1
            if success:
                rec.successes += 1
            latency_ok = 1.0 if latency_ms < _LATENCY_THRESHOLD_MS else 0.0
            http_success = 1.0 if success else 0.0
            rec.reliability_score = max(
                0.0,
                min(
                    1.0,
                    latency_ok * _LATENCY_WEIGHT
                    + http_success * _SUCCESS_WEIGHT
                    + 1.0 * _NO_DOWNGRADE_WEIGHT,
                ),
            )
            self._save()

    def score(self, provider: str) -> float:
        with self._lock:
            return self._ensure(provider).reliability_score

    def _ensure(self, provider: str) -> QualityRecord:
        if provider not in self._records:
            self._records[provider] = QualityRecord(provider=provider)
        return self._records[provider]

    def _save(self) -> None:
        data: dict[str, dict] = {}
        for name, rec in self._records.items():
            data[name] = {
                "provider": rec.provider,
                "calls": rec.calls,
                "successes": rec.successes,
                "latency_ewma_ms": rec.latency_ewma_ms,
                "reliability_score": rec.reliability_score,
            }
        d = self._dir
        d.mkdir(parents=True, exist_ok=True)
        p = self._path()
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        tmp.replace(p)

    def _load(self) -> None:
        p = self._path()
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        for name, d in data.items():
            if isinstance(d, dict):
                self._records[name] = QualityRecord(
                    provider=str(d.get("provider", name)),
                    calls=int(d.get("calls", 0)),
                    successes=int(d.get("successes", 0)),
                    latency_ewma_ms=float(d.get("latency_ewma_ms", 0.0)),
                    reliability_score=float(d.get("reliability_score", 0.5)),
                )

    def _path(self) -> Path:
        return self._dir / _QUALITY_FILE
