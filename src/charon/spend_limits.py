from __future__ import annotations

import json
import os
import threading
from datetime import datetime
from pathlib import Path

from charon import secrets
from charon.types import SpendDecision

_STATE_FILE = "spend.json"


class SpendLimiter:
    def __init__(self, monthly_limit_usd: float = 0.0, state_dir: Path | None = None):
        self._limit_usd = monthly_limit_usd
        self._spent_usd: float = 0.0
        self._month_start: str = ""
        self._state_dir = state_dir or secrets.config_dir()
        self._lock = threading.RLock()
        self._load()

    def check(self, estimated_cost: float) -> SpendDecision:
        with self._lock:
            if self._limit_usd == 0.0:
                return SpendDecision(
                    allowed=True, remaining=float("inf"), reason=""
                )
            self._ensure_month_reset()
            projected = self._spent_usd + estimated_cost
            if projected > self._limit_usd:
                return SpendDecision(
                    allowed=False,
                    remaining=self._limit_usd - self._spent_usd,
                    reason="monthly spend cap exceeded",
                )
            return SpendDecision(
                allowed=True,
                remaining=self._limit_usd - projected,
                reason="",
            )

    def record(self, cost: float):
        with self._lock:
            self._ensure_month_reset()
            self._spent_usd += cost
            self._save()

    def remaining(self) -> float:
        with self._lock:
            if self._limit_usd == 0.0:
                return float("inf")
            return self._limit_usd - self._spent_usd

    def _ensure_month_reset(self):
        current = datetime.now().strftime("%Y-%m")
        if current != self._month_start:
            self._spent_usd = 0.0
            self._month_start = current

    def _load(self):
        p = self._state_dir / _STATE_FILE
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        self._spent_usd = float(data.get("spent_usd", 0.0))
        self._month_start = str(data.get("month_start", ""))

    def _save(self):
        d = self._state_dir
        d.mkdir(parents=True, exist_ok=True)
        p = d / _STATE_FILE
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(
            json.dumps(
                {
                    "spent_usd": self._spent_usd,
                    "month_start": self._month_start,
                    "monthly_limit_usd": self._limit_usd,
                },
                indent=2,
            ),
            encoding="utf-8",
        )
        os.replace(tmp, p)
