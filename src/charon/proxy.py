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

from dataclasses import dataclass

from .types import Usage

# Gateway statuses that mean "this model/account is out of capacity right now".
_EXHAUSTION_STATUSES = {429, 402, 503}


@dataclass(frozen=True)
class ProxyObservation:
    """What one upstream response told us about a model."""

    requested_model: str
    returned_model: str | None
    status: int
    exhausted: bool
    pseudo_success: bool  # 200 but the gateway silently served a different model
    retry_after: int | None = None
    usage: Usage | None = None
    note: str = ""

    @property
    def failover(self) -> bool:
        """True iff the coordinator should route this model's role elsewhere."""
        return self.exhausted or self.pseudo_success


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

    def observe(
        self,
        requested_model: str,
        status: int,
        headers: dict | None = None,
        body: dict | None = None,
    ) -> ProxyObservation:
        """Classify one upstream response and fold it into proxy state."""
        returned = (body or {}).get("model")
        exhausted = status in _EXHAUSTION_STATUSES
        # pseudo-success: a 200 that silently served a different model than asked.
        pseudo = bool(
            status == 200 and returned and returned != requested_model
        )
        usage = _gateway_usage(body) if status == 200 else None

        note = ""
        if exhausted:
            note = f"exhausted: status={status} {_error_type(body)}".strip()
        elif pseudo:
            note = f"silent downgrade: asked {requested_model!r}, got {returned!r}"

        obs = ProxyObservation(
            requested_model=requested_model,
            returned_model=returned,
            status=status,
            exhausted=exhausted,
            pseudo_success=pseudo,
            retry_after=_retry_after(headers),
            usage=usage,
            note=note,
        )
        if obs.failover:
            # record under the requested model — the router excludes by model id.
            self._exhausted[requested_model] = obs
        if usage is not None:
            self._usage = Usage(
                tokens_in=self._usage.tokens_in + usage.tokens_in,
                tokens_out=self._usage.tokens_out + usage.tokens_out,
                cost_usd=self._usage.cost_usd + usage.cost_usd,
                latency_ms=self._usage.latency_ms + usage.latency_ms,
            )
        return obs

    def is_exhausted(self, model: str) -> bool:
        return model in self._exhausted

    def exhausted_models(self) -> set[str]:
        """Model ids that have signalled exhaustion or a silent downgrade — the
        coordinator maps these to pool-entry keys to exclude on the next route."""
        return set(self._exhausted)

    def cumulative_usage(self) -> Usage:
        return self._usage
