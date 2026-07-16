"""Data-plane failover forwarder for the gateway proxy (seams D + F).

The money-path: builds each upstream attempt and runs the ordered failover loop
(non-200 / 200-nonstream / 200-stream branches, silent-downgrade detection,
exhaustion synthesis, caching, spend recording). Extracted VERBATIM from
_ProxyHandler._handle / _build_upstream_req -- identical SR-1/SR-2/DTC behavior,
only relocated. Cooldown/chain/order locking stays on GatewayProxyServer and is
reached through ``srv``; this module never re-implements it. No logic change.
"""
from __future__ import annotations

import hashlib
import json
import time
import urllib.error
import urllib.request
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from . import translate
from .netutil import BROWSER_UA
from .providers import WIRE_ANTHROPIC
from .proxy_response import _extract, _pre_flight_estimate
from .request_normalizer import normalize_messages as _normalize_request_messages
from .response_adapters import get_adapter
from .response_normalizer import NormalizeMode

if TYPE_CHECKING:  # annotation-only; a runtime import would re-form the proxy_server cycle
    from .proxy_server import UpstreamRoute

_SKIP_HEADERS = {"host", "authorization", "content-length", "connection",
                 "accept-encoding", "proxy-authorization"}
# Browser-like (P5): a non-browser default trips Cloudflare 1010 (→403) on
# CF-fronted providers (groq/cerebras/together). Shared with balance.py + probes
# via the single BROWSER_UA constant so it can never drift.
_DEFAULT_UA = BROWSER_UA
# Library-default UAs upstream bot-protection bans (Cloudflare 1010); normalize
# these to the proxy's own identity so an internal urllib caller isn't blocked.
_BANNED_UA_PREFIXES = ("python-urllib", "python-requests")
# Cap the streamed bytes buffered while looking for the response `model` id (the
# silent-downgrade check before committing a stream); bounds memory on a stream
# that never carries a model field.
_STREAM_HEAD_CAP = 65536

# Per ADR-0016 step #5: a structured envelope on terminal 5xx so the caller
# sees WHICH providers were tried, WHY each failed, and WHEN it re-arms —
# without reading logs. Sourced from the proxy's own ``balance_tracker``
# (the single source of truth for funding class) and the per-attempt
# failovers list; never hand-fabricated. Funding class taxonomy mirrors
# ``balance.py`` and ``config/providers.py`` (1=free-recurring, 2=flat-sub,
# 3=drain-then-park, 4=PAYG). Each class has a different re-arm condition
# (free → auto-reset by quota window, prepaid drain-then-park → operator
# top-up, flat-sub → next billing cycle, PAYG → top-up / rate-limit cooldown).
_FUNDING_CLASS_LABEL: dict[int, str] = {
    1: "free-recurring",
    2: "flat-sub",
    3: "drain-then-park",
    4: "PAYG",
}
_FUNDING_CLASS_REARM: dict[int, str] = {
    1: "auto reset (quota window)",
    2: "operator top-up (next cycle)",
    3: "operator top-up",
    4: "top-up or rate-limit cooldown",
}


def _classify_provider(provider: str, bt) -> tuple[str, str]:
    """Return ``(class, rearm)`` strings for a provider, sourced from
    ``bt.funding_class(provider)`` so a per-provider config drift can never
    diverge from the actual routing decisions. Unknown → ("unknown",
    "unknown") so the field is always populated (never null) and the caller
    can still see WHICH provider was tried."""
    if bt is None:
        return ("unknown", "unknown")
    fc = bt.funding_class(provider)
    if fc is None:
        return ("unknown", "unknown")
    try:
        return (_FUNDING_CLASS_LABEL[int(fc)], _FUNDING_CLASS_REARM[int(fc)])
    except (KeyError, ValueError):
        return ("unknown", "unknown")


def _spend_to_record(obs, est_cost: float) -> float:
    """Amount to bill the spend limiter for a served 200 response.

    The provider's METERED cost is authoritative whenever it is KNOWN — including a
    real ``$0`` from a free-tier or flat-subscription route (a flat/free provider
    ALWAYS reports ``cost==0``). Billing the pre-flight ``est_cost`` floor on those
    $0 responses is the phantom-spend bug that inflated ``spend.json`` to the
    fictional ~$223: the old ``cost if cost > 0 else est_cost`` substituted the
    fabricated floor (``request_bytes/4 · $1.5e-6``) on EVERY free/flat completion.

    Distinguish by ``obs.cost_source``:
      * ``free`` / ``provider(0)`` — provider reported a real $0 → record 0.0.
      * ``provider`` / ``computed`` — a real charge → record it verbatim.
      * ``unpriced`` (usage present, no cost field, no stored pricing) or no usage
        block at all — GENUINELY unknown → keep the ``est_cost`` floor so an
        uncosted call still advances the universal monthly cap (SR-7). This is the
        ONLY case the floor is substituted.
    """
    if obs.usage is None or obs.cost_source == "unpriced":
        return est_cost
    return obs.usage.cost_usd


def _normalize_message_content(body_bytes: bytes, normalizer) -> bytes:
    """Run the post-response normalizer over ONLY ``choices[0].message.content``,
    never the whole JSON envelope.

    ``STANDARDIZE_MD`` is a regex pass over its input string; handed the full
    serialized body it rewrites the envelope itself (heading/fence/blank-line
    regexes firing on JSON punctuation, ids, or a fenced code block embedded in the
    content). The normalizer is specified to touch message content alone, so parse
    the body, rewrite just the assistant content string, and re-serialize. Anything
    unparseable or content-less passes through byte-for-byte (never corrupt a body
    we can't safely address)."""
    try:
        obj = json.loads(body_bytes)
    except (ValueError, TypeError):
        return body_bytes
    try:
        message = obj["choices"][0]["message"]
        content = message["content"]
    except (KeyError, IndexError, TypeError):
        return body_bytes
    if not isinstance(content, str):
        return body_bytes
    message["content"] = normalizer.normalize(content, NormalizeMode.STANDARDIZE_MD)
    return json.dumps(obj).encode()


def _tool_schemas_from_request(orig_bj: dict) -> dict[str, dict]:
    """Map tool name -> declared JSON-schema parameters from the client's
    ``tools`` array (OpenAI ``[{"type": "function", "function": {"name",
    "parameters"}}, ...]`` shape). Malformed/missing entries are skipped —
    ``tool_repair`` treats an absent schema as "no schema-guided coercion",
    never an error."""
    schemas: dict[str, dict] = {}
    for entry in orig_bj.get("tools") or []:
        if not isinstance(entry, dict):
            continue
        fn = entry.get("function")
        if not isinstance(fn, dict):
            continue
        name = fn.get("name")
        params = fn.get("parameters")
        if name and isinstance(params, dict):
            schemas[name] = params
    return schemas


def _repair_tool_call_response(body_bytes: bytes, tool_repair, tools: dict) -> bytes:
    """Run schema-only tool-call repair over ONLY ``choices[0].message.tool_calls``,
    never the whole JSON envelope.

    Symmetric to ``_normalize_message_content``: a response with no tool_calls, or
    whose arguments already parse+validate, passes through byte-for-byte
    (``tool_repair.repair_tool_calls`` is itself a validate-then-repair guard —
    this wrapper adds only the "is there anything to repair at all" short-circuit
    and the JSON envelope re-encode). Anything unparseable/shape-mismatched also
    passes through unchanged (never corrupt a body we can't safely address)."""
    try:
        obj = json.loads(body_bytes)
    except (ValueError, TypeError):
        return body_bytes
    try:
        message = obj["choices"][0]["message"]
    except (KeyError, IndexError, TypeError):
        return body_bytes
    tool_calls = message.get("tool_calls")
    if not isinstance(tool_calls, list) or not tool_calls:
        return body_bytes
    _repaired, results = tool_repair.repair_tool_calls(tool_calls, tools)
    if not any(r.changed for r in results):
        return body_bytes
    return json.dumps(obj).encode()


def _build_upstream_req(handler, srv, route: UpstreamRoute, orig_bj: dict,
                        raw_body: bytes) -> urllib.request.Request:
    """Build the upstream request for ONE attempt from the ORIGINAL request —
    each provider gets its own ``upstream_model`` (ADR R10b), and the client
    query string is dropped so our ``?token=`` bearer never leaks upstream
    (security review HIGH)."""
    bj = dict(orig_bj)
    if bj:
        if route.upstream_model:
            bj["model"] = route.upstream_model
        if bj.get("stream") is True:
            opts = dict(bj.get("stream_options") or {})
            opts["include_usage"] = True
            bj["stream_options"] = opts
        # Strip output-only fields (e.g. assistant ``reasoning_content`` echoed
        # by DeepSeek-style providers) before forwarding — another provider
        # (e.g. Groq) rejects the request otherwise. Safe-by-default: these
        # fields are output-only and never part of a valid OpenAI chat request.
        stripped = _normalize_request_messages(bj.get("messages"))
        if stripped is not None:
            bj["messages"] = stripped
        # SR-6 Phase-1: for an Anthropic-wire upstream, inject one prompt-cache
        # breakpoint so the stable tools+system prefix bills at the cache-read
        # price. Per-attempt placement makes a failover to an OpenAI provider
        # automatically untouched, and the branch is unreachable for OpenAI-wire
        # routes (route.wire defaults "openai"). Flag OFF → byte-identical body.
        if srv.anthropic_prompt_cache and route.wire == WIRE_ANTHROPIC:
            bj = translate.enrich_anthropic_cache(bj)
        data: bytes | None = json.dumps(bj).encode()
    else:
        data = raw_body or None

    path = urlsplit(handler.path).path  # PATH ONLY — never forward the query string
    strip_v1 = route.strip_v1 if route.strip_v1 is not None else srv.strip_v1
    if strip_v1 and path.startswith("/v1"):
        path = path[len("/v1"):]  # upstream_base already ends in /v1
    url = route.upstream_base.rstrip("/") + path

    req = urllib.request.Request(url, data=data, method=handler.command)
    for hk in handler.headers.keys():
        # User-Agent is normalized separately (below) — never forwarded raw.
        if hk.lower() not in _SKIP_HEADERS and hk.lower() != "user-agent":
            req.add_header(hk, handler.headers[hk])
    req.add_header("Content-Type", "application/json")
    # Egress identity: forward the agent's real UA (some gateways 403 an unknown
    # one), but replace an absent/library-default UA — "Python-urllib/3.x" trips
    # Cloudflare 1010 (→403). Live-verified.
    client_ua = handler.headers.get("User-Agent", "")
    if client_ua and not client_ua.lower().startswith(_BANNED_UA_PREFIXES):
        req.add_header("User-Agent", client_ua)
    else:
        req.add_header("User-Agent", _DEFAULT_UA)
    if route.api_key:
        req.add_header("Authorization", f"Bearer {route.api_key}")
    return req


def _required_capability(body: dict) -> str | None:
    """Return ``'reasoning'`` when the request body signals a reasoning/thinking
    requirement, else ``None``.

    Detects top-level fields: ``reasoning``, ``thinking``,
    ``reasoning_effort``, ``reasoning_config`` — any truthy presence flags the
    request as needing reasoning capability (safe default: if the client asked
    for it, we route to a provider known to support it)."""
    for key in ("reasoning", "thinking", "reasoning_effort", "reasoning_config"):
        val = body.get(key)
        if val is not None and val is not False:
            return "reasoning"  # type: ignore[return-value]
    return None


def _is_sole_leg(provider: str,
                 pools: dict[str, list],
                 bt) -> bool:
    """True if *provider* is the ONLY remaining leg of ANY pool.

    A provider is "remaining" if it is NOT parked (or otherwise permanently
    excluded).  This is the sole-leg guard: we must never park/exclude the
    last provider in a pool, because that orphans the pool and strands ALL
    its traffic.

    ``pools`` is ``srv.pools``: {pool_id: [UpstreamRoute, ...]}.
    """
    if not pools:
        return False
    for _pool_id, routes in pools.items():
        labels = {r.provider or r.label for r in routes}
        if provider not in labels:
            continue
        # Count how many legs in this pool are still viable (not parked).
        viable = 0
        for r in routes:
            p = r.provider or r.label
            if not bt.is_parked(p) and not bt.is_drained(p):
                viable += 1
        if viable == 0 and provider in labels:
            # This provider is the last leg — all others are parked/drained.
            return True
    return False


def _has_live_sibling(provider: str, pools: dict[str, list], bt) -> bool:
    """True only if, in EVERY pool *provider* belongs to, at least one SIBLING
    leg is neither parked nor drained — i.e. parking *provider* would not
    orphan any of its pools.

    Purpose-built sole-leg guard for the request-path AUTO-PARK call
    (deterministic drained-key 402 — no ``funding_class``/balance config backs
    it). ``_is_sole_leg`` above counts the CANDIDATE itself as "viable" unless
    its own ``is_drained`` flag is *already* True — true only for the fc==3
    balance-drain call site, which only ever calls it once ``bt.is_drained
    (prov)`` is already known True. A plain API-key provider has no balance
    config (``is_drained`` always False), so reusing ``_is_sole_leg`` here
    would never treat it as the last leg and a pool could be parked down to
    zero, one request at a time, before the outer "all routes excluded"
    fallback ever caught it. This checks SIBLINGS ONLY (excludes the
    candidate from its own viability count).

    CONSERVATIVE ACROSS ALL OWNING POOLS: a provider can be a healthy member of
    pool A yet the SOLE live leg of pool B. Returning True on the first pool
    with a live sibling would then let us park it and orphan pool B. So we
    require a live sibling in *every* owning pool before allowing a park, and
    return False for a provider with no pool membership at all (never park a
    provider we have no evidence has an alternative)."""
    if not pools:
        return False
    owned = 0
    for _pool_id, routes in pools.items():
        labels = {r.provider or r.label for r in routes}
        if provider not in labels:
            continue
        owned += 1
        pool_has_live_sibling = False
        for r in routes:
            p = r.provider or r.label
            if p == provider:
                continue
            if not bt.is_parked(p) and not bt.is_drained(p):
                pool_has_live_sibling = True
                break
        if not pool_has_live_sibling:
            # This owning pool would be orphaned by parking *provider* → refuse.
            return False
    return owned > 0


def forward_with_failover(handler, srv) -> None:
    """Run the data-plane failover loop for one client request (money path).

    Reads the (already loopback/token-gated, non-control-plane) request off the
    handler and forwards it across the model's cooldown-ordered provider chain."""
    # Read the client request (size-capped — memory-DoS guard on an exposed bind).
    length = int(handler.headers.get("Content-Length") or 0)
    if length > srv.max_body_bytes:
        handler._json(413, {"error": {"message": "request body too large"}})
        return
    raw_body = handler.rfile.read(length) if length else b""

    # Optional per-session cost attribution (SESSION-COST): a caller (e.g. the
    # benchmark harness) tags its own requests with a self-chosen id so its
    # cumulative cost can be read back in isolation from concurrent gateway
    # traffic — see GatewayProxy.session_usage / GET /charon/cost. Absent
    # header → session=None, meaning "don't attribute" (global counter is
    # unaffected either way).
    session_id = handler.headers.get("X-Charon-Session") or None

    orig_bj: dict = {}
    requested = ""
    try:
        orig_bj = json.loads(raw_body) if raw_body else {}
        requested = orig_bj.get("model", "")
    except Exception:  # noqa: BLE001
        pass

    chain = srv.chain_for(requested)
    if not chain:
        srv.observer.observe(requested, 502, {}, {}, count_usage=False)
        # ADR-0016 step #5: 502 because NO route was configured (distinct from
        # the 503 below where a route existed but was exhausted). Same envelope
        # schema so the client only has to learn one shape; ``providers_tried``
        # is empty (nothing was tried) and ``no_provider_reason`` carries the
        # actionable operator hint. Retry-After is omitted (502 = permanent
        # misconfiguration, retrying won't help without a config change).
        handler._json(502, {"error": {
            "message": (
                f"no route for model {requested!r} — no providers configured; "
                "run 'charon setup' or open http://127.0.0.1:8080/charon/setup"
            ),
            "type": "no_route_configured",
            "requested_model": requested,
            "no_provider_reason": "no_providers_configured",
            "retry_after_s": None,
            "providers_tried": [],
        }})
        return

    # ── capability-based route exclusion ────────────────────────────
    # R3: proactive skip of known-incapable providers. If every route would be
    # excluded (strand risk), fall back to the full chain and warn — NEVER strand.
    cap = _required_capability(orig_bj)
    matrix = getattr(srv, "capability_matrix", None)
    if cap and matrix is not None and len(chain) > 0:
        filtered = [r for r in chain if matrix.supports(r.provider or r.label, cap)]
        if filtered:
            chain = filtered
        else:
            # CRITICAL SAFETY: all routes excluded → fall back, log warning
            import logging
            logging.getLogger("charon.forwarder").warning(
                "Capability exclusion would strand request (model=%s cap=%s); "
                "using full chain instead.", requested, cap)

    # ── R7 capability-engine: max_context / max_concurrency eligibility ───
    # Compute a single pre-flight token estimate (reused by spend cap above).
    est_tokens = max(len(raw_body) // 4, 100)
    if len(chain) > 0:
        eligible = []
        for r in chain:
            skip_reason: str | None = None
            mc = getattr(r, "max_context", None)
            if mc is not None and est_tokens > mc:
                skip_reason = "max_context"
            mconc = getattr(r, "max_concurrency", None)
            if mconc is not None and srv.inflight_count(r) >= mconc:
                skip_reason = "max_concurrency"
            if skip_reason is None:
                eligible.append(r)
        if eligible:
            chain = eligible
        else:
            # CRITICAL SAFETY: all routes excluded by hard limits → fall back, warn
            import logging
            logging.getLogger("charon.forwarder").warning(
                "Capability engine would strand request (model=%s est_tokens=%d); "
                "using full chain instead.", requested, est_tokens)

    # ── DRAIN-AND-PARK: funding-class ordering + pre-flight exclusion ──
    # Reorder by funding class (free-daily first, then drain-then-park, then
    # flat-sub, then PAYG).  Within class 3: positive balance → top priority;
    # at ~0 → excluded (no fail-churn) UNLESS this provider is the sole
    # remaining leg of any pool (sole-leg guard — never orphan a pool).
    bt = getattr(srv, "balance_tracker", None)
    if bt is not None and chain and len(chain) > 1:
        from .routing_policy import order_chain_by_funding_class

        def _fc(prov: str) -> int | None:
            fc = bt.funding_class(prov)
            return int(fc) if fc is not None else None

        def _rem(prov: str) -> float | None:
            return bt.remaining(prov)

        chain = order_chain_by_funding_class(
            chain, funding_class_fn=_fc, remaining_fn=_rem)

        # Pre-flight exclusion: class-3 providers at ~0 → skip unless sole leg.
        drain_eligible: list = []
        for r in chain:
            prov = r.provider or r.label
            fc = bt.funding_class(prov)
            if bt.is_parked(prov):
                # Parked — always excluded, independent of funding_class. Covers
                # BOTH a balance-drained class-3 provider AND a provider
                # auto-parked on a deterministic drained-key 402 (below) that
                # carries no funding_class at all. The "all routes excluded"
                # fallback further down (never-strand safety net) covers the
                # rare case where every leg of a pool ends up parked at once.
                continue
            if fc == 3 and bt.is_drained(prov):
                # Sole-leg guard: check if this provider is the only remaining
                # leg of any pool.
                is_sole = _is_sole_leg(prov, srv.pools, bt)
                if is_sole:
                    # Keep it — never orphan the pool.  An alert is logged
                    # but the provider stays in the chain.
                    import logging
                    logging.getLogger("charon.forwarder").warning(
                        "SOLE-LEG GUARD: provider %r is drained (balance=0) but "
                        "is the only remaining leg of a pool — keeping it to "
                        "prevent pool orphaning.", prov)
                    drain_eligible.append(r)
                    continue
                # Pre-flight skip: drained class-3, not sole leg.
                # Auto-park it right now (routing excludes it without fail-churn).
                bt.park(prov)
                continue
            elif fc == 3 and bt.should_drain(prov):
                # Positive balance — ensure it's unparked (may have been
                # re-armed via top_up).
                bt.unpark(prov)
            drain_eligible.append(r)
        if drain_eligible:
            chain = drain_eligible
        else:
            # CRITICAL SAFETY: all routes excluded by drain routing → fall back
            # to the original chain and warn (never strand).
            import logging
            logging.getLogger("charon.forwarder").warning(
                "DRAIN routing would strand request (model=%s); "
                "using full chain instead.", requested)

    # ── spend cap check (before any upstream call) ──────────────────
    if srv.spend_limiter is not None:
        est_cost = _pre_flight_estimate(requested, est_tokens, srv)
        dec = srv.spend_limiter.check(est_cost)
        if not dec.allowed:
            handler._json(402, {"error": {"message": dec.reason,
                           "remaining": dec.remaining}})
            return
    else:
        est_cost = 0.0

    # ── guardrail request scan ──────────────────────────────────────
    if srv.guardrails is not None:
        msgs = orig_bj.get("messages", [])
        violations, _ = srv.guardrails.scan_request(msgs)
        blocking = [v for v in violations if v.severity == "BLOCK"]
        if blocking:
            handler._json(400, {"error": {
                "message": "request blocked by guardrails",
                "violations": [{"pattern": v.pattern, "message": v.message}
                               for v in blocking]
            }})
            return

    # ── cache check ─────────────────────────────────────────────────
    if srv.semantic_cache is not None:
        cache_key = hashlib.sha256(raw_body).hexdigest()
        cached = srv.semantic_cache.get(cache_key)
        if cached is not None:
            ctype = cached.headers.get("Content-Type", "application/json")
            # X-Cache-Status is a REAL header (emitted before end_headers). The
            # prior `wfile.write(b"X-Cache-Status: HIT\r\n\r\n")` ran AFTER
            # end_headers, so it landed in the response BODY and corrupted the
            # cached JSON/SSE payload (DTC CONCERN #5).
            handler._send_resp_headers(200, ctype, "cache", [], False, cache_status="HIT")
            handler._write(cached.content)
            srv.note_request(requested, "cache-hit", 200, 0.0, [])
            return

    is_stream = orig_bj.get("stream") is True

    # ── R2: dynamic cheapest-first using live metered cost ──────────
    # Reorder the provider chain at request time so the cheapest (by real
    # cumulative metered spend) is tried first.  Empty meter → the order is
    # unchanged (preserves the static configured order built at startup).
    # This runs BEFORE cooldown ordering so a cheap-but-cooled provider is
    # still surfaced correctly by the cooldown pass below.
    observer = getattr(srv, "observer", None)
    if observer is not None and chain:
        live = observer.all_model_provider_costs()
        if live:
            registry: dict[str, dict] = {}
            model_pricing = getattr(srv, "model_pricing", {}) or {}
            model_meta = getattr(srv, "model_meta", {}) or {}
            for route in chain:
                mid = route.model_id or route.pool_id or ""
                if mid and mid not in registry:
                    spec = dict(model_pricing.get(mid, {}))
                    spec.update(model_meta.get(mid, {}))
                    registry[mid] = spec
            from .routing_policy import order_pool_by_live_cost
            chain = order_pool_by_live_cost(
                chain, registry=registry, metered_costs=live)

    ordered = srv.order_by_cooldown(chain)  # fresh providers first, cooled last (R7)

    # ── quality-aware routing ──────────────────────────────────────
    if srv.quality_scorer is not None and ordered:
        scored = [(srv.quality_scorer.score(r.label), r) for r in ordered]
        filtered = [r for s, r in scored if s >= 0.5]
        if filtered:
            ordered = filtered
        # else: all below floor → use original order (no starvation)

    failovers: list[dict] = []

    for i, route in enumerate(ordered):
        more = i < len(ordered) - 1
        okey = route.pool_id or requested  # exclusion/observe key (orchestrator compat)
        expected = route.upstream_model or requested or None
        req = _build_upstream_req(handler, srv, route, orig_bj, raw_body)
        # Resolve the response-shape adapter for THIS attempt (IDENTITY unless the
        # provider declares one). Every call site is guarded by `if route.adapter`
        # so the default path is provably byte-identical (never re-encodes).
        adapter = get_adapter(route.adapter)

        # R7: track in-flight for max_concurrency awareness
        srv.inflight_inc(route)
        start = time.monotonic()
        try:
            resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
            status, rhdrs = resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            resp, status, rhdrs = exc, exc.code, dict(exc.headers)
        except Exception:  # provider unreachable → fail over (don't 502 outright)
            srv.inflight_dec(route)
            srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                expected_model=expected), count_usage=False, session=session_id,
                                provider=route.label)
            srv.set_cooldown(route, None)
            if more:  # count only providers we actually move PAST
                failovers.append({"provider": route.label, "status": "unreachable",
                                  "reason": "connection error"})
                continue
            handler._send_resp_headers(502, "application/json", route.label, failovers, False)
            handler._write(json.dumps(
                {"error": {"message": "all upstreams unreachable"}}).encode())
            srv.note_request(requested, route.label, "unreachable", 0.0, failovers)
            return

        ctype = rhdrs.get("Content-Type", "application/json")
        try:
            # ---- non-200 ----
            if status != 200:
                body_bytes = handler._drain(resp)
                obs_body = _extract(body_bytes, ctype)
                obs = srv.observer.classify(okey, status, rhdrs, obs_body,
                                            expected_model=expected)

                # ---- RETRY-ONCE: transient upstream error (TOOLCALL-ROOTCAUSE) ----
                # A bare 503, or a nanogpt-style "pending billing reservations" 402,
                # is a momentary account-state race that self-heals within
                # milliseconds — retry the SAME provider ONCE (zero backoff, it's
                # already resolved by the time we reopen the connection) before
                # spending a failover slot on it. A deterministic drained-key 402
                # (obs.transient False, e.g. openrouter's "can only afford ...
                # tokens") skips this and falls straight to the existing failover
                # logic below — retrying an empty key is pointless.
                if obs.exhausted and obs.transient:
                    srv.inflight_dec(route)  # release the spent first attempt's slot
                    try:
                        resp.close()
                    except Exception:  # best-effort close of the spent attempt's fd
                        pass
                    retry_req = _build_upstream_req(handler, srv, route, orig_bj, raw_body)
                    srv.inflight_inc(route)
                    start = time.monotonic()
                    try:
                        resp = urllib.request.urlopen(retry_req, timeout=srv.fwd_timeout)
                        status, rhdrs = resp.status, dict(resp.headers)
                    except urllib.error.HTTPError as exc:
                        resp, status, rhdrs = exc, exc.code, dict(exc.headers)
                    except Exception:  # unreachable on retry → fail over, same as a
                        # first-attempt connection error (no further retry).
                        srv.observer.record(
                            srv.observer.classify(okey, 503, {}, {}, expected_model=expected),
                            count_usage=False, session=session_id, provider=route.label)
                        srv.set_cooldown(route, None)
                        if more:
                            failovers.append({"provider": route.label, "status": "unreachable",
                                              "reason": "connection error (retry)"})
                            continue
                        handler._send_resp_headers(502, "application/json", route.label,
                                                    failovers, False)
                        handler._write(json.dumps(
                            {"error": {"message": "all upstreams unreachable"}}).encode())
                        srv.note_request(requested, route.label, "unreachable", 0.0, failovers)
                        return
                    ctype = rhdrs.get("Content-Type", "application/json")
                    if status != 200:
                        body_bytes = handler._drain(resp)
                        obs_body = _extract(body_bytes, ctype)
                        obs = srv.observer.classify(okey, status, rhdrs, obs_body,
                                                    expected_model=expected)
                    # else: retry recovered (200) — `status` is now 200, so the
                    # `if status != 200:` re-check just below is False and this
                    # whole non-200 branch is skipped, falling through to the
                    # ordinary 200-handling code (non-stream/stream) as if the
                    # retried attempt had succeeded on the first try.

            if status != 200:
                srv.observer.record(obs, count_usage=False, session=session_id,
                                    provider=route.label)
                if obs.failover:  # 429/402/503/404/401+billing/unsupported → fail over
                    if obs.exhausted:  # account-level exhaustion → cool the
                        srv.set_cooldown(route, obs.retry_after)  # provider (R10c);
                        # AUTO-PARK (money-path self-park, closes the gap PR #121
                        # left open): a DETERMINISTIC drained-key 402 — status==402,
                        # obs.transient False (e.g. openrouter's "can only afford ...
                        # tokens") — means the key itself is empty, not a momentary
                        # race. A time-boxed cooldown alone just re-tries the same
                        # dead key every ``max_cooldown_s``; park it instead so the
                        # pre-flight exclusion (above, this function) drops it from
                        # rotation until an operator top-up or a poll-mode balance
                        # recovery re-arms it (balance.py). Scoped tightly to 402:
                        # a 429 throttle (self-clears with time, not a drained key)
                        # and any transient 402/503 (PR #121 retry-once) must NEVER
                        # be parked — both are excluded here even though
                        # ``obs.exhausted and not obs.transient`` alone would also
                        # be true for a bare 429 (transient is only ever set True
                        # for 503/transient-402, never for 429).
                        if bt is not None and status == 402 and not obs.transient:
                            prov = route.provider or route.label
                            if _has_live_sibling(prov, srv.pools, bt):
                                bt.record_exhaustion(prov)
                            else:
                                import logging
                                logging.getLogger("charon.forwarder").warning(
                                    "SOLE-LEG GUARD: provider %r deterministically "
                                    "exhausted (402) but has no live sibling in any "
                                    "pool — NOT auto-parking it (would strand traffic "
                                    "with no fallback).", prov)
                    # a 404 ("model gone") is model-level — do NOT cool the provider.
                    if more:  # count only providers we actually move PAST
                        failovers.append({"provider": route.label, "status": status,
                                          "reason": obs.note or "exhausted"})
                        continue
                    if failovers:
                        # The LAST provider of a POOL we already failed across also
                        # failed over-eligibly → EVERY provider is exhausted/
                        # unsupported. Relaying this one provider's raw error is
                        # misleading (the client asked for a model no provider could
                        # serve); synthesize a terminal "all providers exhausted"
                        # response carrying the tracked failover reasons. (A single-
                        # upstream gateway with no pool falls through and relays the
                        # real upstream error transparently — nothing was failed over.)
                        failovers.append({"provider": route.label, "status": status,
                                          "reason": obs.note or "exhausted"})
                        # ADR-0016 step #5: structured envelope so the caller
                        # sees WHICH providers were tried, WHY each failed, and
                        # WHEN each re-arms — without reading logs. ``class`` and
                        # ``rearm`` are sourced from ``bt.funding_class(provider)``
                        # (the routing-time source of truth) so they can never
                        # diverge from the actual funding-class decisions.
                        retry_after_s = srv.retry_after_hint(ordered)
                        providers_tried = []
                        for f in failovers:
                            cls_label, rearm_label = _classify_provider(
                                f["provider"],
                                getattr(srv, "balance_tracker", None))
                            providers_tried.append({
                                "provider": f["provider"],
                                "status": f["status"],
                                "reason": f["reason"],
                                "class": cls_label,
                                "rearm": rearm_label,
                            })
                        handler._send_resp_headers(
                            503, "application/json", route.label, failovers, False,
                            retry_after=retry_after_s)
                        handler._write(json.dumps({"error": {
                            "message": "all providers exhausted",
                            "type": "all_providers_exhausted",
                            "requested_model": requested,
                            "no_provider_reason": None,
                            "retry_after_s": retry_after_s,
                            "providers_tried": providers_tried,
                            "failover_reasons": [
                                f"{f['provider']}={f['status']}" for f in failovers],
                        }}).encode())
                        srv.note_request(requested, route.label, status, 0.0, failovers)
                        return
                # a single-upstream exhaustion, OR a 400/401/403 client/auth error we
                # must NOT fail over (R6) — relay the real upstream response as-is.
                # P1: re-bound a raw upstream Retry-After to <= max_cooldown_s on a
                # transient exhaustion (402/429/503); a 400/401/403 client/auth error
                # is not retry-worthy → no Retry-After.
                relay_retry_after = (
                    min(obs.retry_after or srv.default_cooldown, srv.max_cooldown_s)
                    if status in (402, 429, 503) else None)
                if route.adapter:  # canonicalize the error envelope on the terminal
                    canon_err = adapter.normalize_error(obs_body)  # relay (guarded)
                    if canon_err is not obs_body:
                        body_bytes = json.dumps(canon_err).encode()
                handler._send_resp_headers(status, ctype, route.label, failovers, False,
                                        retry_after=relay_retry_after)
                handler._write(body_bytes)
                srv.note_request(requested, route.label, status, 0.0, failovers)
                return

            # ---- 200, non-streaming: buffer, then check for a silent downgrade ----
            if not is_stream:
                body_bytes = handler._drain(resp)
                if route.adapter:  # IDENTITY path stays byte-identical (guarded)
                    parsed = _extract(body_bytes, ctype)  # {} on non-JSON
                    canon = adapter.normalize_response(parsed)
                    if canon is not parsed:  # only re-encode if it actually changed
                        body_bytes = json.dumps(canon).encode()
                # CG-critical: repair malformed tool_calls[].function.arguments
                # (bad JSON from a flaky provider) BEFORE classify/cache/serve see
                # this body. Guarded no-op — byte-identical when tool_repair is
                # unset or the response carries no tool_calls / is already valid.
                # getattr (not attribute) read: proxy_server only materializes a
                # tool_repair attr when one is injected via modules= (F29), so
                # direct-server tests and unconfigured gateways are unaffected.
                _tool_repair = getattr(srv, "tool_repair", None)
                if _tool_repair is not None:
                    body_bytes = _repair_tool_call_response(
                        body_bytes, _tool_repair, _tool_schemas_from_request(orig_bj))
                observed = _extract(body_bytes, ctype)  # now sees top-level model+usage
                obs = srv.observer.classify(okey, 200, rhdrs, observed, expected_model=expected)
                latency_ms = int((time.monotonic() - start) * 1000)
                srv.latency_tracker.record(route.label, latency_ms)
                # ── genuine silent downgrade (obs.pseudo_success) ─────────────
                # Operator toggle `failover_on_downgrade` (default False):
                #   False → SERVE this COMPLETED, already-billed 200 with the
                #     X-Charon-Downgrade header instead of discarding + re-billing a
                #     fresh completion from the next provider (the 2026-07-03
                #     double-bill incident). SR-1 made the id compare segment-tolerant
                #     so only genuine downgrades reach here.
                #   True  → fail over to try for the asked model, but record the
                #     discarded attempt with count_usage=True — HONEST/VISIBLE, the
                #     pre-SR-2 R1 escape hatch WITHOUT the silent count_usage=False
                #     double-bill that started this incident. No next provider →
                #     fall through and serve it (never error).
                if obs.pseudo_success and srv.failover_on_downgrade and more:
                    srv.observer.record(  # visible, not silent
                        obs, count_usage=True, session=session_id,
                        provider=route.label)
                    failovers.append({"provider": route.label, "status": "downgrade",
                                      "reason": obs.note or "served different model"})
                    continue
                srv.observer.record(  # served → bill usage (R10a)
                    obs, count_usage=True, session=session_id,
                    provider=route.label)
                # ── post-response hooks ──────────────────────────
                cost = obs.usage.cost_usd if obs.usage else 0.0
                if srv.response_normalizer is not None:
                    body_bytes = _normalize_message_content(
                        body_bytes, srv.response_normalizer)
                # NEVER cache a served downgrade — the cache-HIT path can't disclose
                # X-Charon-Downgrade, so a cached downgrade would silently re-serve the
                # wrong model for the whole TTL (DTC BLOCKER #1).
                if srv.semantic_cache is not None and not obs.pseudo_success:
                    cache_key = hashlib.sha256(raw_body).hexdigest()
                    srv.semantic_cache.set(cache_key, body_bytes,
                                           rhdrs, ttl=3600)
                if srv.quality_scorer is not None:
                    # A served downgrade is NOT a clean success — scoring it as one
                    # would reward a habitual downgrader and make quality routing
                    # PREFER it (feedback loop, DTC CONCERN #4).
                    srv.quality_scorer.record(
                        route.label, 0, success=not obs.pseudo_success, tokens=0)
                if srv.spend_limiter is not None:
                    srv.spend_limiter.record(_spend_to_record(obs, est_cost))
                if srv.balance_tracker is not None:
                    srv.balance_tracker.record_spend(route.label, cost, model=requested)
                handler._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                handler._write(body_bytes)
                srv.note_request(requested, route.label, 200, cost, failovers)
                return

            # ---- 200, streaming: buffer the head until `model` is seen (or a cap),
            #      so we can fail over a downgrade BEFORE committing bytes (R1) ----
            head: list[bytes] = []
            head_bytes = 0
            stream_broke = False
            try:
                while head_bytes < _STREAM_HEAD_CAP:
                    c = resp.read(8192)
                    if not c:
                        break
                    head.append(c)
                    head_bytes += len(c)
                    if _extract(b"".join(head), ctype).get("model"):
                        break
            except Exception:  # upstream dropped/garbled before we committed any byte
                stream_broke = True
            if stream_broke:  # nothing sent yet → treat like a failed attempt, fail over
                srv.observer.record(
                    srv.observer.classify(okey, 503, {}, {}, expected_model=expected),
                    count_usage=False, session=session_id,
                    provider=route.label)
                if more:
                    failovers.append({"provider": route.label, "status": "stream-error",
                                      "reason": "upstream stream interrupted"})
                    continue
                handler._send_resp_headers(502, "application/json", route.label, failovers, False)
                handler._write(json.dumps(
                    {"error": {"message": "upstream stream failed"}}).encode())
                srv.note_request(requested, route.label, "stream-error", 0.0, failovers)
                return

            obs = srv.observer.classify(okey, 200, rhdrs, _extract(b"".join(head), ctype),
                                        expected_model=expected)
            latency_ms = int((time.monotonic() - start) * 1000)
            srv.latency_tracker.record(route.label, latency_ms)
            # ── genuine streaming downgrade (obs.pseudo_success) ──────────────
            # Same operator toggle as the non-stream path. With failover_on_downgrade
            # True AND a next provider, fail over BEFORE committing any byte (headers
            # not yet sent) and record the discarded head attempt with count_usage=True
            # (visible, not the old silent double-bill). Otherwise (default, or no next
            # provider) commit and SERVE this completed 200 with X-Charon-Downgrade.
            if obs.pseudo_success and srv.failover_on_downgrade and more:
                srv.observer.record(  # visible, not silent
                    obs, count_usage=True, session=session_id,
                    provider=route.label)
                failovers.append({"provider": route.label, "status": "downgrade",
                                  "reason": obs.note or "served different model"})
                continue
            # commit: stream the buffered head + the remainder (headers now sent —
            # a later read error can only truncate, never fail over).
            handler._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
            full = list(head)
            ok = all(handler._write(c) for c in head)
            # stream_complete: True ONLY if the read loop reached natural EOF (`not c`)
            # with every client write still OK and no exception. A truncated blob —
            # upstream drop (→ except) or a client-write failure (→ ok False) — must
            # NEVER be cached and later served as a whole 200 (DTC BLOCKER #2).
            stream_complete = False
            try:
                while ok:
                    c = resp.read(8192)
                    if not c:
                        stream_complete = True
                        break
                    full.append(c)
                    ok = handler._write(c)
            except Exception:
                pass  # headers committed; partial stream is unavoidable
            full_bytes = b"".join(full)
            served_obs = srv.observer.classify(okey, 200, rhdrs,
                                               _extract(full_bytes, ctype),
                                               expected_model=expected)
            srv.observer.record(served_obs, count_usage=True, session=session_id,
                                provider=route.label)
            latency_ms = int((time.monotonic() - start) * 1000)
            srv.latency_tracker.record(route.label, latency_ms)
            # Cache the streamed 200 (mirrors the non-stream path — only non-stream
            # was cached before SR-2) but ONLY a cleanly-completed, non-downgrade
            # stream: BLOCKER #1 (never cache a downgrade — HIT can't disclose it) +
            # BLOCKER #2 (never cache a truncated blob).
            if (srv.semantic_cache is not None and stream_complete
                    and not served_obs.pseudo_success):
                cache_key = hashlib.sha256(raw_body).hexdigest()
                srv.semantic_cache.set(cache_key, full_bytes, rhdrs, ttl=3600)
            cost = served_obs.usage.cost_usd if served_obs.usage else 0.0
            if srv.spend_limiter is not None:
                srv.spend_limiter.record(_spend_to_record(served_obs, est_cost))
            if srv.balance_tracker is not None:
                srv.balance_tracker.record_spend(route.label, cost, model=requested)
            srv.note_request(requested, route.label, 200, cost, failovers)
            return
        finally:
            srv.inflight_dec(route)
            try:  # release the upstream socket/fd promptly (don't lean on GC)
                resp.close()
            except Exception:
                pass
        return
