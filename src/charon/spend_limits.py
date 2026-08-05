"""The monthly spend cap and the counter it enforces against.

Money path. Three properties this module must hold, in priority order:

1. **The number is TRUE or explicitly UNKNOWN.** A completion whose cost the
   provider did not report is counted in ``unpriced_count`` — never folded into
   ``spent_usd`` as a synthesised floor. A fabricated floor is what inflated this
   counter to a fictional ~$223, and later to $1185.44 against ~$1.34 of real
   metered spend. A confident wrong number steers routing; a null does not.
2. **It fails CLOSED.** If the persisted state exists but cannot be read, or
   carries a non-finite / negative ``spent_usd``, the limiter REFUSES rather than
   serving. An unreadable counter that silently reads ``0.0`` is an uncapped
   gateway wearing a cap's clothes.
3. **The cap is settable while running.** ``monthly_limit_usd`` is re-read from
   disk on every ``check()`` and every ``record()``, and the running process
   never clobbers an external edit back to its constructor value. Before this,
   the only way to cap a runaway was to restart it.

The corrupted-counter RESET path (``reset_month`` / the on-disk
``reset_requested`` flag) exists because a corrupt historical total is not
recoverable and must not be carried forward as if it were real — but it is
never memory-holed either: the discarded value is preserved under ``last_reset``.
"""

from __future__ import annotations

import json
import math
import os
import threading
from datetime import datetime
from pathlib import Path

from charon import secrets
from charon.types import SpendDecision

_STATE_FILE = "spend.json"


def _finite(value) -> float | None:
    """``float(value)`` if it is a real, finite number, else ``None``.

    ``NaN`` is the sharpest edge here: ``json.loads`` accepts a bare ``NaN``
    literal, and ``nan + x`` is ``nan`` while ``nan > limit`` is ``False`` — so a
    single NaN reaching ``_spent_usd`` disables the cap permanently and silently.
    Every number crossing this module's boundary goes through here.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    if not math.isfinite(f):
        return None
    return f


class SpendLimiter:
    def __init__(self, monthly_limit_usd: float = 0.0, state_dir: Path | None = None):
        limit = _finite(monthly_limit_usd)
        if limit is None or limit < 0:
            # Constructor time, no request in flight: raise rather than coerce.
            # Coercing an unusable cap to 0.0 would mean "no cap" — the one
            # translation a spend limiter must never make on its own.
            raise ValueError(
                f"monthly_limit_usd must be a finite, non-negative number, got "
                f"{monthly_limit_usd!r}"
            )
        self._limit_usd = limit
        self._spent_usd: float = 0.0
        self._unpriced_count: int = 0
        self._invalid_cost_count: int = 0
        self._per_provider: dict[str, float] = {}
        self._unpriced_by_provider: dict[str, int] = {}
        self._month_start: str = ""
        self._last_reset: dict | None = None
        # Fail-closed latch: set when the state file EXISTS but cannot be
        # trusted. An ABSENT file is a fresh install, not a fault.
        self._unreadable_reason: str = ""
        self._state_dir = state_dir or secrets.config_dir()
        self._lock = threading.RLock()
        self._refresh()

    # ── decisions ────────────────────────────────────────────────────

    def check(self, estimated_cost: float) -> SpendDecision:
        with self._lock:
            self._refresh()
            if self._unreadable_reason:
                return SpendDecision(
                    allowed=False,
                    remaining=0.0,
                    reason=(
                        "spend state unreadable, refusing to serve (fail-closed): "
                        f"{self._unreadable_reason}"
                    ),
                )
            self._ensure_month_reset()
            if self._limit_usd == 0.0:
                return SpendDecision(allowed=True, remaining=float("inf"), reason="")
            est = _finite(estimated_cost)
            if est is None or est < 0:
                return SpendDecision(
                    allowed=False,
                    remaining=self._limit_usd - self._spent_usd,
                    reason=(
                        "spend pre-flight estimate is not a usable number "
                        f"({estimated_cost!r}), refusing to serve (fail-closed)"
                    ),
                )
            projected = self._spent_usd + est
            if projected > self._limit_usd:
                return SpendDecision(
                    allowed=False,
                    remaining=self._limit_usd - self._spent_usd,
                    reason=(
                        "monthly spend cap exceeded: monthly cap "
                        f"${self._limit_usd:.2f} reached, ${self._spent_usd:.2f} spent "
                        f"in {self._month_start or 'this month'} "
                        f"(this request est ${est:.2f}, {self._unpriced_count} "
                        "unpriced calls not counted)"
                    ),
                )
            return SpendDecision(
                allowed=True, remaining=self._limit_usd - projected, reason=""
            )

    def remaining(self) -> float:
        with self._lock:
            if self._unreadable_reason:
                return 0.0
            if self._limit_usd == 0.0:
                return float("inf")
            return self._limit_usd - self._spent_usd

    # ── accrual ──────────────────────────────────────────────────────

    def record(self, cost: float, provider: str | None = None) -> None:
        """Accrue a KNOWN provider-reported cost.

        A cost that is not a finite, non-negative number is not a cost — it is an
        UNKNOWN, and is routed to the unpriced counter instead of being folded
        into the dollar total. It never raises: the response has already been
        served by the time this is called, and corrupting the counter (or
        crashing the response path) are both worse than counting an unknown.
        """
        with self._lock:
            self._refresh()
            self._ensure_month_reset()
            c = _finite(cost)
            if c is None or c < 0:
                self._invalid_cost_count += 1
                self._note_unpriced(provider)
                self._save()
                return
            self._spent_usd += c
            if provider:
                self._per_provider[provider] = self._per_provider.get(provider, 0.0) + c
            self._save()

    def record_unpriced(self, provider: str | None = None) -> None:
        """Record a completion whose cost the provider did NOT report.

        Increments an explicit UNKNOWN count. It must never touch ``spent_usd``:
        substituting a fabricated floor here is the inflation bug this module
        exists to prevent.
        """
        with self._lock:
            self._refresh()
            self._ensure_month_reset()
            self._note_unpriced(provider)
            self._save()

    def _note_unpriced(self, provider: str | None) -> None:
        self._unpriced_count += 1
        if provider:
            self._unpriced_by_provider[provider] = (
                self._unpriced_by_provider.get(provider, 0) + 1
            )

    # ── reset ────────────────────────────────────────────────────────

    def reset_month(self, reason: str = "operator reset") -> dict:
        """Zero the month's counters, preserving the discarded value for audit.

        Arming step 2: the August counter read $1185.44 against ~$1.34 of real
        metered spend. That total is not repairable, and setting a $50 cap
        against it would refuse every request — an outage, not a control. The
        discarded figures are written to ``last_reset`` so the reset is visible
        rather than a quiet rewrite of history.
        """
        with self._lock:
            record = {
                "at": datetime.now().strftime("%Y-%m-%dT%H:%M:%S"),
                "month": self._month_start,
                "previous_spent_usd": self._spent_usd,
                "previous_unpriced_count": self._unpriced_count,
                "previous_per_provider": dict(self._per_provider),
                "reason": reason,
            }
            self._spent_usd = 0.0
            self._unpriced_count = 0
            self._invalid_cost_count = 0
            self._per_provider = {}
            self._unpriced_by_provider = {}
            self._month_start = datetime.now().strftime("%Y-%m")
            self._last_reset = record
            self._save()
            return record

    # ── surfaces ─────────────────────────────────────────────────────

    def snapshot(self) -> dict:
        """The number and everything needed to judge whether to trust it."""
        with self._lock:
            return {
                "spent_usd": self._spent_usd,
                "unpriced_count": self._unpriced_count,
                "invalid_cost_count": self._invalid_cost_count,
                "per_provider": dict(self._per_provider),
                "unpriced_by_provider": dict(self._unpriced_by_provider),
                "month_start": self._month_start,
                "monthly_limit_usd": self._limit_usd,
                "state_unreadable": bool(self._unreadable_reason),
                "unreadable_reason": self._unreadable_reason,
                "last_reset": self._last_reset,
            }

    @property
    def unpriced_count(self) -> int:
        with self._lock:
            return self._unpriced_count

    @property
    def limit_usd(self) -> float:
        with self._lock:
            return self._limit_usd

    @property
    def spent_usd(self) -> float:
        with self._lock:
            return self._spent_usd

    @property
    def per_provider(self) -> dict[str, float]:
        with self._lock:
            return dict(self._per_provider)

    @property
    def state_unreadable(self) -> bool:
        with self._lock:
            return bool(self._unreadable_reason)

    # ── state ────────────────────────────────────────────────────────

    def _ensure_month_reset(self) -> None:
        current = datetime.now().strftime("%Y-%m")
        if current != self._month_start:
            self._spent_usd = 0.0
            self._unpriced_count = 0
            self._invalid_cost_count = 0
            self._per_provider = {}
            self._unpriced_by_provider = {}
            self._month_start = current

    def _read_state(self) -> tuple[dict | None, str]:
        """``(data, unreadable_reason)``. Absent file → ``(None, "")``."""
        p = self._state_dir / _STATE_FILE
        try:
            raw = p.read_text(encoding="utf-8")
        except FileNotFoundError:
            return None, ""
        except OSError as exc:
            return None, f"cannot read {_STATE_FILE}: {type(exc).__name__}"
        try:
            data = json.loads(raw)
        except (json.JSONDecodeError, UnicodeDecodeError):
            return None, f"{_STATE_FILE} is not valid JSON"
        if not isinstance(data, dict):
            return None, f"{_STATE_FILE} is not a JSON object"
        return data, ""

    def _refresh(self) -> None:
        """Re-read persisted state: the cap (so it is settable while running),
        the counters (so an out-of-process reset is seen), and the one-shot
        ``reset_requested`` flag."""
        data, bad = self._read_state()
        if bad:
            self._unreadable_reason = bad
            return
        if data is None:  # absent → fresh install, legitimately empty
            self._unreadable_reason = ""
            return

        spent = _finite(data.get("spent_usd", 0.0))
        if spent is None or spent < 0:
            self._unreadable_reason = (
                f"{_STATE_FILE} spent_usd is not a finite, non-negative number "
                f"({data.get('spent_usd')!r})"
            )
            return
        limit = _finite(data.get("monthly_limit_usd", self._limit_usd))
        if limit is None or limit < 0:
            self._unreadable_reason = (
                f"{_STATE_FILE} monthly_limit_usd is not a finite, non-negative "
                f"number ({data.get('monthly_limit_usd')!r})"
            )
            return

        self._unreadable_reason = ""
        self._spent_usd = spent
        self._limit_usd = limit
        self._month_start = str(data.get("month_start", ""))
        try:
            self._unpriced_count = max(0, int(data.get("unpriced_count", 0)))
            self._invalid_cost_count = max(0, int(data.get("invalid_cost_count", 0)))
        except (TypeError, ValueError):
            self._unpriced_count = 0
            self._invalid_cost_count = 0
        self._per_provider = _coerce_money_map(data.get("per_provider"))
        self._unpriced_by_provider = _coerce_count_map(data.get("unpriced_by_provider"))
        if isinstance(data.get("last_reset"), dict):
            self._last_reset = data["last_reset"]

        if data.get("reset_requested"):
            # One-shot, disk-triggered: lets the operator clear a corrupt counter
            # on a RUNNING gateway. _save() below drops the flag.
            self.reset_month(
                reason=str(data.get("reset_reason") or "reset_requested via spend.json")
            )

    def _save(self) -> None:
        d = self._state_dir
        d.mkdir(parents=True, exist_ok=True)
        p = d / _STATE_FILE
        payload = {
            "spent_usd": self._spent_usd,
            "unpriced_count": self._unpriced_count,
            "invalid_cost_count": self._invalid_cost_count,
            "per_provider": self._per_provider,
            "unpriced_by_provider": self._unpriced_by_provider,
            "month_start": self._month_start,
            "monthly_limit_usd": self._limit_usd,
        }
        if self._last_reset is not None:
            payload["last_reset"] = self._last_reset
        tmp = p.with_name(p.name + ".tmp")
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, p)


def _coerce_money_map(value) -> dict[str, float]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, float] = {}
    for k, v in value.items():
        f = _finite(v)
        if f is not None and f >= 0:
            out[str(k)] = f
    return out


def _coerce_count_map(value) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    out: dict[str, int] = {}
    for k, v in value.items():
        try:
            n = int(v)
        except (TypeError, ValueError):
            continue
        if n >= 0:
            out[str(k)] = n
    return out
