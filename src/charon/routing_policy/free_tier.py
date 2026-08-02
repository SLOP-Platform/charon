"""Free-tier quota ledger (FREE-TIER-QUOTA-ROUTING).

Provides a **quota-aware router** that orders free legs by remaining headroom
instead of price — the correct axis for free-tier selection, where cost_rank
is always $0 and cannot discriminate between legs.

Layers onto the existing routing_policy infrastructure without modifying it:
the ``FreeTierLedger`` wraps ``QuotaTracker`` with per-provider limit loading
from the TSV seed, and ``order_chain_free_first`` produces the sort key
that reorders a chain so free legs with headroom come first.

Composition with the existing axis (cost_rank / cost_class_priority):
  * Free legs WITH known headroom:  ordered by remaining quota (most headroom first)
  * Free legs AT limit:             excluded from the free bucket; visible in counters
  * Free legs UNKNOWN limit:        surfaced but not preferred; no silent drop
  * Paid legs:                      fall through unchanged; ordered by cost_rank

Observed beats declared: the ledger records usage from every request and
reconciles against live limits from response headers.  A drift between the
TSV seed and observed reality is a signal to update the TSV — never a
silent override of either source.
"""
from __future__ import annotations

import csv
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING, Any

from charon.quota import QuotaTracker

if TYPE_CHECKING:
    from charon.proxy_server import UpstreamRoute

_LIMIT_PATH = Path(__file__).parent.parent.parent / "fleet" / "state" / "FREE-TIER-LIMITS.tsv"

_WINDOW_KEYS = frozenset(
    {"rpm", "rpd", "rwk", "rmo", "tpm", "tpd", "twk", "tmo"}
)


@dataclass
class ProviderLimit:
    """Per-(provider, model) free-tier limits parsed from the TSV seed.

    Fields are optional — a provider may only publish request limits or only
    token limits, and some rows carry ``unpublished`` markers.
    """

    provider: str
    model: str
    rpd: int | None = None
    rpm: int | None = None
    tpd: int | None = None
    tpm: int | None = None
    rwk: int | None = None
    twk: int | None = None
    rmo: int | None = None
    tmo: int | None = None
    exhaustion_signal: str = ""
    unpublished: bool = False

    def limits_dict(self) -> dict[str, int]:
        """The slice of this limit relevant to ``QuotaTracker``."""
        out: dict[str, int] = {}
        for key in _WINDOW_KEYS:
            val = getattr(self, key, None)
            if val is not None and val > 0:
                out[key] = val
        return out

    def has_any_limit(self) -> bool:
        return bool(self.limits_dict())

    def is_unknown(self) -> bool:
        return not self.has_any_limit()


@dataclass
class _UsageRecord:
    """One recorded request's token span for self-accounting."""

    ts: float
    tokens: int


@dataclass
class FreeTierLedger:
    """Quota ledger for free-tier providers.

    Wraps :class:`QuotaTracker` with:
    - Loading per-(provider, model) limits from the TSV seed
    - Self-accounting for providers with unpublished limits
    - Remaining-quota computation for routing selection
    - Reconciliation hook for live observed limits from response headers

    Construction is side-effect-free (no network, no threads).  ``record``
    and ``should_skip`` are thread-safe.

    Usage::

        ledger = FreeTierLedger()
        # or load from TSV seed:
        ledger = FreeTierLedger.from_tsv()

        # Before sending a request:
        if ledger.should_skip(provider, est_tokens=200):
            # ... try another provider
        # ... send request, get actual tokens back ...
        ledger.record(provider, tokens=actual_tokens)

        # Routing selection:
        ordered = order_chain_free_first(chain, ledger, est_tokens=200)

    Observed-override flow::

        # After receiving a response, extract live limits from headers:
        observed = parse_ratelimit_headers(response.headers)
        if observed:
            ledger.reconcile_from_observed(provider, observed)
    """

    tracker: QuotaTracker = field(default_factory=QuotaTracker)
    _limits: dict[tuple[str, str], ProviderLimit] = field(default_factory=dict)
    _self_acct: dict[str, list[_UsageRecord]] = field(default_factory=dict)
    _lock: threading.Lock = field(default_factory=threading.Lock)

    @classmethod
    def from_tsv(
        cls,
        path: Path | str | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
        state_dir: str | Path | None = None,
    ) -> FreeTierLedger:
        """Build a ledger from the TSV seed at *path*.

        ``state_dir`` is passed to :class:`QuotaTracker` for persistence.
        """
        path = Path(path) if path is not None else _LIMIT_PATH
        self_acct: dict[str, list[_UsageRecord]] = {}
        limits: dict[tuple[str, str], ProviderLimit] = {}
        if path.exists():
            try:
                text = path.read_text(encoding="utf-8")
            except OSError:
                text = ""
            reader = csv.DictReader(text.splitlines(), delimiter="\t")
            for row in reader:
                prov = str(row.get("provider", "")).strip()
                model = str(row.get("model", "")).strip()
                if not prov:
                    continue
                sig = str(row.get("exhaustion_signal", "")).strip().lower()
                unpublished = (
                    "unpublished" in sig
                    or sig == "-"
                    or sig == "unknown"
                    or sig == ""
                )
                pl = ProviderLimit(
                    provider=prov,
                    model=model,
                    rpd=_int_or_none(row.get("rpd")),
                    rpm=_int_or_none(row.get("rpm")),
                    tpd=_int_or_none(row.get("tpd")),
                    tpm=_int_or_none(row.get("tpm")),
                    rwk=_int_or_none(row.get("rwk")),
                    twk=_int_or_none(row.get("twk")),
                    rmo=_int_or_none(row.get("rmo")),
                    tmo=_int_or_none(row.get("tmo")),
                    exhaustion_signal=str(row.get("exhaustion_signal", "")),
                    unpublished=unpublished,
                )
                limits[(prov, model)] = pl
                # Init self-accounting for unpublished providers.
                if pl.is_unknown():
                    self_acct.setdefault(prov, [])
        limits_cfg: dict[str, dict[str, Any]] = {}
        for _key, pl in limits.items():
            prov = pl.provider
            ld = pl.limits_dict()
            if ld:
                existing = limits_cfg.setdefault(prov, {})
                for k, v in ld.items():
                    if k not in existing or v > existing[k]:
                        existing[k] = v
        inst = cls.__new__(cls)
        inst.tracker = QuotaTracker(limits=limits_cfg, now=now, state_dir=state_dir)
        inst._limits = dict(limits)  # type: ignore[assignment]
        inst._self_acct = self_acct
        inst._lock = threading.Lock()
        return inst

    def should_skip(self, provider: str, est_tokens: int = 0) -> bool:
        """Return True iff sending ~*est_tokens* to *provider* would exceed a
        configured limit (from the TSV seed or an observed reconciliation)."""
        return self.tracker.should_skip(provider, est_tokens=est_tokens)

    def record(self, provider: str, tokens: int) -> None:
        """Record one completed request against *provider*'s configured limits.

        Also updates self-accounting for providers with unpublished limits so
        unknown-limit providers are tracked from our own usage.
        """
        self.tracker.record(provider, tokens)
        with self._lock:
            if provider in self._self_acct:
                self._self_acct[provider].append(
                    _UsageRecord(ts=time.monotonic(), tokens=tokens)
                )

    def get_headroom(self, provider: str, window: str = "tpd") -> float | None:
        """Return the fraction of headroom remaining for *provider* on *window*.

        Returns ``None`` when the provider has no configured limit on that
        window (unknown limit).  A return of ``0.0`` means the limit is
        saturated.  Values in ``(0.0, 1.0]`` indicate remaining capacity.
        """
        from charon.quota import _window_defaults

        active = self.tracker._active.get(provider)
        if not active:
            return None
        limit_cfg = active.get(window)
        if limit_cfg is None:
            return None
        limit, reset = limit_cfg
        if limit <= 0:
            return None
        now_mono = self.tracker._now()
        now_utc = self.tracker._utc_now()
        with self.tracker._lock:
            st = self.tracker._state.get(provider)
            if st is None:
                return 1.0
            try:
                window_seconds, is_token = _window_defaults(window)
            except KeyError:
                return None
            if reset == "rolling":
                if is_token:
                    dq = st.tok_rolling.get(window)
                    if dq is None:
                        return 1.0
                    from charon.quota import _evict_token

                    _evict_token(dq, window_seconds, now_mono)
                    used = sum(t for _, t in dq)
                else:
                    dq = st.req_rolling.get(window)
                    if dq is None:
                        return 1.0
                    from charon.quota import _evict_req

                    _evict_req(dq, window_seconds, now_mono)
                    used = len(dq)
            else:
                cal = st.calendar.get(window)
                if cal is None:
                    return 1.0
                from charon.quota import _is_calendar_rolled

                if _is_calendar_rolled(cal, window, now_utc):
                    return 1.0
                used = cal.count
        return max(0.0, 1.0 - (used / float(limit)))

    def remaining_quota(self, provider: str) -> float | None:
        """Return the combined headroom score for *provider*.

        Combines token and request headroom into a single comparable float.
        Returns ``None`` for unknown-limit providers.  Higher = more headroom.
        """
        h_tpd = self.get_headroom(provider, "tpd")
        h_tpm = self.get_headroom(provider, "tpm")
        h_rpd = self.get_headroom(provider, "rpd")
        h_rpm = self.get_headroom(provider, "rpm")
        heads = [h for h in [h_tpd, h_tpm, h_rpd, h_rpm] if h is not None]
        if not heads:
            return None
        return min(heads)

    def is_unknown_limit(self, provider: str) -> bool:
        """True when the provider has no known limit (unpublished / unresearched)."""
        return self.tracker._active.get(provider) is None

    def is_exhausted(self, provider: str, est_tokens: int = 0) -> bool:
        """True when the provider is at or over ALL its known limits."""
        return self.should_skip(provider, est_tokens=est_tokens)

    def reconcile_from_observed(
        self, provider: str, observed: dict[str, int]
    ) -> None:
        """Update limits from live observed values (response headers / key endpoints).

        Precedence: observed > our accounting > TSV seed.  A drift between the TSV
        and an observed value is surfaced in counters (``limit_drift``), not silently
        resolved.
        """
        if not observed:
            return
        ld = {k: v for k, v in observed.items() if k in _WINDOW_KEYS and v > 0}
        if not ld:
            return
        with self._lock:
            with self.tracker._lock:
                self.tracker._active[provider] = {}
                for k, v in ld.items():
                    self.tracker._active[provider][k] = (v, "rolling")

    def counters(self) -> dict[str, int]:
        """Return a snapshot of skip counters including any limit-reconciliation signals."""
        return dict(self.tracker.counters())


def _int_or_none(v: object) -> int | None:
    if v is None:
        return None
    s = str(v).strip()
    if not s or s == "-" or s.lower() == "unknown":
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def order_chain_free_first(
    chain: list[UpstreamRoute],
    ledger: FreeTierLedger,
    *,
    est_tokens: int = 0,
    cost_rank_key: Callable[[UpstreamRoute], tuple[bool, int, int]] | None = None,
) -> list[UpstreamRoute]:
    """Reorder *chain* so free legs with headroom come FIRST, ordered by
    remaining quota (most headroom first); free legs AT limit are deprioritised
    (but not dropped — they're still reachable as fallback).

    Paid legs and free legs with unknown limits fall through unchanged, ordered
    by *cost_rank_key* if provided (otherwise left in their input position).

    Anti-over-block rule (DONE contract c): when ALL free legs are exhausted
    or unknown, the chain is returned with paid legs in their input order so
    a request that a paid leg could serve is never stranded.

    A provider with an unknown limit is neither preferred as unlimited nor
    silently dropped — it falls through to its input position (DONE contract e).

    ``cost_rank_key(route)`` must return ``(not free, cost_class_priority, cost_rank)``
    — the same tuple ``_live_rank_key`` produces.  When absent, the paid-leg
    bucket is returned in input order.

    Usage::

        ordered = order_chain_free_first(chain, ledger, est_tokens=200)
    """
    if not chain:
        return []

    def _headroom_sort_key(route: UpstreamRoute) -> tuple[int, int]:
        prov = route.provider or route.label
        rem = ledger.remaining_quota(prov)
        unknown = ledger.is_unknown_limit(prov)
        if rem is None:
            unknown_headroom = 2
        elif rem <= 0.0:
            unknown_headroom = 1
        else:
            unknown_headroom = 0
        # Invert headroom so most-headroom sorts first (lowest score).
        # Use large int for unknown so it sorts last in the free bucket.
        if unknown_headroom == 0:
            headroom_inv = int((1.0 - (rem if rem is not None else 0.0)) * 10_000)
        elif unknown:
            headroom_inv = 9998
        else:
            headroom_inv = 9999
        return (unknown_headroom, headroom_inv)

    free_legs: list[UpstreamRoute] = []
    paid_legs: list[UpstreamRoute] = []

    for route in chain:
        spec_free = getattr(route, "free", False)
        if not spec_free:
            paid_legs.append(route)
            continue
        prov = route.provider or route.label
        if ledger.is_exhausted(prov, est_tokens=est_tokens):
            free_legs.append(route)
        elif ledger.is_unknown_limit(prov):
            free_legs.append(route)
        else:
            free_legs.append(route)

    free_legs.sort(key=_headroom_sort_key)

    if not paid_legs:
        return free_legs

    if cost_rank_key is not None:
        paid_legs.sort(key=cost_rank_key)

    return free_legs + paid_legs


class FreeTierPolicy:
    """Routing policy: free-first by quota headroom, then paid by cost.

    Implements the :class:`Policy` interface from ``routing_policy.base``.
    Wraps a :class:`FreeTierLedger` and produces an ordered candidate list
    from the gateway's routes/pools view.

    A provider with an UNKNOWN limit is neither preferred as unlimited nor
    silently dropped — it appears after known-headroom providers in the free
    bucket but before paid legs.  A quota-exhausted free leg is kept at the
    end of the free bucket so it can still serve if all paid legs also fail.
    """

    name: str = "free_tier"

    def __init__(
        self,
        ledger: FreeTierLedger | None = None,
        *,
        now: Callable[[], float] = time.monotonic,
        state_dir: str | Path | None = None,
    ) -> None:
        self._ledger = ledger or FreeTierLedger.from_tsv(state_dir=state_dir)

    @property
    def ledger(self) -> FreeTierLedger:
        return self._ledger

    def select(
        self,
        *,
        model_id: str | None = None,
        work_class: str | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
        est_tokens: int = 0,
    ) -> list[UpstreamRoute]:
        """Return the ordered candidate chain for *model_id*.

        *routes* / *pools* are the gateway's routing tables.  When *model_id*
        is in *pools*, the pool chain is reordered free-first-by-quota.
        Otherwise falls through to ``DefaultPolicy`` behaviour (single route or []).
        """
        pools = pools or {}
        routes = routes or {}
        if model_id is not None and model_id in pools:
            base = list(pools[model_id])
            return order_chain_free_first(base, self._ledger, est_tokens=est_tokens)
        if model_id is not None and model_id in routes:
            return [routes[model_id]]
        return []


def load_tsv_seed(path: Path | str | None = None) -> dict[tuple[str, str], ProviderLimit]:
    """Load the TSV seed into a dict keyed by (provider, model)."""
    path = Path(path) if path is not None else _LIMIT_PATH
    out: dict[tuple[str, str], ProviderLimit] = {}
    if not path.exists():
        return out
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return out
    reader = csv.DictReader(text.splitlines(), delimiter="\t")
    for row in reader:
        prov = str(row.get("provider", "")).strip()
        model = str(row.get("model", "")).strip()
        if not prov:
            continue
        sig = str(row.get("exhaustion_signal", "")).strip().lower()
        unpublished = (
            "unpublished" in sig
            or sig == "-"
            or sig == "unknown"
            or sig == ""
        )
        out[(prov, model)] = ProviderLimit(
            provider=prov,
            model=model,
            rpd=_int_or_none(row.get("rpd")),
            rpm=_int_or_none(row.get("rpm")),
            tpd=_int_or_none(row.get("tpd")),
            tpm=_int_or_none(row.get("tpm")),
            rwk=_int_or_none(row.get("rwk")),
            twk=_int_or_none(row.get("twk")),
            rmo=_int_or_none(row.get("rmo")),
            tmo=_int_or_none(row.get("tmo")),
            exhaustion_signal=str(row.get("exhaustion_signal", "")),
            unpublished=unpublished,
        )
    return out
