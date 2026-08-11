"""Simple per-request spend limiter with per-provider tracking.

Tracks cumulative spend globally and per-provider to enforce monthly caps.
Configurable via gateway module config::

    modules.spend.monthly_limit_usd: float       # global cap (0.0 = no limit)
    modules.spend.provider_limits: dict[str,float]  # per-provider caps

When a cap is hit, ``check()`` returns ``allowed=False`` and the gateway responds
HTTP 402 before making an upstream call — no spend leak through a capped path.
"""
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
    def __init__(
        self,
        monthly_limit_usd: float = 0.0,
        state_dir: Path | None = None,
        *,
        provider_limits: dict[str, float] | None = None,
    ):
        self._limit_usd = monthly_limit_usd
        self._spent_usd: float = 0.0
        self._month_start: str = ""
        self._state_dir = state_dir or secrets.config_dir()
        self._lock = threading.RLock()
        self._provider_limits = dict(provider_limits or {})
        self._provider_spent: dict[str, float] = {}
        self._load()

    def check(self, estimated_cost: float, *, provider: str | None = None) -> SpendDecision:
        with self._lock:
            self._ensure_month_reset()
            # Per-provider cap — checked before global
            if provider and provider in self._provider_limits:
                limit = self._provider_limits[provider]
                if limit > 0.0:
                    pspent = self._provider_spent.get(provider, 0.0)
                    projected = pspent + estimated_cost
                    if projected > limit:
                        return SpendDecision(
                            allowed=False,
                            remaining=limit - pspent,
                            reason=f"per-provider monthly spend cap exceeded for {provider}",
                        )
            # Global cap
            if self._limit_usd == 0.0:
                return SpendDecision(
                    allowed=True, remaining=float("inf"), reason=""
                )
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

    def record(self, cost: float, *, provider: str | None = None):
        with self._lock:
            self._ensure_month_reset()
            self._spent_usd += cost
            if provider is not None:
                self._provider_spent[provider] = (
                    self._provider_spent.get(provider, 0.0) + cost)
            self._save()

    def remaining(self, *, provider: str | None = None) -> float:
        with self._lock:
            if provider and provider in self._provider_limits:
                limit = self._provider_limits[provider]
                return limit - self._provider_spent.get(provider, 0.0)
            if self._limit_usd == 0.0:
                return float("inf")
            return self._limit_usd - self._spent_usd

    def provider_spent(self, provider: str) -> float:
        with self._lock:
            return self._provider_spent.get(provider, 0.0)

    def provider_limits(self) -> dict[str, float]:
        with self._lock:
            return dict(self._provider_limits)

    def spent_summary(self) -> dict:
        with self._lock:
            return {
                "total": self._spent_usd,
                "global_limit": self._limit_usd,
                "provider_spent": dict(self._provider_spent),
                "provider_limits": dict(self._provider_limits),
                "month_start": self._month_start,
            }

    def _ensure_month_reset(self):
        current = datetime.now().strftime("%Y-%m")
        if current != self._month_start:
            self._spent_usd = 0.0
            self._provider_spent = {}
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
        self._provider_spent = {}
        ps = data.get("provider_spent")
        if isinstance(ps, dict):
            for k, v in ps.items():
                self._provider_spent[str(k)] = float(v)

    def _save(self):
        d = self._state_dir
        d.mkdir(parents=True, exist_ok=True)
        p = d / _STATE_FILE
        tmp = p.with_name(p.name + ".tmp")
        out = {
            "spent_usd": self._spent_usd,
            "month_start": self._month_start,
            "monthly_limit_usd": self._limit_usd,
            "provider_spent": self._provider_spent,
        }
        if self._provider_limits:
            out["provider_limits"] = self._provider_limits
        tmp.write_text(json.dumps(out, indent=2), encoding="utf-8")
        os.replace(tmp, p)
