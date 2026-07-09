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
import urllib.error
import urllib.request
from typing import TYPE_CHECKING
from urllib.parse import urlsplit

from .netutil import BROWSER_UA
from .proxy_response import _extract, _pre_flight_estimate
from .request_normalizer import normalize_messages as _normalize_request_messages
from .response_normalizer import NormalizeMode

if TYPE_CHECKING:  # annotation-only; runtime import would be circular via proxy_server
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
        handler._json(502, {"error": {"message": (
            f"no route for model {requested!r} — no providers configured; "
            "run 'charon setup' or open http://127.0.0.1:8080/charon/setup"
        )}})
        return

    # ── spend cap check (before any upstream call) ──────────────────
    if srv.spend_limiter is not None:
        est_tokens = max(len(raw_body) // 4, 100)
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

        try:
            resp = urllib.request.urlopen(req, timeout=srv.fwd_timeout)
            status, rhdrs = resp.status, dict(resp.headers)
        except urllib.error.HTTPError as exc:
            resp, status, rhdrs = exc, exc.code, dict(exc.headers)
        except Exception:  # provider unreachable → fail over (don't 502 outright)
            srv.observer.record(srv.observer.classify(okey, 503, {}, {},
                                expected_model=expected), count_usage=False, session=session_id)
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
                srv.observer.record(obs, count_usage=False, session=session_id)
                if obs.failover:  # 429/402/503/404/401+billing/unsupported → fail over
                    if obs.exhausted:  # account-level exhaustion → cool the
                        srv.set_cooldown(route, obs.retry_after)  # provider (R10c);
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
                        handler._send_resp_headers(
                            503, "application/json", route.label, failovers, False,
                            retry_after=srv.retry_after_hint(ordered))
                        handler._write(json.dumps({"error": {
                            "message": "all providers exhausted",
                            "type": "all_providers_exhausted",
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
                handler._send_resp_headers(status, ctype, route.label, failovers, False,
                                        retry_after=relay_retry_after)
                handler._write(body_bytes)
                srv.note_request(requested, route.label, status, 0.0, failovers)
                return

            # ---- 200, non-streaming: buffer, then check for a silent downgrade ----
            if not is_stream:
                body_bytes = handler._drain(resp)
                observed = _extract(body_bytes, ctype)
                obs = srv.observer.classify(okey, 200, rhdrs, observed, expected_model=expected)
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
                        obs, count_usage=True, session=session_id)
                    failovers.append({"provider": route.label, "status": "downgrade",
                                      "reason": obs.note or "served different model"})
                    continue
                srv.observer.record(  # served → bill usage (R10a)
                    obs, count_usage=True, session=session_id)
                # ── post-response hooks ──────────────────────────
                cost = obs.usage.cost_usd if obs.usage else 0.0
                if srv.response_normalizer is not None:
                    body_bytes = srv.response_normalizer.normalize(
                        body_bytes.decode(errors="replace"),
                        NormalizeMode.STANDARDIZE_MD,
                    ).encode()
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
                    srv.spend_limiter.record(cost if cost > 0 else est_cost)
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
                    count_usage=False, session=session_id)
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
            # ── genuine streaming downgrade (obs.pseudo_success) ──────────────
            # Same operator toggle as the non-stream path. With failover_on_downgrade
            # True AND a next provider, fail over BEFORE committing any byte (headers
            # not yet sent) and record the discarded head attempt with count_usage=True
            # (visible, not the old silent double-bill). Otherwise (default, or no next
            # provider) commit and SERVE this completed 200 with X-Charon-Downgrade.
            if obs.pseudo_success and srv.failover_on_downgrade and more:
                srv.observer.record(  # visible, not silent
                    obs, count_usage=True, session=session_id)
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
            srv.observer.record(served_obs, count_usage=True, session=session_id)
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
                srv.spend_limiter.record(cost if cost > 0 else est_cost)
            srv.note_request(requested, route.label, 200, cost, failovers)
            return
        finally:
            try:  # release the upstream socket/fd promptly (don't lean on GC)
                resp.close()
            except Exception:
                pass
        return
