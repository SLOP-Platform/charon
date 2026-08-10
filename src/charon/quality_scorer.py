"""Per-provider quality scoring for gateway routing.

Tracks latency EWMA, cumulative success rate, and a composite reliability score.
Thread-safe; persists to ``quality.json`` in the config dir.

The score combines three signals weighted equally:
  - latency: 1.0 when under threshold, decays linearly to 0 at 2× threshold
  - success rate: accumulated successes / max(1, accumulated calls)
  - no-downgrade: 1.0 when the observer has never flagged a downgrade,
    decaying toward 0 as the downgrade ratio increases

Cold-start policy: an unmeasured provider reports sufficient calls (N=0 → no
history → default 0.5) to pass the floor immediately rather than being excluded.
Once measured, the score reflects real accumulated history.
"""
from __future__ import annotations

import json
import threading
from pathlib import Path

from charon import secrets

_FILENAME = "quality.json"
_ALPHA = 0.34
_LATENCY_THRESHOLD_MS = 30_000

# Weights: three equally-weighted signals
_LATENCY_WEIGHT = 1.0 / 3.0
_SUCCESS_RATE_WEIGHT = 1.0 / 3.0
_NO_DOWNGRADE_WEIGHT = 1.0 / 3.0


class QualityScorer:
    def __init__(self, state_dir: Path | None = None) -> None:
        self._lock = threading.RLock()
        self._dir = state_dir or secrets.config_dir()
        self._records: dict[str, dict] = {}
        self._downgrade_counts: dict[str, int] = {}
        self._load()

    def record(
        self, provider: str, latency_ms: int, success: bool, tokens: int,
        *, downgrade: bool = False,
    ) -> None:
        with self._lock:
            r = self._ensure(provider)
            r["latency_ewma_ms"] = (
                _ALPHA * latency_ms + (1 - _ALPHA) * r["latency_ewma_ms"])
            r["calls"] += 1
            if success:
                r["successes"] += 1
            if downgrade:
                self._downgrade_counts[provider] = (
                    self._downgrade_counts.get(provider, 0) + 1)
            self._save()

    def score(self, provider: str) -> float:
        with self._lock:
            r = self._ensure(provider)
            calls = r["calls"]
            successes = r["successes"]
            downgrades = self._downgrade_counts.get(provider, 0)

            if calls == 0:
                return 0.5  # cold-start: unmeasured → default pass

            lat_norm = max(0.0, 1.0 - r["latency_ewma_ms"] / (2 * _LATENCY_THRESHOLD_MS))
            lat_term = lat_norm * _LATENCY_WEIGHT

            success_rate = successes / calls
            success_term = success_rate * _SUCCESS_RATE_WEIGHT

            downgrade_rate = downgrades / calls
            downgrade_term = (1.0 - downgrade_rate) * _NO_DOWNGRADE_WEIGHT

            return float(max(0.0, min(1.0, lat_term + success_term + downgrade_term)))

    def downgrade_count(self, provider: str) -> int:
        with self._lock:
            return self._downgrade_counts.get(provider, 0)

    def _ensure(self, provider: str) -> dict:
        if provider not in self._records:
            self._records[provider] = {
                "calls": 0,
                "successes": 0,
                "latency_ewma_ms": 0.0,
            }
        return self._records[provider]

    def _save(self) -> None:
        data: dict[str, dict] = {}
        for name, r in self._records.items():
            data[name] = dict(r)
            data[name]["downgrades"] = self._downgrade_counts.get(name, 0)
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
                self._records[name] = {
                    "calls": int(d.get("calls", 0)),
                    "successes": int(d.get("successes", 0)),
                    "latency_ewma_ms": float(d.get("latency_ewma_ms", 0.0)),
                }
                dg = d.get("downgrades")
                if dg is not None:
                    self._downgrade_counts[name] = int(dg)

    def _path(self) -> Path:
        return self._dir / _FILENAME
