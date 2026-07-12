"""Balance tracker — DRAIN a provider's prepaid balance before moving off it.

Two balance sources:
1. **Poll adapters** — providers that expose a balance API: DeepSeek, OpenRouter,
   NanoGPT. A small per-provider adapter returns remaining USD (or None if
   unsupported). TTL-cached (default 300s) to avoid hammering the balance API.
2. **Fixed / observer-metered** — class-3 drain-then-park providers configured
   with a ``starting_balance``; remaining = starting_balance − observer-metered
   spend (sum of per-(model,provider) costs from the gateway proxy's observer).
   No parallel per-provider decrement ledger — one spend source, not two.

All operations are thread-safe (``threading.Lock``).  Config-driven, OFF/inert
unless a provider is explicitly configured with a balance.  Stdlib only, no
network, no external deps.  Per-reason counters like ``quota.py``.

Public API:
  ``remaining(provider) -> float|None``
  ``record_spend(provider, usd, model=None)``
  ``model_spend(model, provider) -> float``
  ``should_drain(provider) -> bool``   (positive balance -> route-first)
  ``is_drained(provider, floor=0.0) -> bool``  (approx 0 -> demote/skip)
  ``funding_class(provider) -> int|None``
  ``park(provider)`` / ``unpark(provider)`` / ``is_parked(provider)``
"""
from __future__ import annotations

import json
import os
import time
from collections.abc import Callable
from threading import Lock
from typing import Any

from .netutil import BROWSER_UA  # shared browser-like UA (P5 — Cloudflare 1010)

# ---------------------------------------------------------------------------
# Balance poll adapters — pure functions that take (base_url, api_key) and
# return remaining USD (float) or None when the provider doesn't expose one.
# ---------------------------------------------------------------------------


def _poll_deepseek(base_url: str, api_key: str, timeout: float) -> float | None:
    """DeepSeek ``GET /user/balance`` → return remaining USD."""
    import urllib.request

    url = base_url.rstrip("/") + "/user/balance"
    req = urllib.request.Request(url, method="GET")
    req.add_header("User-Agent", BROWSER_UA)
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
    req.add_header("User-Agent", BROWSER_UA)
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
    req.add_header("User-Agent", BROWSER_UA)
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

_DEFAULT_POLL_TTL = 300.0  # seconds


# ---------------------------------------------------------------------------
# Balance tracker — thread-safe, config-driven
# ---------------------------------------------------------------------------


class BalanceTracker:
    """Thread-safe per-provider balance tracker.

    Two modes:
    * **Poll** — configured with ``base_url`` + ``api_key``; periodically calls
      the provider's balance endpoint to get real remaining USD. TTL-cached
      (configurable, default 300s).
    * **Fixed / observer-metered** — class-3 drain-then-park providers with a
      ``starting_balance``; remaining = starting_balance − observer-metered
      spend. No parallel per-provider decrement ledger — one spend source.

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
        self._model_spend: dict[tuple[str, str], float] = {}
        # Poll TTL cache: provider → (result_usd_or_None, timestamp)
        self._poll_cache: dict[str, tuple[float | None, float]] = {}
        # Parked providers (class-3 drain-then-park providers at ~0)
        self._parked: set[str] = set()
        # Observer-metered spend callback: (provider) -> float
        self._spend_provider_fn: Callable[[str], float] | None = None

        # _build_configs_internal normalises the raw providers.json config into
        # the internal per-provider dict the tracker expects.
        for provider, cfg in self._config.items():
            self._build_configs_internal(provider, cfg)

    def _build_configs_internal(self, provider: str,
                                 raw: dict[str, Any]) -> None:
        """Normalise one provider's config from providers.json shape to the
        internal shape consumed by remaining/record_spend."""
        mode = raw.get("mode")
        fc = raw.get("funding_class")
        if fc is not None:
            raw["funding_class"] = int(fc)

        if mode == "fixed":
            start = raw.get("starting_balance") or raw.get("starting_usd", 0.0)
            try:
                self._fixed_balances[provider] = float(start)
            except (ValueError, TypeError):
                self._fixed_balances[provider] = 0.0
            raw["starting_usd"] = float(start)
        elif mode == "poll":
            # Resolve balance_key_env → api_key
            base_url = raw.get("balance_base_url") or raw.get("base_url")
            if base_url:
                raw["base_url"] = str(base_url)
            be = raw.get("balance_key_env") or raw.get("key_env")
            if be and isinstance(be, str):
                raw["api_key"] = os.environ.get(be) or raw.get("api_key", "")
                if not raw["api_key"]:
                    from . import secrets as _sec
                    raw["api_key"] = _sec.load_secrets().get(be, "")
            ttl_raw = raw.get("balance_ttl")
            if ttl_raw is not None:
                try:
                    raw["ttl"] = float(ttl_raw)
                except (ValueError, TypeError):
                    pass

    # -- public API ---------------------------------------------------------

    def remaining(self, provider: str) -> float | None:
        """Current remaining USD for *provider*, or None if not configured.

        Poll providers: TTL-cached; returns None when unreachable (no stale
        cache).  Fixed class-3 providers: starting_balance − observer-metered
        spend (anti-sprawl: one spend source).  Fixed legacy providers (no
        funding_class): the internal tracked balance.

        Unconfigured providers return None.
        """
        cfg = self._config.get(provider)
        if cfg is None:
            return None

        mode = cfg.get("mode")
        if mode == "fixed":
            start = cfg.get("starting_usd", 0.0)
            fc = cfg.get("funding_class")
            if fc == 3 and self._spend_provider_fn is not None:
                spent = self._spend_provider_fn(provider)
                return max(start - spent, 0.0)
            with self._lock:
                return self._fixed_balances.get(provider, 0.0)

        if mode == "poll":
            base_url = cfg.get("base_url")
            api_key = cfg.get("api_key")
            timeout = float(cfg.get("timeout", 20.0))
            ttl = float(cfg.get("ttl", _DEFAULT_POLL_TTL))
            if not base_url or not api_key:
                return None
            adapter = _POLL_ADAPTERS.get(provider)
            if adapter is None:
                return None
            now = self._now()
            with self._lock:
                cached = self._poll_cache.get(provider)
                if cached is not None and (now - cached[1]) < ttl:
                    return cached[0]
            try:
                result = adapter(str(base_url), str(api_key), timeout)
            except Exception:  # noqa: BLE001
                with self._lock:
                    self._counters["poll_error"] = (
                        self._counters.get("poll_error", 0) + 1
                    )
                    self._poll_cache[provider] = (None, now)
                return None
            with self._lock:
                self._poll_cache[provider] = (result, now)
                if result is not None:
                    self._counters["poll_success"] = (
                        self._counters.get("poll_success", 0) + 1
                    )
            return result

        return None

    def record_spend(self, provider: str, usd: float,
                     model: str | None = None) -> None:
        """Decrement a fixed provider's tracked balance by *usd*.

        For class-3 drain-then-park providers AND poll providers, this is a
        no-op on the balance — the observer meter is the single spend source
        (anti-sprawl).  ``_model_spend`` is still updated when ``model`` is
        given so the model-level ledger stays consistent.
        """
        usd = float(usd)
        if usd <= 0.0:
            return
        cfg = self._config.get(provider)
        fc = cfg.get("funding_class") if cfg is not None else None
        if cfg is None or cfg.get("mode") != "fixed":
            if model is not None:
                with self._lock:
                    key = (model, provider)
                    self._model_spend[key] = (
                        self._model_spend.get(key, 0.0) + usd)
            return
        with self._lock:
            # Anti-sprawl: class-3 drain-then-park providers use the observer
            # meter, not a parallel internal decrement.
            if fc != 3:
                cur = self._fixed_balances.get(provider, 0.0)
                self._fixed_balances[provider] = max(cur - usd, 0.0)
            if model is not None:
                key = (model, provider)
                self._model_spend[key] = (
                    self._model_spend.get(key, 0.0) + usd)

    def model_spend(self, model: str, provider: str) -> float:
        """Cumulative metered spend for one (model, provider) pair.

        Returns 0.0 for a never-seen entry (never raises).
        """
        with self._lock:
            return self._model_spend.get((model, provider), 0.0)

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
            return False
        return rem <= floor

    def funding_class(self, provider: str) -> int | None:
        """Return the provider's ``funding_class``, or None if not configured
        or unset."""
        cfg = self._config.get(provider)
        if cfg is None:
            return None
        fc = cfg.get("funding_class")
        if fc is not None:
            return int(fc)
        return None

    # -- park lifecycle (class-3 drain-then-park) ------------------------

    def park(self, provider: str) -> None:
        """Mark a provider as parked (unavailable; routing skips it)."""
        with self._lock:
            self._parked.add(str(provider))

    def unpark(self, provider: str) -> None:
        """Re-arm a parked provider (available again)."""
        with self._lock:
            self._parked.discard(str(provider))

    def is_parked(self, provider: str) -> bool:
        """True if the provider is currently parked."""
        with self._lock:
            return provider in self._parked

    def parked_providers(self) -> set[str]:
        """Return a read-only snapshot of currently-parked providers."""
        with self._lock:
            return set(self._parked)

    # -- spend-source wiring (observer meter) ----------------------------

    def set_spend_provider_fn(self, fn: Callable[[str], float]) -> None:
        """Wire the observer-metered spend callback.

        ``fn(provider)`` must return the total metered spend for that provider
        (sum of ``GatewayProxy.all_model_provider_costs()`` filtered by
        provider label).
        """
        with self._lock:
            self._spend_provider_fn = fn

    # -- poll control ----------------------------------------------------

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
        now = self._now()
        with self._lock:
            self._poll_cache[provider] = (result, now)
            if result is not None:
                self._counters["poll_success"] = (
                    self._counters.get("poll_success", 0) + 1
                )
        return result

    def top_up(self, provider: str, amount_usd: float) -> None:
        """Add *amount_usd* to a fixed provider's configured starting_balance.

        This re-arms a parked class-3 provider by giving it fresh credit.
        """
        amt = float(amount_usd)
        if amt <= 0:
            return
        cfg = self._config.get(provider)
        if cfg is None:
            return
        with self._lock:
            current_start = float(cfg.get("starting_usd", 0.0))
            cfg["starting_usd"] = current_start + amt
            if cfg.get("mode") == "fixed":
                cur = self._fixed_balances.get(provider, 0.0)
                self._fixed_balances[provider] = cur + amt

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
