"""Free-tier quota ledger and quota-aware routing policy (FREE-TIER-QUOTA-ROUTING).

Free-tier selection needs a different axis than paid legs: every free leg is
$0, so ``cost_rank`` cannot discriminate between them, and a leg with quota
remaining is indistinguishable from one that is exhausted.  The correct
selector for a free tier is **remaining quota, not price**.

This module layers onto the existing ``routing_policy`` package without
modifying it.  It provides:

* :class:`FreeTierLedger` — a per-provider quota ledger.  It wraps
  :class:`charon.quota.QuotaTracker` with per-(provider, model) limit
  loading from the TSV seed, self-accounting for providers with unpublished
  limits, remaining-headroom computation, and a live-observation
  reconciliation hook (response headers / key endpoints).
* :func:`order_chain_free_first` — the selection rule.  Among capable legs it
  prefers FREE legs with headroom (most headroom first), falls back to PAID
  legs ordered by ``cost_rank``, and only then to free legs whose limits are
  unknown or exhausted.  It composes with, and does not replace, the existing
  cost-first axis for paid legs.
* :class:`FreeTierPolicy` — a ``routing_policy.base.Policy`` implementation
  wrapping the ledger for the gateway's route/pool view.

Limit semantics
---------------
* Limits are DATA (the TSV seed), never hardcoded — providers change them.
* A provider with an UNKNOWN limit is surfaced, not preferred as unlimited
  and not silently dropped (DONE contract (e)).
* A quota-exhausted leg is healthy and recovers at window rollover; it must
  never be parked as faulty (DONE contract (d)).
* Observed beats declared: live values from response headers take precedence
  over our own accounting, which takes precedence over the TSV seed.  A
  drift between seed and observation is surfaced in counters, not silently
  resolved either way.

``mistral``'s monthly budget is encoded in the seed as ``N_per_month`` in
the token column; it is parsed into the calendar ``tmo`` window so the
provider's largest free budget is a real, enforced limit.
"""
from __future__ import annotations

import csv
import re
import threading
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path
from typing import TYPE_CHECKING

from charon.quota import QuotaTracker

if TYPE_CHECKING:
    from charon.proxy_server import UpstreamRoute

# repo root / fleet / state / FREE-TIER-LIMITS.tsv.  ``free_tier.py`` lives at
# src/charon/routing_policy/, so the repo root is 4 parents up.
_LIMIT_PATH = (
    Path(__file__).resolve().parents[3] / "fleet" / "state" / "FREE-TIER-LIMITS.tsv"
)

_WINDOW_KEYS = frozenset({"rpm", "rpd", "rwk", "rmo", "tpm", "tpd", "twk", "tmo"})

# Suffix -> window code for cells like ``1000000000_per_month``.  The request/
# token kind (first char of the column name) is preserved.
_WINDOW_SUFFIX = {
    "minute": "pm",
    "day": "pd",
    "week": "wk",
    "month": "mo",
}

# request/token windows that feed routing headroom (most binding constraint wins).
_HEADROOM_WINDOWS = ("tpd", "tpm", "tmo", "rpd", "rpm", "rmo", "twk", "rwk")


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


def _parse_window_value(column: str, raw: object) -> tuple[str, int] | None:
    """Parse a TSV cell into ``(window_key, limit)``.

    Handles plain ints (``1000``) and suffixed values like
    ``1000000000_per_month`` (mapped to the monthly window of the same
    request/token kind, e.g. the ``tpd`` column -> ``tmo``).  Returns None
    for empty/``-``/``unknown``/``unpublished`` cells and for cells with a
    suffix this module cannot map to a known window.
    """
    s = str(raw).strip()
    if not s or s in ("-", "unknown", "unpublished"):
        return None
    match = re.fullmatch(r"(\d+)(?:_per_(\w+))?", s)
    if match is None:
        return None
    limit = int(match.group(1))
    if limit <= 0:
        return None
    per = match.group(2)
    if per is None:
        key = column
    else:
        code = _WINDOW_SUFFIX.get(per.lower())
        if code is None or not column:
            return None
        key = column[0] + code
    if key not in _WINDOW_KEYS:
        return None
    return key, limit


def _int_or_none(v: object) -> int | None:
    """Back-compat plain-int parser (legacy tests / callers)."""
    if v is None:
        return None
    s = str(v).strip()
    if not s or s in ("-", "unknown", "unpublished"):
        return None
    try:
        return int(s)
    except (ValueError, TypeError):
        return None


def _limit_from_row(row: dict[str, str]) -> ProviderLimit:
    prov = str(row.get("provider", "")).strip()
    model = str(row.get("model", "")).strip()
    sig = str(row.get("exhaustion_signal", "")).strip().lower()
    unpublished = (
        "unpublished" in sig or sig in ("-", "unknown", "")
    )
    fields: dict[str, int] = {}
    for col in _WINDOW_KEYS:
        if col not in row:
            continue
        parsed = _parse_window_value(col, row.get(col))
        if parsed is not None:
            fields[parsed[0]] = parsed[1]
    return ProviderLimit(
        provider=prov,
        model=model,
        rpd=fields.get("rpd"),
        rpm=fields.get("rpm"),
        tpd=fields.get("tpd"),
        tpm=fields.get("tpm"),
        rwk=fields.get("rwk"),
        twk=fields.get("twk"),
        rmo=fields.get("rmo"),
        tmo=fields.get("tmo"),
        exhaustion_signal=str(row.get("exhaustion_signal", "")),
        unpublished=unpublished,
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.exists():
        return []
    try:
        text = path.read_text(encoding="utf-8")
    except OSError:
        return []
    return [dict(r) for r in csv.DictReader(text.splitlines(), delimiter="\t")]


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
        # or load from TSV seed (the repo's fleet-state seed, see _LIMIT_PATH):
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
            ledger.record_headers(provider, list(response.headers))
    """

    tracker: QuotaTracker = field(default_factory=QuotaTracker)
    _limits: dict[tuple[str, str], ProviderLimit] = field(default_factory=dict)
    _self_acct: dict[str, list[_UsageRecord]] = field(default_factory=dict)
    _header_inventory: dict[str, set[str]] = field(default_factory=dict)
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
        The default *path* is the repo's TSV seed (see ``_LIMIT_PATH``).
        """
        path = Path(path) if path is not None else _LIMIT_PATH
        limits: dict[tuple[str, str], ProviderLimit] = {}
        self_acct: dict[str, list[_UsageRecord]] = {}
        for row in _read_rows(path):
            if not str(row.get("provider", "")).strip():
                continue
            pl = _limit_from_row(row)
            limits[(pl.provider, pl.model)] = pl
            if pl.is_unknown():
                self_acct.setdefault(pl.provider, [])
        # Aggregate per-(provider, window) to the MAX across the provider's
        # models — one per-provider ledger (the ticket's unit) per window.
        limits_cfg: dict[str, dict[str, int]] = {}
        for pl in limits.values():
            prov = pl.provider
            ld = pl.limits_dict()
            if not ld:
                continue
            agg = limits_cfg.setdefault(prov, {})
            for k, v in ld.items():
                if k not in agg or v > agg[k]:
                    agg[k] = v
        inst = cls(tracker=QuotaTracker(limits=limits_cfg, now=now, state_dir=state_dir))
        inst._limits = dict(limits)
        inst._self_acct = self_acct
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

        Combines the headroom of every configured window (request AND token,
        rolling AND calendar) into a single comparable float — the most
        binding constraint governs, so a provider one window away from its
        limit scores low even if every other window is empty.

        Returns ``None`` for unknown-limit providers.  Higher = more headroom.
        """
        heads = [
            h
            for w in _HEADROOM_WINDOWS
            if (h := self.get_headroom(provider, w)) is not None
        ]
        if not heads:
            return None
        return min(heads)

    def is_unknown_limit(self, provider: str) -> bool:
        """True when the provider has no known limit (unpublished / unresearched)."""
        return self.tracker._active.get(provider) is None

    def is_exhausted(self, provider: str, est_tokens: int = 0) -> bool:
        """True when sending to *provider* would exceed a known limit."""
        return self.should_skip(provider, est_tokens=est_tokens)

    def reconcile_from_observed(
        self, provider: str, observed: dict[str, int]
    ) -> None:
        """Update limits from live observed values (response headers / key endpoints).

        Precedence: observed > our accounting > TSV seed.  A drift between the
        seed and an observed value is surfaced via the ``limit_drift`` counter
        — never silently resolved in either direction.
        """
        if not observed:
            return
        ld = {k: v for k, v in observed.items() if k in _WINDOW_KEYS and v > 0}
        if not ld:
            return
        with self._lock:
            with self.tracker._lock:
                existing = self.tracker._active.get(provider, {})
                for k, v in ld.items():
                    if k in existing and existing[k][0] != v:
                        self.tracker._bump("limit_drift")
                self.tracker._active[provider] = {}
                for k, v in ld.items():
                    reset = "calendar" if k in ("rmo", "tmo") else "rolling"
                    self.tracker._active[provider][k] = (v, reset)

    def record_headers(self, provider: str, header_names: list[str] | set[str]) -> None:
        """Record which header names *provider* actually emitted (the
        fly-blind inventory).  The set of providers that never report limits
        tells us where we cannot rely on live discovery."""
        with self._lock:
            self._header_inventory.setdefault(provider, set()).update(header_names)

    def header_inventory(self) -> dict[str, list[str]]:
        """Provider -> sorted list of header names observed, for the fly-blind
        report (which providers expose limits and which do not)."""
        with self._lock:
            return {p: sorted(s) for p, s in self._header_inventory.items()}

    def counters(self) -> dict[str, int]:
        """Snapshot of skip counters, including any limit-drift signals."""
        return dict(self.tracker.counters())


def load_tsv_seed(path: Path | str | None = None) -> dict[tuple[str, str], ProviderLimit]:
    """Load the TSV seed into a dict keyed by (provider, model)."""
    path = Path(path) if path is not None else _LIMIT_PATH
    out: dict[tuple[str, str], ProviderLimit] = {}
    for row in _read_rows(path):
        if not str(row.get("provider", "")).strip():
            continue
        pl = _limit_from_row(row)
        out[(pl.provider, pl.model)] = pl
    return out


def order_chain_free_first(
    chain: list[UpstreamRoute],
    ledger: FreeTierLedger,
    *,
    est_tokens: int = 0,
    cost_rank_key: Callable[[UpstreamRoute], tuple[bool, int, int]] | None = None,
) -> list[UpstreamRoute]:
    """Reorder *chain* so free legs with headroom come FIRST.

    Final order — four buckets, in preference order:

    1. FREE legs with KNOWN headroom, most headroom first.
    2. PAID legs, ordered by *cost_rank_key* when provided (else input order).
    3. FREE legs with UNKNOWN limits — surfaced, not preferred, not dropped.
    4. FREE legs at/exceeding their limit — last resort only, and re-admitted
       at window rollover automatically (DONE contract (d)).

    This ordering keeps the ANTI-OVER-BLOCK guarantee: a request that a paid
    leg could serve is never stranded, and an exhausted free leg is never
    sent to while a paid leg can serve (no 429 incurred — DONE contract (b)).

    ``cost_rank_key(route)`` must return ``(not free, cost_class_priority,
    cost_rank)`` — the same tuple ``_live_rank_key`` produces.  When absent,
    the paid-leg bucket is returned in input order.

    Usage::

        ordered = order_chain_free_first(chain, ledger, est_tokens=200)
    """
    if not chain:
        return []

    free_headroom: list[UpstreamRoute] = []
    free_unknown: list[UpstreamRoute] = []
    free_exhausted: list[UpstreamRoute] = []
    paid_legs: list[UpstreamRoute] = []

    for route in chain:
        if not getattr(route, "free", False):
            paid_legs.append(route)
            continue
        prov = route.provider or route.label
        if ledger.is_unknown_limit(prov):
            free_unknown.append(route)
        elif ledger.is_exhausted(prov, est_tokens=est_tokens):
            free_exhausted.append(route)
        else:
            free_headroom.append(route)

    # Most headroom first: remaining_quota in (0, 1.0]; ascending 1-rem.
    free_headroom.sort(
        key=lambda r: 1.0 - (ledger.remaining_quota(r.provider or r.label) or 0.0)
    )

    if cost_rank_key is not None:
        paid_legs.sort(key=cost_rank_key)

    return free_headroom + paid_legs + free_unknown + free_exhausted


class FreeTierPolicy:
    """Routing policy: free-first by quota headroom, then paid by cost.

    Implements the :class:`Policy` interface from ``routing_policy.base``.
    Wraps a :class:`FreeTierLedger` and produces an ordered candidate list
    from the gateway's routes/pools view.

    A provider with an UNKNOWN limit is neither preferred as unlimited nor
    silently dropped — it is surfaced (DONE contract (e)).  A quota-exhausted
    free leg is kept as a last-resort fallback so it can still serve if every
    paid leg also fails (DONE contract (c)).
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
