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
  ``record_exhaustion(provider)`` (request-path auto-park on a deterministic
  drained-key 402 — distinct counter from an operator-triggered ``park()``)

Park state persists to ``<state_dir>/balance_park.json`` (atomic write) when
constructed with a ``state_dir`` — survives a gateway restart. A poll-mode
provider (deepseek/openrouter/nanogpt) auto-re-arms the moment its balance
poll shows recovered funds (see ``remaining()``); a fixed-mode class-3
provider re-arms via ``top_up()`` (operator) as before.
"""
from __future__ import annotations

import json
import os
import threading
import time
import uuid
from collections.abc import Callable
from pathlib import Path
from threading import Lock
from typing import Any

from .netutil import BROWSER_UA  # shared browser-like UA (P5 — Cloudflare 1010)

# AUTO-PARK persistence: the parked-provider set survives a gateway restart by
# being written to this file under the tracker's ``state_dir`` — same JSON +
# tmp-write/os.replace convention as spend_limits.py's ``spend.json`` /
# quality_scorer.py's state file. ``state_dir`` is None unless the caller opts
# in (gateway.py's ``_build_balance_tracker`` always passes the resolved
# CHARON_HOME/config dir — CRITICAL: that must be the mounted volume in a
# container deploy, never the ephemeral image FS, or a restart loses parks).
_PARK_STATE_FILE = "balance_park.json"
# A parked poll-mode provider (deepseek/openrouter/nanogpt) auto-re-arms the
# moment its balance poll reports MORE than this many USD — same floor
# ``should_drain`` uses for "has funds, route-first".
_AUTO_REARM_MIN_USD = 0.0

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
        state_dir: str | Path | None = None,
    ) -> None:
        self._config: dict[str, dict[str, Any]] = dict(config or {})
        self._lock = Lock()
        self._now = now

        self._fixed_balances: dict[str, float] = {}
        self._counters: dict[str, int] = {}
        self._model_spend: dict[tuple[str, str], float] = {}
        # Poll TTL cache: provider → (result_usd_or_None, timestamp)
        self._poll_cache: dict[str, tuple[float | None, float]] = {}
        # Parked providers (class-3 drain-then-park providers at ~0, OR any
        # provider auto-parked on a deterministic drained-key 402 — see
        # forwarder.py). None-state_dir → in-memory only (existing unit-test
        # construction pattern; production always passes state_dir).
        self._parked: set[str] = set()
        # Observer-metered spend callback: (provider) -> float
        self._spend_provider_fn: Callable[[str], float] | None = None
        self._state_dir: Path | None = Path(state_dir) if state_dir is not None else None
        # Dedicated I/O lock serializing the ENTIRE parked-set persist
        # (snapshot → write → atomic replace) so two concurrent park()/unpark()
        # callers never interleave their writes. Separate from ``self._lock``
        # (a non-reentrant Lock) so the disk I/O never blocks in-memory reads —
        # the two are acquired _save_lock→_lock, never the reverse, so no
        # inversion. See ``_save_parked``.
        self._save_lock = Lock()

        # _build_configs_internal normalises the raw providers.json config into
        # the internal per-provider dict the tracker expects.
        for provider, cfg in self._config.items():
            self._build_configs_internal(provider, cfg)

        if self._state_dir is not None:
            self._load_parked()

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
            # AUTO-UNPARK (re-arm): a fresh poll on a PARKED poll-mode provider
            # that now shows recovered funds re-arms it immediately — no operator
            # action. Only fresh polls (not TTL-cached hits, handled above) reach
            # here, so this fires at most once per TTL window per provider.
            if result is not None and result > _AUTO_REARM_MIN_USD:
                self._maybe_auto_unpark(provider)
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
        """Mark a provider as parked (unavailable; routing skips it).

        Persisted to disk (when ``state_dir`` was given) so the park survives a
        gateway restart — never loses the fact that a key was drained."""
        with self._lock:
            self._parked.add(str(provider))
        self._save_parked()

    def unpark(self, provider: str) -> None:
        """Re-arm a parked provider (available again). Persisted like ``park``."""
        with self._lock:
            self._parked.discard(str(provider))
        self._save_parked()

    def is_parked(self, provider: str) -> bool:
        """True if the provider is currently parked."""
        with self._lock:
            return provider in self._parked

    def parked_providers(self) -> set[str]:
        """Return a read-only snapshot of currently-parked providers."""
        with self._lock:
            return set(self._parked)

    def record_exhaustion(self, provider: str) -> None:
        """Auto-park *provider* from the request path on a DETERMINISTIC billing
        exhaustion (a drained-key 402 — see ``forwarder.py``'s non-200 branch).

        Distinct entry point from the operator-triggered ``park()`` (web console
        / setup API `balance` action) purely for observability: bumps the
        ``auto_park`` counter so a self-park is distinguishable from a manual
        one in ``counters()``. Identical park semantics otherwise — excluded
        from rotation, provider config untouched, reversible via ``unpark()``,
        ``top_up()``, or an automatic poll-recovery re-arm."""
        with self._lock:
            self._counters["auto_park"] = self._counters.get("auto_park", 0) + 1
        self.park(provider)

    # -- persistence (survive a gateway restart) -------------------------

    def _load_parked(self) -> None:
        """Load the parked-provider set from disk. Missing/corrupt file → start
        with an empty set (never raises — a fresh install has no state yet)."""
        if self._state_dir is None:
            return
        p = self._state_dir / _PARK_STATE_FILE
        if not p.exists():
            return
        try:
            data = json.loads(p.read_text())
        except (OSError, json.JSONDecodeError):
            return
        if not isinstance(data, dict):
            return
        parked = data.get("parked")
        if isinstance(parked, list):
            with self._lock:
                self._parked = {str(x) for x in parked}

    def _save_parked(self) -> None:
        """Write the current parked-provider set to disk atomically. No-op when
        ``state_dir`` was never configured (in-memory-only construction, e.g.
        most unit tests).

        CONCURRENCY: this runs from ``park()``/``unpark()`` AFTER releasing
        ``self._lock`` (unlike ``spend_limits._save()``, which is called by
        ``record()`` while it still HOLDS its lock — fully serialized there).
        Because park() is reached from the money path (``forwarder.py``'s
        non-200 branch via ``record_exhaustion``) an unhandled exception here
        would tear down the client connection with no HTTP response — a silent
        hang. Two protections make that impossible:

        1. The whole snapshot → write → replace runs under ``self._save_lock``
           so concurrent saves are fully serialized (the final ``os.replace``
           always reflects a consistent snapshot; a stale write can never win).
        2. The temp file carries a per-call UNIQUE suffix (pid + thread id +
           uuid) so two callers never share one tmp path — the old single
           static ``<name>.tmp`` let one thread's ``os.replace`` consume the
           other's tmp, and the loser raised ``FileNotFoundError`` (repro:
           526/1200 calls under 4 threads).

        Belt-and-braces, any residual OS error is swallowed (best-effort
        persist) so a disk hiccup can NEVER propagate into the money path and
        break the loud-terminal-503 invariant — the in-memory park state is
        still correct, only its durability is at risk."""
        if self._state_dir is None:
            return
        with self._save_lock:
            with self._lock:
                snapshot = sorted(self._parked)
            d = self._state_dir
            p = d / _PARK_STATE_FILE
            # Unique per-call tmp name — pid + thread id + uuid — so concurrent
            # writers never collide on a shared tmp path (root cause of the race).
            tmp = p.with_name(
                f"{p.name}.{os.getpid()}.{threading.get_ident()}.{uuid.uuid4().hex}.tmp")
            try:
                d.mkdir(parents=True, exist_ok=True)
                tmp.write_text(
                    json.dumps({"parked": snapshot}, indent=2), encoding="utf-8")
                os.replace(tmp, p)
            except OSError:
                # Best-effort: never let a persist failure reach the money path.
                # Clean up our own tmp so we don't leak it, then give up quietly.
                try:
                    tmp.unlink()
                except OSError:
                    pass
                with self._lock:
                    self._counters["park_save_error"] = (
                        self._counters.get("park_save_error", 0) + 1)

    def _maybe_auto_unpark(self, provider: str) -> None:
        """Re-arm *provider* if it is currently parked (idempotent no-op
        otherwise) — the poll-recovery path in ``remaining()``."""
        with self._lock:
            was_parked = provider in self._parked
        if not was_parked:
            return
        self.unpark(provider)
        with self._lock:
            self._counters["auto_unpark"] = self._counters.get("auto_unpark", 0) + 1

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
        # AUTO-UNPARK: same re-arm-on-recovery as remaining()'s poll branch —
        # this is the operator-triggerable refresh, so a manual "check now"
        # must re-arm just as readily as the next request's lazy poll would.
        if result is not None and result > _AUTO_REARM_MIN_USD:
            self._maybe_auto_unpark(provider)
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
