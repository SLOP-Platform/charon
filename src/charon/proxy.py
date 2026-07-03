"""Observing gateway proxy — the failover/cost mechanism (ADR-0004 R1).

Charon drives a coding agent over ACP; the *agent* talks to the model gateway, so
Charon never sees the raw gateway HTTP response. Without that, the operator's two
core needs are unobservable: (1) "this model is rate-limited, move to the next"
and (2) "minimize cost". This module is the fix: a thin Charon-owned
OpenAI-compatible proxy the agent points at (`baseURL = http://127.0.0.1:<port>/v1`).
The proxy forwards each call to the configured upstream and **observes every
response**, turning it into a vendor-neutral signal:

- HTTP ``429``/``402`` (+ ``Retry-After``) ⇒ the model is **exhausted** → fail over.
- a ``200`` whose returned ``model`` ≠ the requested one ⇒ a **silent downgrade**
  (e.g. a flat plan dropping to a free model) — a *pseudo-success* that must also
  trigger failover, not be mistaken for progress.
- the ``usage`` object ⇒ tokens + cost, summed into the Ledger (INV-1, cost).

Because the proxy holds the upstream API keys, credentials stay in Charon's
control plane and never reach the worker/agent. This module is the testable
*observation core*; the HTTP serving/forwarding shell sits on top and is exercised
live via ``charon doctor`` (no real network in these unit tests).
"""
from __future__ import annotations

import threading
from dataclasses import dataclass

from .types import Usage

# Gateway statuses that mean "this model/account is out of capacity right now"
# (transient — retry later / fail over).
_EXHAUSTION_STATUSES = {429, 402, 503}
# Statuses meaning "this model is gone" — drop it from the pool permanently for
# this run, not retry (free rosters churn; renames/removals return 404). ADR R6.
_DROP_STATUSES = {404}


@dataclass(frozen=True)
class ProxyObservation:
    """What one upstream response told us about a model."""

    requested_model: str
    returned_model: str | None
    status: int
    exhausted: bool
    pseudo_success: bool  # 200 but the gateway silently served a different model
    dropped: bool = False  # 404: model is gone — drop from the pool, not retry
    retry_after: int | None = None
    usage: Usage | None = None
    note: str = ""

    @property
    def failover(self) -> bool:
        """True iff the coordinator should route this model's role elsewhere."""
        return self.exhausted or self.pseudo_success or self.dropped


def _retry_after(headers: dict | None) -> int | None:
    if not headers:
        return None
    # case-insensitive header lookup
    for k, v in headers.items():
        if k.lower() == "retry-after":
            try:
                return int(float(v))
            except (TypeError, ValueError):
                return None
    return None


def _gateway_usage(body: dict | None) -> Usage | None:
    """Map an OpenAI/OpenRouter-shaped ``usage`` object to Charon's vendor-neutral
    Usage. Gateways report ``prompt_tokens``/``completion_tokens``/``cost`` — not
    Charon's internal field names — so this is a deliberate translation, not
    ``Usage.from_dict`` (which is for the Ledger's own format)."""
    u = (body or {}).get("usage")
    if not isinstance(u, dict):
        return None
    return Usage(
        tokens_in=int(u.get("prompt_tokens", 0) or 0),
        tokens_out=int(u.get("completion_tokens", 0) or 0),
        cost_usd=float(u.get("cost", u.get("total_cost", 0.0)) or 0.0),
    )


def _error_type(body: dict | None) -> str:
    if not body:
        return ""
    err = body.get("error")
    if isinstance(err, dict):
        meta = err.get("metadata")
        if isinstance(meta, dict) and meta.get("error_type"):
            return str(meta["error_type"])
        if err.get("code"):
            return str(err["code"])
    return ""


class GatewayProxy:
    """Observation core: feed it each upstream response, read exhaustion + cost.

    State is per-run (the coordinator owns one): a set of exhausted model ids the
    router excludes (H6), and a cumulative ``Usage`` mirrored into the Ledger."""

    def __init__(self) -> None:
        self._exhausted: dict[str, ProxyObservation] = {}
        self._usage = Usage()
        self._delta_seen = Usage()
        # The proxy server is THREADED — concurrent agent calls race on this
        # state. A lock keeps usage summation and the exhausted set atomic.
        self._lock = threading.Lock()

    def observe(
        self,
        requested_model: str,
        status: int,
        headers: dict | None = None,
        body: dict | None = None,
        expected_model: str | None = None,
        count_usage: bool = True,
    ) -> ProxyObservation:
        """Classify one upstream response and fold it into proxy state (atomically).

        ``requested_model`` is the id we record exclusion under (the router's pool
        id). ``expected_model`` is the NATIVE model id actually sent upstream, used
        for the pseudo-success comparison — they differ when the pool id carries a
        provider prefix (``opencode-go/kimi-k2.7-code`` vs the upstream's bare
        ``kimi-k2.7-code``), so comparing the returned id against the pool id would
        false-positive every honest 200 as a silent downgrade. Defaults to
        ``requested_model`` (the two coincide when there is no prefix).

        ``count_usage`` is False for a gateway attempt that is **discarded and
        failed over from** — its tokens/cost must NOT be billed, since the client
        never receives that response (ADR-0005 R10a, double-counting fix). Exclusion
        is still recorded so the next request skips it.

        ``observe`` = ``classify`` (pure) + ``record`` (mutate). The gateway's
        in-request failover loop calls them separately, so it can classify an
        attempt, decide whether to serve it, then bill usage only for the one it
        actually returns to the client."""
        obs = self.classify(requested_model, status, headers, body, expected_model)
        self.record(obs, count_usage=count_usage)
        return obs

    def classify(
        self,
        requested_model: str,
        status: int,
        headers: dict | None = None,
        body: dict | None = None,
        expected_model: str | None = None,
    ) -> ProxyObservation:
        """Classify one upstream response into a ``ProxyObservation`` — PURE, no
        state mutation (so the gateway can classify before deciding to serve)."""
        returned = (body or {}).get("model")
        exhausted = status in _EXHAUSTION_STATUSES
        dropped = status in _DROP_STATUSES
        # pseudo-success: a 200 that silently served a different model than asked.
        expected = expected_model if expected_model is not None else requested_model
        pseudo = bool(status == 200 and returned
                      and returned.rsplit("/", 1)[-1] != expected.rsplit("/", 1)[-1])
        usage = _gateway_usage(body) if status == 200 else None

        note = ""
        if exhausted:
            note = f"exhausted: status={status} {_error_type(body)}".strip()
        elif dropped:
            note = f"dropped: status=404 {_error_type(body)} (model gone)".strip()
        elif pseudo:
            note = f"silent downgrade: asked {expected!r}, got {returned!r}"

        return ProxyObservation(
            requested_model=requested_model,
            returned_model=returned,
            status=status,
            exhausted=exhausted,
            pseudo_success=pseudo,
            dropped=dropped,
            retry_after=_retry_after(headers),
            usage=usage,
            note=note,
        )

    def record(self, obs: ProxyObservation, *, count_usage: bool = True) -> None:
        """Fold a classified observation into proxy state (atomically). Exclusion is
        always recorded on failover; usage is folded only when ``count_usage`` (the
        attempt was actually served to the client — ADR-0005 R10a)."""
        with self._lock:
            if obs.failover:
                # record under the requested model — the router excludes by model id.
                self._exhausted[obs.requested_model] = obs
            if obs.usage is not None and count_usage:
                u = obs.usage
                self._usage = Usage(
                    tokens_in=self._usage.tokens_in + u.tokens_in,
                    tokens_out=self._usage.tokens_out + u.tokens_out,
                    cost_usd=self._usage.cost_usd + u.cost_usd,
                    latency_ms=self._usage.latency_ms + u.latency_ms,
                )

    def is_exhausted(self, model: str) -> bool:
        with self._lock:
            return model in self._exhausted

    def exhausted_models(self) -> set[str]:
        """Model ids to exclude on the next route — exhausted (429/402/503),
        dropped (404), or silently downgraded (H6)."""
        with self._lock:
            return set(self._exhausted)

    def cumulative_usage(self) -> Usage:
        with self._lock:
            return self._usage

    def take_delta(self) -> Usage:
        """Atomically return usage since the last call (so a backend can attribute
        a dispatch's spend without racing the shared observer — review fix #2)."""
        with self._lock:
            cur, prev = self._usage, self._delta_seen
            self._delta_seen = cur
            return Usage(
                tokens_in=cur.tokens_in - prev.tokens_in,
                tokens_out=cur.tokens_out - prev.tokens_out,
                cost_usd=cur.cost_usd - prev.cost_usd,
                latency_ms=cur.latency_ms - prev.latency_ms,
            )
