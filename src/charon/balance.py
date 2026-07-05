"""Balance tracker — DRAIN a provider's prepaid balance before moving off it.

Two balance sources:
1. **Poll adapters** — providers that expose a balance API: DeepSeek, OpenRouter,
   NanoGPT. A small per-provider adapter returns remaining USD (or None if
   unsupported).
2. **Spend-tracking** — dashboard-only providers (opencode-zen, Together,
   NeuralWatt): an operator-configured starting balance, decremented by
   ``record_spend()`` using real ``cost_usd``.

All operations are thread-safe (``threading.Lock``).  Config-driven, OFF/inert
unless a provider is explicitly configured with a balance.  Stdlib only, no
network, no external deps.  Per-reason counters like ``quota.py``.

Public API:
  ``remaining(provider) -> float|None``
  ``record_spend(provider, usd)``
  ``should_drain(provider) -> bool``   (positive balance -> route-first)
  ``is_drained(provider, floor=0.0) -> bool``  (approx 0 -> demote/skip)
"""
from __future__ import annotations

import json
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

# ---------------------------------------------------------------------------
# Balance poll adapters — pure functions that take (base_url, api_key) and
# return remaining USD (float) or None when the provider doesn't expose one.
# ---------------------------------------------------------------------------


def _poll_deepseek(base_url: str, api_key: str, timeout: float) -> float | None:
    """DeepSeek ``GET /user/balance`` → return remaining USD."""
    import urllib.request

    url = base_url.rstrip("/") + "/user/balance"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")
    req.add_header("Authorization", "Bearer " + api_key)
    try:
        resp = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        ).open(req, timeout=timeout)
        data = json.loads(resp.read(100_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    bal = data.get("balance")
    if not isinstance(bal, dict):
        return None
    usd = bal.get("total_remaining") or bal.get("total_balance")
    if usd is not None:
        try:
            return float(usd)
        except (ValueError, TypeError):
            return None
    return None


def _poll_openrouter(base_url: str, api_key: str, timeout: float) -> float | None:
    """OpenRouter ``GET /api/v1/credits`` → data.credits (float USD)."""
    import urllib.request

    url = base_url.rstrip("/") + "/credits"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", "charon-proxy/0.1")
    req.add_header("Authorization", "Bearer " + api_key)
    try:
        resp = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        ).open(req, timeout=timeout)
        data = json.loads(resp.read(100_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if not isinstance(data, dict):
        return None
    data_block = data.get("data")
    if not isinstance(data_block, dict):
        return None
    credits = data_block.get("credits")
    if credits is not None:
        try:
            return float(credits)
        except (ValueError, TypeError):
            return None
    return None


def _poll_nanogpt(base_url: str, api_key: str, timeout: float) -> float | None:
    """NanoGPT ``POST /api/check-balance`` → balance (float USD)."""
    import urllib.request

    url = base_url.rstrip("/") + "/api/check-balance"
    body = json.dumps({}).encode()
    req = urllib.request.Request(url, data=body, method="POST")
    req.add_header("User-Agent", "charon-proxy/0.1")
    req.add_header("Content-Type", "application/json")
    req.add_header("Authorization", "Bearer " + api_key)
    try:
        resp = urllib.request.build_opener(
            urllib.request.HTTPRedirectHandler
        ).open(req, timeout=timeout)
        data = json.loads(resp.read(100_000).decode("utf-8", "replace"))
    except Exception:  # noqa: BLE001
        return None
    if isinstance(data, dict):
        bal = data.get("balance")
        if bal is not None:
            try:
                return float(bal)
            except (ValueError, TypeError):
                return None
    return None


_POLL_ADAPTERS: dict[str, Callable[..., float | None]] = {
    "deepseek": _poll_deepseek,
    "openrouter": _poll_openrouter,
    "nanogpt": _poll_nanogpt,
}


# ---------------------------------------------------------------------------
# Balance tracker — thread-safe, config-driven
# ---------------------------------------------------------------------------


class BalanceTracker:
    """Thread-safe per-provider balance tracker.

    Two modes:
    * **Poll** — configured with ``base_url`` + ``api_key``; periodically calls
      the provider's balance endpoint to get real remaining USD.
    * **Fixed** — operator-configured starting balance (e.g. dashboard
      providers); decremented by ``record_spend()``.

    A provider not present in ``config`` is always inert: ``remaining`` returns
    None, ``should_drain`` returns False, and ``record_spend`` is a no-op.

    Usage::

        bt = BalanceTracker(config={
            "deepseek": {"mode": "poll", "base_url": "...", "api_key": "sk-..."},
            "opencode-zen": {"mode": "fixed", "starting_usd": 10.00},
        })
        bt.should_drain("deepseek")   # True if positive balance
        bt.record_spend("opencode-zen", 0.0015)
        bt.is_drained("opencode-zen")  # True if ≈ 0
    """

    def __init__(
        self,
        config: dict[str, dict[str, Any]] | None = None,
        now: Callable[[], float] = time.monotonic,
    ) -> None:
        self._config: dict[str, dict[str, Any]] = dict(config or {})
        self._lock = Lock()
        self._now = now

        self._fixed_balances: dict[str, float] = {}
        self._counters: dict[str, int] = {}

        for provider, cfg in self._config.items():
            if cfg.get("mode") == "fixed":
                start = cfg.get("starting_usd", 0.0)
                try:
                    self._fixed_balances[provider] = float(start)
                except (ValueError, TypeError):
                    self._fixed_balances[provider] = 0.0

    # -- public API ---------------------------------------------------------

    def remaining(self, provider: str) -> float | None:
        """Current remaining USD for *provider*, or None if not configured.

        Poll providers return None when unreachable (don't cache stale).
        Fixed providers return the tracked balance (non-negative).
        """
        cfg = self._config.get(provider)
        if cfg is None:
            return None

        mode = cfg.get("mode")
        if mode == "fixed":
            with self._lock:
                return self._fixed_balances.get(provider, 0.0)

        if mode == "poll":
            base_url = cfg.get("base_url")
            api_key = cfg.get("api_key")
            timeout = float(cfg.get("timeout", 20.0))
            if not base_url or not api_key:
                return None
            adapter = _POLL_ADAPTERS.get(provider)
            if adapter is None:
                return None
            try:
                return adapter(str(base_url), str(api_key), timeout)
            except Exception:  # noqa: BLE001
                self._counters["poll_error"] = (
                    self._counters.get("poll_error", 0) + 1
                )
                return None

        return None

    def record_spend(self, provider: str, usd: float) -> None:
        """Decrement a fixed provider's tracked balance by *usd*.

        For poll providers or unconfigured providers this is a no-op (their
        balance is authoritative — we don't double-count).
        """
        usd = float(usd)
        if usd <= 0.0:
            return  # negative/zero spend is ignored
        cfg = self._config.get(provider)
        if cfg is None or cfg.get("mode") != "fixed":
            return
        with self._lock:
            cur = self._fixed_balances.get(provider, 0.0)
            self._fixed_balances[provider] = max(cur - usd, 0.0)

    def should_drain(self, provider: str) -> bool:
        """True if *provider* has a positive remaining balance → route-first.

        Providers not configured for balance tracking are never "to drain"
        (they're just neutral).
        """
        rem = self.remaining(provider)
        if rem is None:
            return False
        return rem > 0.0

    def is_drained(self, provider: str, floor: float = 0.0) -> bool:
        """True if *provider*'s remaining balance is at or near *floor*.

        Used to decide: stop routing (skip/demote) when balance is exhausted.
        Unconfigured providers are considered "not drained" (they're neutral).
        """
        rem = self.remaining(provider)
        if rem is None:
            # Not configured — not tracking, so never "drained".
            return False
        return rem <= floor

    def force_poll(self, provider: str) -> float | None:
        """Synchronous poll for a poll-configured provider, regardless of cache.

        Returns float USD or None (unreachable / unsupported).
        This is the operator-triggerable refresh path.
        """
        cfg = self._config.get(provider)
        if cfg is None or cfg.get("mode") != "poll":
            return None
        base_url = cfg.get("base_url")
        api_key = cfg.get("api_key")
        timeout = float(cfg.get("timeout", 20.0))
        if not base_url or not api_key:
            return None
        adapter = _POLL_ADAPTERS.get(provider)
        if adapter is None:
            return None
        try:
            result = adapter(str(base_url), str(api_key), timeout)
        except Exception:  # noqa: BLE001
            with self._lock:
                self._counters["poll_error"] = (
                    self._counters.get("poll_error", 0) + 1
                )
            return None
        if result is not None:
            with self._lock:
                self._counters["poll_success"] = (
                    self._counters.get("poll_success", 0) + 1
                )
        return result

    def configure(
        self,
        provider: str,
        mode: str,
        starting_usd: float | None = None,
        base_url: str | None = None,
        api_key: str | None = None,
    ) -> None:
        """Add or update a provider's balance config at runtime."""
        cfg: dict[str, Any] = {"mode": mode}
        if mode == "fixed" and starting_usd is not None:
            cfg["starting_usd"] = float(starting_usd)
        if mode == "poll":
            if base_url is not None:
                cfg["base_url"] = base_url
            if api_key is not None:
                cfg["api_key"] = api_key
        with self._lock:
            self._config[provider] = cfg
            if mode == "fixed":
                start = cfg.get("starting_usd", 0.0)
                self._fixed_balances[provider] = float(start)

    def counters(self) -> dict[str, int]:
        """Return a read-only snapshot of per-reason counters."""
        with self._lock:
            return dict(self._counters)
