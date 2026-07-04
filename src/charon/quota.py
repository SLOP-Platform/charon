"""Proactive per-provider sliding-window quota tracker.

Tracks RPM/TPM (60s) and RPD/TPD (86400s) windows per provider using
stdlib collections.deque + time.monotonic.  When limits are configured
this module can predict a 429 BEFORE the request is sent — the router
can skip the provider, avoiding a wasted round-trip, latency, and
failover thrash.

All operations are thread-safe (threading.Lock).  No network, no
external deps.  Config-driven with default-off/advisory semantics:
a provider with no configured limits is never skipped, though usage
is still recorded so counters remain meaningful.
"""
from __future__ import annotations

import time
from collections import deque
from collections.abc import Callable
from threading import Lock
from typing import cast

# The public API keys on the provider string.  A future ticket may widen
# the key to (provider, model) — the internal data structures are already
# dict-of-provider and a follow-up would add per-model deques under each.

_WINDOW_RPM = 60       # seconds
_WINDOW_TPM = 60
_WINDOW_RPD = 86400    # 24 hours
_WINDOW_TPD = 86400

_DEFAULT_LIMITS: dict[str, int | None] = {
    "rpm": None,
    "tpm": None,
    "rpd": None,
    "tpd": None,
}

# Union type for the two deque kinds used internally.
_TSDQ = deque[float]
_TTDQ = deque[tuple[float, int]]


def _evict_deque(dq: _TSDQ, window: float, now: float) -> None:
    """Remove timestamps older than ``now - window`` from the left."""
    cutoff = now - window
    while dq and dq[0] < cutoff:
        dq.popleft()


def _evict_token_deque(dq: _TTDQ, window: float, now: float) -> None:
    """Remove (timestamp, tokens) entries older than ``now - window``."""
    cutoff = now - window
    while dq and dq[0][0] < cutoff:
        dq.popleft()


class QuotaTracker:
    """Per-provider sliding-window quota tracker.

    Usage::

        tracker = QuotaTracker(limits={"openai": {"rpm": 500}})
        if not tracker.should_skip("openai", est_tokens=200):
            # send request ...
            tracker.record("openai", tokens=actual)
    """

    def __init__(
        self,
        limits: dict[str, dict[str, int]] | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._limits: dict[str, dict[str, int | None]] = {}
        if limits:
            for provider, cfg in limits.items():
                merged = dict(_DEFAULT_LIMITS)
                merged.update(cfg)
                self._limits[provider] = merged

        self._lock = Lock()
        self._now = now

        self._req_rpm: dict[str, _TSDQ] = {}
        self._req_rpd: dict[str, _TSDQ] = {}
        self._tok_tpm: dict[str, _TTDQ] = {}
        self._tok_tpd: dict[str, _TTDQ] = {}

        self._counters: dict[str, int] = {}

    # -- public API ---------------------------------------------------------

    def should_skip(self, provider: str, est_tokens: int = 0) -> bool:
        """Return True iff sending ~*est_tokens* would exceed any configured limit.

        A provider with no configured limits returns False for every window,
        even after many ``record`` calls (the tracker still records usage).
        """
        limits = self._limits.get(provider)
        if limits is None:
            return False

        now = self._now()
        with self._lock:
            self._ensure_deques(provider)

            if limits["rpm"] is not None:
                _evict_deque(self._req_rpm[provider], _WINDOW_RPM, now)
                if len(self._req_rpm[provider]) + 1 > cast(int, limits["rpm"]):
                    self._counters["skip_rpm"] = (
                        self._counters.get("skip_rpm", 0) + 1
                    )
                    return True

            if limits["tpm"] is not None and est_tokens > 0:
                _evict_token_deque(self._tok_tpm[provider], _WINDOW_TPM, now)
                cur_tpm = sum(t for _, t in self._tok_tpm[provider])
                if cur_tpm + est_tokens > cast(int, limits["tpm"]):
                    self._counters["skip_tpm"] = (
                        self._counters.get("skip_tpm", 0) + 1
                    )
                    return True

            if limits["rpd"] is not None:
                _evict_deque(self._req_rpd[provider], _WINDOW_RPD, now)
                if len(self._req_rpd[provider]) + 1 > cast(int, limits["rpd"]):
                    self._counters["skip_rpd"] = (
                        self._counters.get("skip_rpd", 0) + 1
                    )
                    return True

            if limits["tpd"] is not None and est_tokens > 0:
                _evict_token_deque(self._tok_tpd[provider], _WINDOW_TPD, now)
                cur_tpd = sum(t for _, t in self._tok_tpd[provider])
                if cur_tpd + est_tokens > cast(int, limits["tpd"]):
                    self._counters["skip_tpd"] = (
                        self._counters.get("skip_tpd", 0) + 1
                    )
                    return True

        return False

    def record(self, provider: str, tokens: int) -> None:
        """Record one completed request against all windows."""
        now = self._now()
        with self._lock:
            self._ensure_deques(provider)
            self._req_rpm[provider].append(now)
            self._req_rpd[provider].append(now)
            if tokens > 0:
                self._tok_tpm[provider].append((now, tokens))
                self._tok_tpd[provider].append((now, tokens))

    def get_wait_time(self, provider: str, est_tokens: int = 0) -> float:
        """Return the shortest seconds until ``should_skip`` would flip back to False.

        Returns 0.0 if the provider is not currently blocked.  The caller
        can use this to schedule a retry at ``time.monotonic() + wait``.
        """
        limits = self._limits.get(provider)
        if limits is None:
            return 0.0

        now = self._now()
        wait: float = float("inf")
        with self._lock:
            self._ensure_deques(provider)

            if limits["rpm"] is not None:
                _evict_deque(self._req_rpm[provider], _WINDOW_RPM, now)
                dq: _TSDQ = self._req_rpm[provider]
                rpm_limit = cast(int, limits["rpm"])
                if rpm_limit == 0 or len(dq) >= rpm_limit:
                    if rpm_limit == 0:
                        return float("inf")
                    wait = min(wait, dq[0] + _WINDOW_RPM - now)

            if limits["tpm"] is not None and est_tokens > 0:
                _evict_token_deque(self._tok_tpm[provider], _WINDOW_TPM, now)
                tdq: _TTDQ = self._tok_tpm[provider]
                cur = sum(t for _, t in tdq)
                tpm_limit = cast(int, limits["tpm"])
                if cur + est_tokens > tpm_limit:
                    need = cur + est_tokens - tpm_limit
                    for ts, tok in tdq:
                        need -= tok
                        if need <= 0:
                            wait = min(wait, ts + _WINDOW_TPM - now)
                            break

            if limits["rpd"] is not None:
                _evict_deque(self._req_rpd[provider], _WINDOW_RPD, now)
                dq = self._req_rpd[provider]
                rpd_limit = cast(int, limits["rpd"])
                if rpd_limit == 0 or len(dq) >= rpd_limit:
                    if rpd_limit == 0:
                        return float("inf")
                    wait = min(wait, dq[0] + _WINDOW_RPD - now)

            if limits["tpd"] is not None and est_tokens > 0:
                _evict_token_deque(self._tok_tpd[provider], _WINDOW_TPD, now)
                tdq = self._tok_tpd[provider]
                cur = sum(t for _, t in tdq)
                tpd_limit = cast(int, limits["tpd"])
                if cur + est_tokens > tpd_limit:
                    need = cur + est_tokens - tpd_limit
                    for ts, tok in tdq:
                        need -= tok
                        if need <= 0:
                            wait = min(wait, ts + _WINDOW_TPD - now)
                            break

        return 0.0 if wait == float("inf") else max(wait, 0.0)

    def counters(self) -> dict[str, int]:
        """Return a read-only snapshot of per-reason skip counters."""
        with self._lock:
            return dict(self._counters)

    # -- internals ----------------------------------------------------------

    def _ensure_deques(self, provider: str) -> None:
        if provider not in self._req_rpm:
            self._req_rpm[provider] = deque()
            self._req_rpd[provider] = deque()
            self._tok_tpm[provider] = deque()
            self._tok_tpd[provider] = deque()
