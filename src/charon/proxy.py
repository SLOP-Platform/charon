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

import re
import threading
from collections import OrderedDict
from dataclasses import dataclass

from .types import Usage

# Cap on distinct session ids tracked in ``GatewayProxy._session_usage`` (SESSION-COST).
# The bucket is keyed by the caller-supplied ``X-Charon-Session`` header on an
# open-by-default gateway, so without a bound a client minting varied session ids
# grows this dict (and process RSS) without limit — a memory-leak / DoS vector.
# Bounded with LRU eviction: the least-recently-used session id is dropped once a
# NEW session id would push the dict past this cap.
_SESSION_USAGE_MAX = 4096

# Gateway statuses that mean "this model/account is out of capacity right now"
# (transient — retry later / fail over).
_EXHAUSTION_STATUSES = {429, 402, 503}
# Statuses meaning "this model is gone" — drop it from the pool permanently for
# this run, not retry (free rosters churn; renames/removals return 404). ADR R6.
_DROP_STATUSES = {404}
# TOOLCALL-ROOTCAUSE (2026-07-13): a bare 503, or a 402 whose body matches one of
# these patterns, is a MOMENTARY provider-side race that self-heals within
# milliseconds (confirmed live: NanoGPT's "pending billing reservations" 402
# recovered on the very next call). Retrying the SAME provider once (forwarder.py)
# recovers it without burning a failover slot. A deterministic drained-key 402
# (e.g. OpenRouter's "can only afford ... tokens" — the key is genuinely empty)
# does NOT match these patterns and must fail over immediately instead — see
# ``_is_transient_billing_error``.
_TRANSIENT_BILLING_BODY_PATTERNS = [
    "pending billing reservation", "insufficient balance after pending",
]
# Body patterns that signal a billing/capacity exhaustion — we inspect the JSON
# response body because some providers (e.g. OpenCode) return 401 for billing
# failures, not 402/429/503. Without this, the gateway never fails over.
_EXHAUSTION_BODY_PATTERNS = [
    "insufficient_balance", "insufficient quota", "billing",
    "out of funds", "payment required", "credits exhausted",
    "insufficient_quota", "quota exceeded", "rate limit",
    "rate_limit", "too many requests", "overloaded",
]
# Body patterns that signal an AUTHENTICATION error, NOT a billing error. A 401
# with these patterns must NOT trigger failover — it's a bad key, not a depleted
# account. Retrying with the same key on another provider is pointless.
_AUTH_BODY_PATTERNS = [
    "invalid api key", "invalid_key", "unauthorized",
    "authentication failed", "auth error", "incorrect api key",
    "invalid token", "bad credentials", "access denied",
]
# Statuses + body patterns meaning "THIS provider does not serve this model" — a
# per-provider availability error (providers like OpenCode return a terminal 400
# for models they don't host, e.g. "Model gpt-5.5 is not supported"). Treat it
# like a 404 DROP: exclude this candidate and fail over to the next provider in
# the pool (the model may exist elsewhere, possibly on a free/cheaper tier). This
# is what makes tier/cross-provider fallback work. Gated on the body so a generic
# 400 (bad params) is NOT dropped.
# 401 is included because some gateways (opencode-go) return a *401* for a model
# they don't host ("Model gpt-5.5 is not supported"), not a 400/404. It is only
# ever treated as unsupported when the BODY matches an availability pattern below,
# so a genuine auth-401 (bad key) is never dropped — see ``_is_unsupported_model``.
_UNSUPPORTED_STATUSES = {400, 401, 422}
_UNSUPPORTED_BODY_PATTERNS = [
    "not supported", "unsupported", "no such model", "model not found",
    "model_not_found", "does not exist", "unknown model", "invalid model",
    "no route for model", "model is not available", "no endpoints",
    "no endpoints found", "not a valid model",
]


@dataclass(frozen=True)
class ProxyObservation:
    """What one upstream response told us about a model."""

    requested_model: str
    returned_model: str | None
    status: int
    exhausted: bool
    pseudo_success: bool  # 200 but the gateway silently served a different model
    dropped: bool = False  # 404: model is gone — drop from the pool, not retry
    transient: bool = False  # exhausted AND self-heals in ms — retry-once-same-provider
    retry_after: int | None = None
    usage: Usage | None = None
    note: str = ""
    cost_source: str = ""  # "provider" | "computed" | "unpriced" | "" (no usage)

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


def _collect_error_strings(value: object, out: list[str], depth: int = 0) -> None:
    """Recursively gather every string under a (possibly nested) error value.

    Gateways wrap the real upstream error: OpenRouter returns
    ``{"error":{"message":"Provider returned error","metadata":{"raw":"…Invalid
    model…"}}}`` where the actionable text lives in ``error.metadata.raw`` — and
    ``raw`` is frequently a *stringified JSON blob*. Reading only ``error.message``
    misses it, so the classifier can't tell an unsupported-model error from an
    opaque one. This walks the whole ``error`` subtree, and when a string looks
    like embedded JSON (starts with ``{`` / ``[``) it parses and recurses so the
    nested message is matched too. Depth-bounded to avoid pathological bodies."""
    if depth > 6:
        return
    if isinstance(value, str):
        out.append(value)
        s = value.strip()
        if s and s[0] in "{[":  # a stringified JSON error blob (error.metadata.raw)
            import json
            try:
                _collect_error_strings(json.loads(s), out, depth + 1)
            except (ValueError, TypeError):
                pass
    elif isinstance(value, dict):
        for v in value.values():
            _collect_error_strings(v, out, depth + 1)
    elif isinstance(value, list):
        for v in value:
            _collect_error_strings(v, out, depth + 1)


def _body_text_lower(body: dict | None) -> str:
    """Collapse the response body into a lowercased string for pattern matching —
    walks the entire ``error`` subtree (including wrapped/stringified
    ``error.metadata.raw``) plus the top-level ``detail``/``message`` fields."""
    if not body:
        return ""
    parts: list[str] = []
    _collect_error_strings(body.get("error"), parts)
    for k in ("detail", "message"):
        v = body.get(k)
        if isinstance(v, str):
            parts.append(v)
    return " ".join(parts).lower()


def _has_body_pattern(body: dict | None, patterns: list[str]) -> bool:
    """True when any pattern appears in the collapsed body text. Normalizes
    both the body text and patterns by collapsing non-alphanumeric chars to
    spaces, so code-style keys like ``insufficient_balance`` match human-
    readable messages like ``Insufficient balance``."""
    import re
    text = _body_text_lower(body)
    if not text:
        return False
    normalized_text = re.sub(r"[^a-z0-9]+", " ", text).strip()
    for p in patterns:
        normalized_p = re.sub(r"[^a-z0-9]+", " ", p).strip()
        if normalized_p and normalized_p in normalized_text:
            return True
    return False


def _is_billing_error(body: dict | None, status: int) -> bool:
    """A capacity/billing exhaustion: either a well-known HTTP status (429/402/503)
    or a 401 whose response body contains billing/credit-exhaustion language —
    the OpenCode provider returns 401 for "Insufficient balance", not 402."""
    return status in _EXHAUSTION_STATUSES or (
        status == 401 and _has_body_pattern(body, _EXHAUSTION_BODY_PATTERNS))


def _is_transient_billing_error(body: dict | None, status: int) -> bool:
    """True for an exhaustion worth ONE same-provider retry before failing over
    (TOOLCALL-ROOTCAUSE.md): a bare 503, or a 402 matching a known self-healing
    billing-reservation race. A deterministic drained-key 402 does not match and
    returns False — see ``forward_with_failover``'s retry-once-then-failover."""
    if status == 503:
        return True
    if status == 402:
        return _has_body_pattern(body, _TRANSIENT_BILLING_BODY_PATTERNS)
    return False


def _is_auth_error(body: dict | None, status: int) -> bool:
    """An authentication/authorization error — bad key, not billing. A 401 with
    auth patterns must NOT fail over (pointless; every provider rejects a bad key).
    A 401 without billing patterns is conservatively treated as auth."""
    if status != 401:
        return False
    if _has_body_pattern(body, _EXHAUSTION_BODY_PATTERNS):
        return False  # 401 + billing = exhausted, not auth
    if not body:
        return True  # 401 with no body → assume auth, not billing
    return _has_body_pattern(body, _AUTH_BODY_PATTERNS)


def _is_unsupported_model(body: dict | None, status: int) -> bool:
    """A per-provider "this model isn't served here" error (400/401/422 whose body
    says so). DROP the candidate and fail over — the model may exist on another
    provider (tier/cross-provider fallback). Body-gated so a generic bad-request
    400 or an auth-401 (bad key) is not mistaken for a model-availability error."""
    return status in _UNSUPPORTED_STATUSES and _has_body_pattern(
        body, _UNSUPPORTED_BODY_PATTERNS)


# Trailing quantization suffixes a provider may append to an otherwise-identical
# model id (``glm-5.2-fp8`` vs pool ``glm-5.2``). Matched at the END of the final
# path segment (post-lowercasing) so the compare is case-insensitive AND
# quant-insensitive: fp8/fp16/fp32, bf16, int8/int4, and the GGUF ``q<n>[_...]``
# family (``q4_k_m``, ``q5_0``). Stripped repeatedly to fold rare stacked suffixes.
_QUANT_SUFFIX = re.compile(
    r"-(?:fp8|fp16|fp32|bf16|int8|int4|q\d+(?:[._][0-9a-z]+)*)$")


def _normalize_model_id(model_id: str | None) -> str:
    """Normalize a model id for the pseudo-success compare: FINAL path segment,
    lower-cased, with any trailing quantization suffix stripped.

    Providers namespace the same model variously — "accounts/fireworks/models/
    deepseek-v4-pro" and bare "deepseek-v4-pro" are the same model. Comparing the
    final segment avoids false-positives on provider-prefixed aliases (R10d).
    Stripping only the FIRST segment left multi-segment ids prefixed
    ("fireworks/models/deepseek-v4-pro" != "deepseek-v4-pro"), false-flagging
    honest 200s as silent downgrades and triggering a discard-and-rebill
    (double-billing, SR-1).

    Beyond the namespace, the SAME model is echoed with cosmetic case variance
    ("Kimi-K2.7-Code" vs pool "kimi-k2.7-code") or a quant tag ("GLM-5.2-FP8" vs
    "glm-5.2"). Left as-is those diff from the expected id, false-flag a
    ``pseudo_success`` and serve a spurious ``X-Charon-Downgrade`` on an honest 200
    (why a working provider scores 0/4). Lower-case + quant-strip folds them
    together WITHOUT touching the final-segment rsplit that SR-1 depends on."""
    if not model_id:
        return ""
    seg = model_id.rsplit("/", 1)[-1].lower()
    prev = ""
    while prev != seg:
        prev = seg
        seg = _QUANT_SUFFIX.sub("", seg)
    return seg


class GatewayProxy:
    """Observation core: feed it each upstream response, read exhaustion + cost.

    State is per-run (the coordinator owns one): a set of exhausted model ids the
    router excludes (H6), and a cumulative ``Usage`` mirrored into the Ledger."""

    def __init__(self, model_pricing: dict[str, dict] | None = None) -> None:
        self._exhausted: dict[str, ProxyObservation] = {}
        self._usage = Usage()
        self._delta_seen = Usage()
        self._model_pricing = model_pricing or {}
        # Per-(model, provider) cumulative cost (METER-MODEL-PROVIDER Wave 1).
        # Keyed by (requested_model, provider_label); tracks the real metered
        # cost_usd folded in by ``record()`` when both ``provider`` and
        # ``count_usage`` are truthy. This is the per-route spend ledger — Wave-2
        # cost-rank and drain-then-park decisions WILL read from here instead of
        # an est_cost floor. Caller wiring (provider=route.label) is deferred to
        # Wave 2, so this ledger is EMPTY under real traffic today.
        self._model_provider_cost: dict[tuple[str, str], float] = {}
        # Per-session cumulative usage (SESSION-COST), keyed by the caller-supplied
        # ``X-Charon-Session`` id (proxy_server.py). Purely additive bookkeeping
        # alongside ``_usage`` — never read for routing/billing decisions, so this
        # is read-only cost EXPOSURE, not a billing change. A session id that never
        # appears simply never gets an entry. Bounded via LRU eviction
        # (``_SESSION_USAGE_MAX``) so a caller minting unbounded distinct session ids
        # cannot grow this dict without limit (memory-leak / DoS on an
        # open-by-default gateway) — see ``_SESSION_USAGE_MAX`` docstring.
        self._session_usage: OrderedDict[str, Usage] = OrderedDict()
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
        provider: str | None = None,
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

        ``provider`` is the upstream provider label (e.g. ``"deepseek"``,
        ``"openrouter"``). When set, the cost is also folded into the per-(model,
        provider) ledger (METER-MODEL-PROVIDER Wave 1) so Wave-2 cost-rank
        routing and drain-then-park can read actual metered spend instead of
        an est_cost floor. Omitted / None → global counter only
        (backward-compatible). Caller wiring (provider=route.label in
        forwarder.py) is deferred to Wave 2, so this ledger is EMPTY under
        real traffic today — only tests exercise it directly.

        ``observe`` = ``classify`` (pure) + ``record`` (mutate). The gateway's
        in-request failover loop calls them separately, so it can classify an
        attempt, decide whether to serve it, then bill usage only for the one it
        actually returns to the client."""
        obs = self.classify(requested_model, status, headers, body, expected_model)
        self.record(obs, count_usage=count_usage, provider=provider)
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
        if not isinstance(body, dict):
            # Some upstreams (e.g. Google's OpenAI-compatible error responses) ship
            # a JSON *array* rather than an object for error bodies. There is no
            # `.model`/`.error` field to extract from a non-dict payload, so treat
            # it as "no parseable body" instead of crashing every `.get()` below —
            # an AttributeError here happens mid-request (after the upstream status
            # is already known) and surfaces to the client as a connection reset
            # instead of a clean status passthrough. The HTTP `status` itself is
            # still classified normally either way.
            body = None
        returned = (body or {}).get("model")
        exhausted = _is_billing_error(body, status)
        transient = exhausted and _is_transient_billing_error(body, status)
        auth_error = _is_auth_error(body, status)
        dropped = status in _DROP_STATUSES or _is_unsupported_model(body, status)
        # pseudo-success: a 200 that silently served a different model than asked.
        # Use normalized comparison to avoid false-positives when an upstream returns
        # the model id with a provider prefix (e.g. "openai/gpt-4" vs "gpt-4").
        expected = expected_model if expected_model is not None else requested_model
        pseudo = bool(status == 200 and returned and
                      _normalize_model_id(returned) != _normalize_model_id(expected))
        usage = _gateway_usage(body) if status == 200 else None
        cost_source = ""

        # When the provider reports no cost, compute from stored per-token pricing.
        if usage is not None and usage.cost_usd == 0:
            pricing = self._lookup_pricing(requested_model, expected_model)
            ci = pricing.get("cost_input")
            co = pricing.get("cost_output")
            if pricing.get("free") is True:
                cost_source = "free"
            elif ci is not None and co is not None:
                computed = usage.tokens_in * float(ci) + usage.tokens_out * float(co)
                if computed > 0:
                    usage = Usage(
                        tokens_in=usage.tokens_in,
                        tokens_out=usage.tokens_out,
                        cost_usd=computed,
                        latency_ms=usage.latency_ms,
                    )
                    cost_source = "computed"
                else:
                    cost_source = "unpriced"
            else:
                cost_source = "unpriced"
        elif usage is not None:
            cost_source = "provider"

        note = ""
        if exhausted:
            hint = _error_type(body) or _body_text_lower(body)[:60]
            note = f"exhausted: status={status} {hint}".strip()
        elif auth_error:
            note = f"auth: status={status} {_error_type(body)}".strip()
        elif dropped:
            reason = "model gone" if status in _DROP_STATUSES else "unsupported here"
            note = f"dropped: status={status} {_error_type(body)} ({reason})".strip()
        elif pseudo:
            note = f"silent downgrade: asked {expected!r}, got {returned!r}"

        return ProxyObservation(
            requested_model=requested_model,
            returned_model=returned,
            status=status,
            exhausted=exhausted,
            pseudo_success=pseudo,
            dropped=dropped,
            transient=transient,
            retry_after=_retry_after(headers),
            usage=usage,
            note=note,
            cost_source=cost_source,
        )

    def _lookup_pricing(self, requested_model: str,
                        expected_model: str | None) -> dict:
        """Find per-token pricing for a model. Tries the exact requested model id
        first, then a normalized match against expected/requested, then a final-
        segment match against all known model ids."""
        if not self._model_pricing:
            return {}
        models = [requested_model]
        if expected_model and expected_model != requested_model:
            models.append(expected_model)
        for mid in models:
            if mid in self._model_pricing:
                return self._model_pricing[mid]
        for mid in models:
            cleaned = _normalize_model_id(mid)
            if cleaned in self._model_pricing:
                return self._model_pricing[cleaned]
        cleaned_req = _normalize_model_id(requested_model)
        for known_id, entry in self._model_pricing.items():
            if _normalize_model_id(known_id) == cleaned_req:
                return entry
        return {}

    def set_pricing(self, model_pricing: dict[str, dict] | None) -> None:
        """Swap in fresh per-token pricing (web-setup hot-reload). A reference
        reassignment is atomic under the GIL, so a concurrent ``classify`` read
        sees the whole old or whole new dict, never a torn view."""
        self._model_pricing = model_pricing or {}

    def record(self, obs: ProxyObservation, *, count_usage: bool = True,
              session: str | None = None, provider: str | None = None) -> None:
        """Fold a classified observation into proxy state (atomically). Exclusion is
        always recorded on failover; usage is folded only when ``count_usage`` (the
        attempt was actually served to the client — ADR-0005 R10a).

        ``session`` (SESSION-COST) optionally also folds the same usage into a
        per-session bucket, isolated from both the global counter and every other
        session id — so concurrent gateway traffic tagged with a different session
        id (or untagged, ``session=None``) never pollutes this one's cumulative
        cost. Purely additive: the global counter's behavior is unchanged whether
        or not ``session`` is given.

        ``provider`` (METER-MODEL-PROVIDER Wave 1) optionally also folds the same
        usage into the per-(model, provider) ledger so Wave-2 cost-rank routing
        and drain-then-park can read actual metered spend instead of an
        est_cost floor. Caller wiring (provider=route.label) is deferred to
        Wave 2, so this ledger is EMPTY under real traffic today."""
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
                if provider is not None:
                    key = (obs.requested_model, provider)
                    self._model_provider_cost[key] = (
                        self._model_provider_cost.get(key, 0.0) + u.cost_usd)
                if session is not None:
                    prev = self._session_usage.get(session, Usage())
                    is_new = session not in self._session_usage
                    self._session_usage[session] = Usage(
                        tokens_in=prev.tokens_in + u.tokens_in,
                        tokens_out=prev.tokens_out + u.tokens_out,
                        cost_usd=prev.cost_usd + u.cost_usd,
                        latency_ms=prev.latency_ms + u.latency_ms,
                    )
                    self._session_usage.move_to_end(session)
                    if is_new and len(self._session_usage) > _SESSION_USAGE_MAX:
                        self._session_usage.popitem(last=False)

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

    def session_usage(self, session: str) -> Usage:
        """Cumulative ``Usage`` folded under one session id (SESSION-COST) — isolated
        from the global counter and from every other session id, so a benchmark run
        (or any caller) can read exactly its own attributable spend even while other
        traffic hits the same gateway. An unrecognized/never-seen session id returns
        a zero ``Usage`` (never raises)."""
        with self._lock:
            if session in self._session_usage:
                self._session_usage.move_to_end(session)
            return self._session_usage.get(session, Usage())

    def model_provider_cost(self, model: str, provider: str) -> float:
        """Cumulative metered cost for one (model, provider) pair (METER-MODEL-
        PROVIDER Wave 1). Returns 0.0 for a never-seen entry (never raises).

        WAVE-2 DEFERRED: this ledger WILL be read by Wave-2 cost-rank routing
        and drain-then-park to get actual per-route spend instead of an
        est_cost floor. Caller wiring (provider=route.label in forwarder.py)
        is deferred to Wave 2, so this ledger is EMPTY under real traffic
        today — only tests exercise it directly.

        Keying precondition: ``model`` MUST be the EXACT ``requested_model``
        string passed to ``observe()`` — NOT a normalized, prefix-stripped, or
        aliased form. The meter stores entries ONLY for observations that
        passed a non-None ``provider``; ``provider=None`` observations advance
        the global ``_usage`` counter but are NOT metered per-route.

        KNOWN-WAVE2-GAPS (deliberately deferred consistency items so callers
        do not ingest this meter blindly in Wave 2):
        (a) Negative/refund costs are passed through UNGUARDED (no
            ``max(..., 0.0)`` clamp) — matching the global ``_usage`` counter.
            Clamping only here would BREAK the sum(meter)==cumulative_usage
            delta-zero invariant; the guard is intentionally omitted.
        (b) ``unpriced`` responses contribute 0 to this meter while the
            spend-limiter records an est_cost floor — the two ledgers diverge
            on unpriced routes BY DESIGN. Wave-2 cost-rank routing must NOT
            ingest this meter blindly without reconciling the unpriced gap."""
        with self._lock:
            return self._model_provider_cost.get((model, provider), 0.0)

    def all_model_provider_costs(self) -> dict[tuple[str, str], float]:
        """Return a read-only snapshot of all per-(model, provider) metered costs
        (METER-MODEL-PROVIDER Wave 1).

        WAVE-2 DEFERRED: caller wiring (provider=route.label in forwarder.py)
        is deferred to Wave 2, so this ledger is EMPTY under real traffic
        today. See ``model_provider_cost`` for the keying precondition and
        known Wave-2 gaps."""
        with self._lock:
            return dict(self._model_provider_cost)

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
