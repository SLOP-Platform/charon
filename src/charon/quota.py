"""Proactive per-provider free-tier quota engine.

A complete free-tier enforcement engine: rolling sliding windows (RPM/TPM,
RPD/TPD, RWK/TWK) AND calendar-anchored daily/weekly/monthly caps, with
usage that survives a gateway restart.

Window types
------------
* **Rolling** (default — preserves pre-existing behavior of the original
  QuotaTracker): a sliding window of length ``N`` seconds
  (``rpm``/``tpm`` = 60s, ``rpd``/``tpd`` = 86400s, ``rwk``/``twk`` = 604800s).
  Entries older than ``now - N`` are evicted; the count of remaining
  entries is compared to the limit.
* **Calendar**: a single scalar counter per (provider, window) that resets
  at a fixed UTC anchor — UTC midnight for daily, next Monday 00:00 UTC
  for weekly, first-of-month 00:00 UTC for monthly. The anchor is
  recomputed on every ``should_skip``/``record`` so a boundary crossing
  immediately frees the limit; no drift between the boundary clock and
  the caller's monotonic clock.

Per-limit config
----------------
The limits dict maps provider → per-window config. A window key may be a
plain int (rolling, default) or a dict ``{"limit": int, "reset": "rolling"|"calendar"}``.
A limit declared as a plain int behaves EXACTLY as the legacy config did
(``{"rpm": 500}`` → 60s rolling) — back-compat is the default.

Supported keys (rolling default, all optional):
  ``rpm``/``rpd``/``rwk``/``rmo`` — request-count limits
  ``tpm``/``tpd``/``twk``/``tmo`` — token-count limits

``rmo``/``tmo`` are calendar-anchored by definition (a month is a
calendar concept, not a rolling-30-days window). ``rpd``/``tpd`` and
``rwk``/``twk`` default to rolling but can be opted into ``reset="calendar"``
for UTC-midnight / Monday-midnight semantics. A ``reset`` field on an
individual limit wins over the default.

Persistence
-----------
When constructed with a ``state_dir``, usage counts (both calendar
scalars AND rolling deques, trimmed to the window) are persisted to
``<state_dir>/quota_usage.json``. The atomic-write discipline is the
exact one from ``balance.py`` (unique tmp = pid+tid+uuid, ``os.replace``,
``_save_lock``, best-effort ``OSError`` swallow) so a partial write can
never be observed by a re-loader. Missing/corrupt file degrades to
empty usage (fail-open on load only — a never-saved state MUST not
prevent the gateway from starting).

API
---
The public surface is intentionally small and stable: ``should_skip``,
``record``, ``get_wait_time``, ``counters``. Stdlib-only, synchronous
(quota is called from the router's request path — must not block on
async I/O).
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections import deque
from collections.abc import Callable
from dataclasses import dataclass
from pathlib import Path
from threading import Lock
from typing import Any

# Public surface keys (per-provider). The internal data structures are
# dict-of-provider; a follow-up ticket may widen to per-(provider, model)
# — the deques here are already keyed by provider.

_WINDOW_RPM = 60
_WINDOW_TPM = 60
_WINDOW_RPD = 86400
_WINDOW_TPD = 86400
_WINDOW_RWK = 604800       # 7 days
_WINDOW_TWK = 604800

# Calendar reset anchors (seconds since epoch → next boundary epoch).
_SECONDS_PER_DAY = 86400
_SECONDS_PER_WEEK = 604800

# State file — same convention as balance.py's _PARK_STATE_FILE.
_QUOTA_STATE_FILE = "quota_usage.json"

# Rolling-window keys (legacy, default) — each maps to a deque type.
# Calendar-window keys each map to a CalendarCounter (scalar + period_start).
# ``rpd``/``tpd`` and ``rwk``/``twk`` can be either, controlled per-limit
# by the ``reset`` field; ``rmo``/``tmo`` are calendar-only.
_ROLLING_REQ_DEFAULTS: dict[str, int] = {
    "rpm": _WINDOW_RPM,
    "rpd": _WINDOW_RPD,
    "rwk": _WINDOW_RWK,
}
_ROLLING_TOK_DEFAULTS: dict[str, int] = {
    "tpm": _WINDOW_TPM,
    "tpd": _WINDOW_TPD,
    "twk": _WINDOW_TWK,
}
_CALENDAR_KEYS: frozenset[str] = frozenset(
    {"rpd", "tpd", "rwk", "twk", "rmo", "tmo"})

# Union type for the two deque kinds used internally.
_TSDQ = deque[float]
_TTDQ = deque[tuple[float, int]]


@dataclass
class _Calendar:
    period_start: float  # epoch of the START of the current calendar period
    count: float  # request count (int) or token count (int)


# ---------------------------------------------------------------------------
# Calendar boundary math (UTC-anchored; stdlib datetime.timezone.utc only).
# ---------------------------------------------------------------------------


def _utc_midnight_epoch(t: float) -> float:
    """Epoch seconds at the most recent UTC midnight (start of the day containing *t*)."""
    return (float(t) // _SECONDS_PER_DAY) * _SECONDS_PER_DAY


def _next_utc_midnight(t: float) -> float:
    """Epoch seconds of the NEXT UTC midnight strictly after *t*."""
    return _utc_midnight_epoch(t) + _SECONDS_PER_DAY


def _week_start_epoch(t: float) -> float:
    """Epoch seconds at the most recent Monday 00:00 UTC at or before *t*."""
    import datetime as _dt
    midnight = _utc_midnight_epoch(t)
    weekday = _dt.datetime.fromtimestamp(midnight, tz=_dt.UTC).weekday()
    return midnight - weekday * _SECONDS_PER_DAY


def _next_week_start(t: float) -> float:
    return _week_start_epoch(t) + _SECONDS_PER_WEEK


def _month_start_epoch(t: float) -> float:
    """Epoch seconds at the first instant of the calendar month containing *t* (UTC)."""
    import datetime as _dt
    dt = _dt.datetime.fromtimestamp(float(t), tz=_dt.UTC)
    month_start = _dt.datetime(dt.year, dt.month, 1, tzinfo=_dt.UTC)
    return month_start.timestamp()


def _next_month_start(t: float) -> float:
    import datetime as _dt
    dt = _dt.datetime.fromtimestamp(float(t), tz=_dt.UTC)
    if dt.month == 12:
        nxt = _dt.datetime(dt.year + 1, 1, 1, tzinfo=_dt.UTC)
    else:
        nxt = _dt.datetime(dt.year, dt.month + 1, 1, tzinfo=_dt.UTC)
    return nxt.timestamp()


def _calendar_period_start(key: str, t: float) -> float:
    if key in ("rpd", "tpd"):
        return _utc_midnight_epoch(t)
    if key in ("rwk", "twk"):
        return _week_start_epoch(t)
    if key in ("rmo", "tmo"):
        return _month_start_epoch(t)
    raise KeyError(key)


def _calendar_next_boundary(key: str, t: float) -> float:
    if key in ("rpd", "tpd"):
        return _next_utc_midnight(t)
    if key in ("rwk", "twk"):
        return _next_week_start(t)
    if key in ("rmo", "tmo"):
        return _next_month_start(t)
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Limit normalization: legacy ``{"rpm": 500}`` → (500, "rolling")
# ---------------------------------------------------------------------------


def _normalize_limit(value: Any) -> tuple[int, str] | None:
    """Return ``(limit, reset)`` for one config value, or None if disabled.

    Accepts:
      * ``int`` (or anything int-coercible) → ``(int, "rolling")`` (legacy).
      * ``None`` → None (limit not configured).
      * ``{"limit": int, "reset": "rolling"|"calendar"}`` → ``(int, reset)``.

    Anything else → None (treated as unset; the provider just won't be
    throttled on that window — the same effect as omitting the key).
    """
    if value is None:
        return None
    if isinstance(value, bool):  # bool is an int subclass — reject silently
        return None
    if isinstance(value, int):
        return int(value), "rolling"
    if isinstance(value, dict):
        lim = value.get("limit")
        reset = value.get("reset", "rolling")
        if not isinstance(lim, int) or isinstance(lim, bool):
            return None
        if reset not in ("rolling", "calendar"):
            return None
        return int(lim), str(reset)
    try:
        return int(value), "rolling"  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return None


def _window_defaults(key: str) -> tuple[float, bool]:
    """Return ``(window_seconds, is_token)`` for *key*. Raises KeyError if
    the key is not a known window name. ``window_seconds`` is unused for
    calendar-only keys (``rmo``/``tmo``) and returned as 0.0."""
    if key in _ROLLING_REQ_DEFAULTS:
        return float(_ROLLING_REQ_DEFAULTS[key]), False
    if key in _ROLLING_TOK_DEFAULTS:
        return float(_ROLLING_TOK_DEFAULTS[key]), True
    if key == "rmo":
        return 0.0, False
    if key == "tmo":
        return 0.0, True
    raise KeyError(key)


# ---------------------------------------------------------------------------
# Per-provider state
# ---------------------------------------------------------------------------


class _ProviderState:
    """All state for one provider — rolling deques + calendar counters.

    Lives inside the tracker under ``self._lock``. Never escapes."""

    __slots__ = ("req_rolling", "tok_rolling", "calendar")

    def __init__(self) -> None:
        # window_key → deque ([float] for request, [(float, int)] for token)
        self.req_rolling: dict[str, _TSDQ] = {}
        self.tok_rolling: dict[str, _TTDQ] = {}
        # window_key → _Calendar
        self.calendar: dict[str, _Calendar] = {}

    def snapshot(self) -> dict[str, Any]:
        """Return a JSON-serializable snapshot for persistence."""
        rolling_req = {k: list(dq) for k, dq in self.req_rolling.items()}
        rolling_tok = {
            k: [[ts, tok] for ts, tok in dq]
            for k, dq in self.tok_rolling.items()
        }
        rolling: dict[str, Any] = {**rolling_req, **rolling_tok}
        calendar: dict[str, Any] = {
            k: {"period_start": c.period_start, "count": c.count}
            for k, c in self.calendar.items()
        }
        return {"rolling": rolling, "calendar": calendar}

    @classmethod
    def from_snapshot(cls, snap: dict[str, Any]) -> _ProviderState:
        st = cls()
        rolling = snap.get("rolling")
        if isinstance(rolling, dict):
            for k, vals in rolling.items():
                if k in _ROLLING_REQ_DEFAULTS and isinstance(vals, list):
                    dq: _TSDQ = deque(float(x) for x in vals)
                    st.req_rolling[k] = dq
                elif k in _ROLLING_TOK_DEFAULTS and isinstance(vals, list):
                    dq2: _TTDQ = deque(
                        (float(ts), int(tok)) for ts, tok in vals
                    )
                    st.tok_rolling[k] = dq2
        cal = snap.get("calendar")
        if isinstance(cal, dict):
            for k, c in cal.items():
                if k not in _CALENDAR_KEYS or not isinstance(c, dict):
                    continue
                ps = c.get("period_start")
                cnt = c.get("count")
                if not isinstance(ps, (int, float)) or not isinstance(cnt, (int, float)):
                    continue
                st.calendar[k] = _Calendar(period_start=float(ps), count=float(cnt))
        return st


# ---------------------------------------------------------------------------
# QuotaTracker
# ---------------------------------------------------------------------------


class QuotaTracker:
    """Per-provider free-tier quota engine.

    Usage::

        tracker = QuotaTracker(
            limits={"openai": {"rpm": 500, "tpm": 200_000}},
            state_dir="/var/lib/charon",   # optional; persist across restarts
        )
        if not tracker.should_skip("openai", est_tokens=200):
            # send request ...
            tracker.record("openai", tokens=actual)

    For monthly caps (e.g. mistral ~1B tokens/month)::

        tracker = QuotaTracker(
            limits={"mistral": {"tmo": 1_000_000_000}},   # calendar monthly
            state_dir="/var/lib/charon",
        )
    """

    def __init__(
        self,
        limits: dict[str, dict[str, Any]] | None = None,
        now: Callable[[], float] = time.monotonic,
        state_dir: str | Path | None = None,
    ) -> None:
        # Normalize the per-provider config first. Legacy ``{"rpm": 500}``
        # maps to (500, "rolling") — back-compat is the default.
        self._active: dict[str, dict[str, tuple[int, str]]] = {}
        if limits:
            for provider, cfg in limits.items():
                if not isinstance(cfg, dict):
                    continue
                a: dict[str, tuple[int, str]] = {}
                for k, v in cfg.items():
                    try:
                        _window_defaults(k)
                    except KeyError:
                        continue
                    norm = _normalize_limit(v)
                    if norm is not None:
                        # rmo/tmo are calendar-only by definition; force it.
                        if k in ("rmo", "tmo"):
                            a[k] = (norm[0], "calendar")
                        else:
                            a[k] = norm
                if a:
                    self._active[provider] = a

        self._lock = Lock()
        self._now = now
        self._state_dir: Path | None = (
            Path(state_dir) if state_dir is not None else None
        )

        # Per-provider state — lazily populated on first should_skip/record.
        self._state: dict[str, _ProviderState] = {}
        # Monotonic clock doesn't map to UTC; we need a separate UTC clock
        # for calendar boundary math. Default to time.time (configurable
        # via the ``set_utc_now`` injection point in tests).
        self._utc_now: Callable[[], float] = time.time

        # Per-reason skip counters (kept under lock).
        self._counters: dict[str, int] = {}
        # I/O lock for persistence — see balance.py for why a dedicated
        # I/O lock (NOT a re-lock of ``self._lock``) is correct here.
        self._save_lock = Lock()

        if self._state_dir is not None:
            self._load_state()

    # -- injection points (tests) ----------------------------------------

    def set_utc_now(self, fn: Callable[[], float]) -> None:
        """Inject the UTC clock used for calendar-boundary math.

        Tests use a FakeClock (separate from the ``now=`` monotonic clock)
        so that boundary crossings can be simulated deterministically
        without sleeping.
        """
        self._utc_now = fn

    # -- public API -------------------------------------------------------

    def should_skip(self, provider: str, est_tokens: int = 0) -> bool:
        """Return True iff sending ~*est_tokens* would exceed any configured limit.

        A provider with no configured limits returns False for every window,
        even after many ``record`` calls (the tracker still records usage).
        """
        active = self._active.get(provider)
        if not active:
            return False

        now_mono = self._now()
        now_utc = self._utc_now()
        with self._lock:
            st = self._state.setdefault(provider, _ProviderState())
            for key, (limit, reset) in active.items():
                try:
                    window_seconds, is_token = _window_defaults(key)
                except KeyError:
                    continue
                if reset == "rolling":
                    if is_token:
                        t_dq: _TTDQ = st.tok_rolling.setdefault(key, deque())
                        _evict_token(t_dq, window_seconds, now_mono)
                        cur = sum(t for _, t in t_dq)
                        if est_tokens > 0 and cur + est_tokens > limit:
                            self._bump("skip_" + key)
                            return True
                    else:
                        r_dq: _TSDQ = st.req_rolling.setdefault(key, deque())
                        _evict_req(r_dq, window_seconds, now_mono)
                        if len(r_dq) + 1 > limit:
                            self._bump("skip_" + key)
                            return True
                else:  # calendar
                    cal = st.calendar.get(key)
                    if cal is None or _is_calendar_rolled(cal, key, now_utc):
                        # First time, or period rolled: reset to 0 in new period.
                        cal = _Calendar(
                            period_start=_calendar_period_start(key, now_utc),
                            count=0,
                        )
                        st.calendar[key] = cal
                    if is_token:
                        if est_tokens > 0 and cal.count + est_tokens > limit:
                            self._bump("skip_" + key)
                            return True
                    else:
                        if cal.count + 1 > limit:
                            self._bump("skip_" + key)
                            return True
        return False

    def record(self, provider: str, tokens: int) -> None:
        """Record one completed request against all configured windows.

        Persists to ``<state_dir>/quota_usage.json`` when a state dir was
        configured (best-effort; OSError is swallowed — see ``balance.py``).
        """
        active = self._active.get(provider)
        if not active:
            return  # legacy behavior: providers without limits are inert

        now_mono = self._now()
        now_utc = self._utc_now()
        with self._lock:
            st = self._state.setdefault(provider, _ProviderState())
            for key, (_limit, reset) in active.items():
                try:
                    window_seconds, is_token = _window_defaults(key)
                except KeyError:
                    continue
                if reset == "rolling":
                    if is_token:
                        t_dq: _TTDQ = st.tok_rolling.setdefault(key, deque())
                        _evict_token(t_dq, window_seconds, now_mono)
                        if tokens > 0:
                            t_dq.append((now_mono, tokens))
                    else:
                        r_dq: _TSDQ = st.req_rolling.setdefault(key, deque())
                        _evict_req(r_dq, window_seconds, now_mono)
                        r_dq.append(now_mono)
                else:  # calendar
                    cal = st.calendar.get(key)
                    if cal is None or _is_calendar_rolled(cal, key, now_utc):
                        cal = _Calendar(
                            period_start=_calendar_period_start(key, now_utc),
                            count=0,
                        )
                        st.calendar[key] = cal
                    if is_token:
                        if tokens > 0:
                            cal.count += int(tokens)
                    else:
                        cal.count += 1
        # Persist outside the hot path's lock — but the I/O lock serializes
        # the snapshot+write+replace so concurrent record()s never interleave.
        if self._state_dir is not None:
            self._save_state()

    def get_wait_time(self, provider: str, est_tokens: int = 0) -> float:
        """Return the shortest seconds until ``should_skip`` would flip back to False.

        Returns 0.0 if the provider is not currently blocked.  For calendar
        limits the wait is the time until the next calendar boundary (UTC
        midnight / next Monday / 1st of next month); for rolling it's the
        time until the oldest in-window entry slides off.
        """
        active = self._active.get(provider)
        if not active:
            return 0.0

        now_mono = self._now()
        now_utc = self._utc_now()
        wait: float = float("inf")
        with self._lock:
            st = self._state.setdefault(provider, _ProviderState())
            for key, (limit, reset) in active.items():
                try:
                    window_seconds, is_token = _window_defaults(key)
                except KeyError:
                    continue
                if reset == "rolling":
                    if is_token:
                        t_dq: _TTDQ = st.tok_rolling.setdefault(key, deque())
                        _evict_token(t_dq, window_seconds, now_mono)
                        cur = sum(t for _, t in t_dq)
                        if est_tokens > 0 and cur + est_tokens > limit:
                            need = cur + est_tokens - limit
                            for ts, tok in t_dq:
                                need -= tok
                                if need <= 0:
                                    wait = min(wait, ts + window_seconds - now_mono)
                                    break
                    else:
                        r_dq: _TSDQ = st.req_rolling.setdefault(key, deque())
                        _evict_req(r_dq, window_seconds, now_mono)
                        if limit == 0 or len(r_dq) >= limit:
                            if limit == 0:
                                return float("inf")
                            wait = min(wait, r_dq[0] + window_seconds - now_mono)
                else:  # calendar
                    cal = st.calendar.get(key)
                    if cal is None or _is_calendar_rolled(cal, key, now_utc):
                        # Already rolled — wait is "now" (0).
                        wait = min(wait, 0.0)
                        continue
                    if is_token:
                        if est_tokens > 0 and cal.count + est_tokens > limit:
                            wait = min(wait, _calendar_next_boundary(key, now_utc) - now_utc)
                    else:
                        if cal.count + 1 > limit:
                            wait = min(wait, _calendar_next_boundary(key, now_utc) - now_utc)

        return 0.0 if wait == float("inf") else max(wait, 0.0)

    def counters(self) -> dict[str, int]:
        """Return a read-only snapshot of per-reason skip counters."""
        with self._lock:
            return dict(self._counters)

    # -- internals -------------------------------------------------------

    def _bump(self, name: str) -> None:
        self._counters[name] = self._counters.get(name, 0) + 1

    # -- persistence (best-effort, never raises) ------------------------

    def _load_state(self) -> None:
        """Load usage from disk. Missing/corrupt file → empty usage.

        Fail-open is deliberate: a fresh install has no state yet, and a
        partially-written file from a crash must not prevent the gateway
        from starting (a quota engine that refuses to start is worse than
        one that forgets the last few minutes of usage).
        """
        if self._state_dir is None:
            return
        p = self._state_dir / _QUOTA_STATE_FILE
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        provs = data.get("providers")
        if not isinstance(provs, dict):
            return
        with self._lock:
            for provider, snap in provs.items():
                if not isinstance(snap, dict):
                    continue
                self._state[str(provider)] = _ProviderState.from_snapshot(snap)

    def _save_state(self) -> None:
        """Atomic-write the current usage to ``quota_usage.json``.

        Mirrors ``balance.py``'s ``_save_parked`` discipline EXACTLY:
          * dedicated ``_save_lock`` so concurrent ``record()``s serialize
            their snapshot+write+replace (a stale snapshot can never win
            because the final ``os.replace`` reflects the snapshot taken
            inside this lock);
          * unique tmp = pid + thread-id + uuid4.hex so two callers never
            share a tmp path (the race that the b8e62d0 fix addressed);
          * best-effort ``OSError`` swallow — a disk hiccup MUST never
            propagate into the request path, only a counter increment.
        """
        if self._state_dir is None:
            return
        with self._save_lock:
            with self._lock:
                snap: dict[str, Any] = {
                    p: st.snapshot() for p, st in self._state.items()
                }
            d = self._state_dir
            p = d / _QUOTA_STATE_FILE
            tmp = p.with_name(
                f"{p.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
            try:
                d.mkdir(parents=True, exist_ok=True)
                tmp.write_text(
                    json.dumps({"providers": snap}, indent=2), encoding="utf-8")
                os.replace(tmp, p)
            except OSError:
                try:
                    tmp.unlink()
                except OSError:
                    pass
                with self._lock:
                    self._counters["quota_save_error"] = (
                        self._counters.get("quota_save_error", 0) + 1)


# ---------------------------------------------------------------------------
# Module-level helpers (kept module-private; tests may import them).
# ---------------------------------------------------------------------------


def _evict_req(dq: _TSDQ, window: float, now: float) -> None:
    """Remove timestamps older than ``now - window`` from the left."""
    cutoff = now - window
    while dq and dq[0] < cutoff:
        dq.popleft()


def _evict_token(dq: _TTDQ, window: float, now: float) -> None:
    """Remove (timestamp, tokens) entries older than ``now - window`` from the left."""
    cutoff = now - window
    while dq and dq[0][0] < cutoff:
        dq.popleft()


def _is_calendar_rolled(cal: _Calendar, key: str, now_utc: float) -> bool:
    """True iff *now_utc* has crossed the next calendar boundary since
    *cal.period_start* (i.e. the period for the stored count has ended)."""
    return now_utc >= _calendar_next_boundary(key, cal.period_start)
