"""HTTP serving shell for the observing proxy (ADR-0004 R1).

Wraps ``GatewayProxy.observe`` in a tiny OpenAI-compatible reverse proxy that the
ACP agent points at (its provider ``baseURL`` → this server). For each call the
server forwards to the configured upstream — injecting the real provider key, so
credentials stay in Charon's control plane and never reach the agent — observes
the response (status / usage / returned model), and relays it back unchanged.

Stdlib only (``http.server`` + ``urllib``). This is the serving plumbing on top of
the unit-tested observation core; it is exercised both by an in-process
integration test (mock upstream) and live via a real OpenCode-Go call.
"""
from __future__ import annotations

import collections
import hashlib
import hmac
import http.cookies
import http.server
import json
import os
import socketserver
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass
from urllib.parse import parse_qs, urlsplit

from .cache import SemanticCache
from .consensus import ConsensusRouter
from .guardrails import Guardrails
from .netutil import BROWSER_UA, is_loopback
from .observability import Observability
from .policy_router import PolicyRouter
from .proxy import GatewayProxy
from .quality_scorer import QualityScorer
from .request_inspector import RequestInspector
from .request_normalizer import normalize_messages as _normalize_request_messages
from .response_normalizer import NormalizeMode, ResponseNormalizer
from .session_affinity import SessionAffinity
from .speculative_execution import SpeculativeExecutor
from .spend_limits import SpendLimiter
from .virtual_keys import VirtualKeyManager
from . import console_router

# Facade re-exports (decompose): keep the public import surface resolving
# unchanged from charon.proxy_server for the test suite and callers.
from .proxy_console_assets import _CONSOLE_HTML, _SETUP_HTML, _WORK_HTML
from .proxy_response import _extract, _pre_flight_estimate


@dataclass(frozen=True)
class UpstreamRoute:
    """Where one agent-facing model id is forwarded (multi-provider pools)."""

    upstream_base: str
    api_key: str | None = None
    upstream_model: str | None = None  # rewrite the body's model to this id upstream
    pool_id: str | None = None  # observe under this id (the router's pool id) if set
    provider: str | None = None  # display label for failover visibility (X-Charon-Provider)
    strip_v1: bool | None = None  # per-provider quirk; None → use the server default

    @property
    def label(self) -> str:
        """Human-facing provider id for failover headers/logs — never a secret. Uses
        host[:port] (NOT netloc) so any ``user:pass@`` userinfo in a misconfigured
        base never surfaces in a header/console (P4 review)."""
        if self.provider:
            return self.provider
        parts = urlsplit(self.upstream_base)
        host = parts.hostname or self.upstream_base
        return f"{host}:{parts.port}" if parts.port else host

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


class _ProxyHandler(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.0"  # close-delimited; works for SSE without length

    def log_message(self, *args) -> None:  # keep the coordinator's stdout clean
        pass

    def do_POST(self) -> None:
        self._handle()

    def do_GET(self) -> None:
        self._handle()

    def _json(self, status: int, obj: dict) -> None:
        data = json.dumps(obj).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _html(self, html: str) -> None:
        data = html.encode()
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(data)))
        self._maybe_set_token_cookie()
        self.end_headers()
        try:
            self.wfile.write(data)
        except (BrokenPipeError, ConnectionResetError):
            pass

    def _authorized(self, token: str) -> bool:
        """Bearer token via ``Authorization`` header, ``?token=`` query, or
        ``charon_token`` cookie; constant-time compare to avoid leaking via timing."""
        presented = ""
        auth = self.headers.get("Authorization", "")
        if auth.startswith("Bearer "):
            presented = auth[len("Bearer "):].strip()
        if not presented:
            qs = parse_qs(urlsplit(self.path).query)
            presented = (qs.get("token") or [""])[0]
        if not presented:
            cookie_header = self.headers.get("Cookie", "")
            cookies = http.cookies.SimpleCookie()
            cookies.load(cookie_header)
            cookie_token = cookies.get("charon_token")
            if cookie_token:
                presented = cookie_token.value
        return bool(presented) and hmac.compare_digest(presented, token)

    def _maybe_set_token_cookie(self) -> None:
        """If this request authenticated via ``?token=``, set a short-lived cookie
        so subsequent page loads don't need the token in the URL."""
        v = getattr(self, '_set_token_cookie', None)
        if v:
            self.send_header("Set-Cookie",
                f"charon_token={v}; Path=/; HttpOnly; SameSite=Lax; Max-Age=900")

    # ---- helpers ---------------------------------------------------------

    def _write(self, data: bytes) -> bool:
        """Write to the client; False if the client hung up (so we stop)."""
        try:
            self.wfile.write(data)
            self.wfile.flush()
            return True
        except (BrokenPipeError, ConnectionResetError):
            return False

    def _drain(self, resp) -> bytes:
        out: list[bytes] = []
        try:
            while True:
                c = resp.read(8192)
                if not c:
                    break
                out.append(c)
        except Exception:  # noqa: BLE001
            pass
        return b"".join(out)

    def _send_resp_headers(self, status: int, ctype: str, provider: str | None,
                           failovers: list[dict], downgrade: bool,
                           cache_status: str | None = None,
                           retry_after: int | None = None) -> None:
        """Send status + Content-Type + the failover-visibility headers (ADR D3).

        ``retry_after`` (P1): when truthy and > 0, emit a bounded ``Retry-After``
        so the GATEWAY owns retry cadence on a transient exhaustion (a dual-402
        can never become a client's runaway ~8h exponential backoff). Callers that
        omit it keep byte-identical headers to before."""
        self.send_response(status)
        self.send_header("Content-Type", ctype)
        if provider:
            self.send_header("X-Charon-Provider", provider)
        self.send_header("X-Charon-Failovers", str(len(failovers)))
        if failovers:
            self.send_header("X-Charon-Failover-Reasons",
                             "; ".join(f"{f['provider']}={f['status']}" for f in failovers))
        if downgrade:
            self.send_header("X-Charon-Downgrade", "served a different model than requested")
        if cache_status:  # real header — must precede end_headers (never in the body)
            self.send_header("X-Cache-Status", cache_status)
        if retry_after and retry_after > 0:  # P1: bounded gateway-owned retry cadence
            self.send_header("Retry-After", str(int(retry_after)))
        self._maybe_set_token_cookie()
        self.end_headers()

    def _build_upstream_req(self, srv, route: UpstreamRoute, orig_bj: dict,
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

        path = urlsplit(self.path).path  # PATH ONLY — never forward the query string
        strip_v1 = route.strip_v1 if route.strip_v1 is not None else srv.strip_v1
        if strip_v1 and path.startswith("/v1"):
            path = path[len("/v1"):]  # upstream_base already ends in /v1
        url = route.upstream_base.rstrip("/") + path

        req = urllib.request.Request(url, data=data, method=self.command)
        for hk in self.headers.keys():
            # User-Agent is normalized separately (below) — never forwarded raw.
            if hk.lower() not in _SKIP_HEADERS and hk.lower() != "user-agent":
                req.add_header(hk, self.headers[hk])
        req.add_header("Content-Type", "application/json")
        # Egress identity: forward the agent's real UA (some gateways 403 an unknown
        # one), but replace an absent/library-default UA — "Python-urllib/3.x" trips
        # Cloudflare 1010 (→403). Live-verified.
        client_ua = self.headers.get("User-Agent", "")
        if client_ua and not client_ua.lower().startswith(_BANNED_UA_PREFIXES):
            req.add_header("User-Agent", client_ua)
        else:
            req.add_header("User-Agent", _DEFAULT_UA)
        if route.api_key:
            req.add_header("Authorization", f"Bearer {route.api_key}")
        return req

    def _handle(self) -> None:
        srv: GatewayProxyServer = self.server  # type: ignore[assignment]

        # Anti-DNS-rebinding (security review HIGH): on a loopback bind, reject a Host
        # header that isn't a loopback literal — defeats the rebinding that would
        # otherwise let a web page drive the ungated-default gateway and exfiltrate keys.
        if srv.require_loopback_host:
            hosthdr = self.headers.get("Host", "")
            if hosthdr and not is_loopback(urlsplit("//" + hosthdr).hostname or ""):
                self._json(403, {"error": {"message": "host not allowed"}})
                return

        # Token gate (gateway mode). Default ``token=None`` keeps the bare proxy
        # open — exactly its prior behavior; a set token requires it on every call.
        if srv.token is not None and not self._authorized(srv.token):
            self._json(401, {"error": {"message": "missing or invalid bearer token"}})
            return

        # If auth was via ?token= query param, set a short-lived cookie so
        # subsequent page loads don't need the token in the URL.
        if srv.token is not None:
            qs = parse_qs(urlsplit(self.path).query)
            qt = qs.get("token")
            if qt and qt[0]:
                self._set_token_cookie = srv.token

        # Control-plane dispatch (console/setup/discovery); True = fully served.
        if console_router.try_handle_control_plane(self, srv):
            return

        # Read the client request (size-capped — memory-DoS guard on an exposed bind).
        length = int(self.headers.get("Content-Length") or 0)
        if length > srv.max_body_bytes:
            self._json(413, {"error": {"message": "request body too large"}})
            return
        raw_body = self.rfile.read(length) if length else b""

        # Optional per-session cost attribution (SESSION-COST): a caller (e.g. the
        # benchmark harness) tags its own requests with a self-chosen id so its
        # cumulative cost can be read back in isolation from concurrent gateway
        # traffic — see GatewayProxy.session_usage / GET /charon/cost. Absent
        # header → session=None, meaning "don't attribute" (global counter is
        # unaffected either way).
        session_id = self.headers.get("X-Charon-Session") or None

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
            self._json(502, {"error": {"message": (
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
                self._json(402, {"error": {"message": dec.reason,
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
                self._json(400, {"error": {
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
                self._send_resp_headers(200, ctype, "cache", [], False, cache_status="HIT")
                self._write(cached.content)
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
            req = self._build_upstream_req(srv, route, orig_bj, raw_body)

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
                self._send_resp_headers(502, "application/json", route.label, failovers, False)
                self._write(json.dumps(
                    {"error": {"message": "all upstreams unreachable"}}).encode())
                srv.note_request(requested, route.label, "unreachable", 0.0, failovers)
                return

            ctype = rhdrs.get("Content-Type", "application/json")
            try:
                # ---- non-200 ----
                if status != 200:
                    body_bytes = self._drain(resp)
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
                            self._send_resp_headers(
                                503, "application/json", route.label, failovers, False,
                                retry_after=srv.retry_after_hint(ordered))
                            self._write(json.dumps({"error": {
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
                    self._send_resp_headers(status, ctype, route.label, failovers, False,
                                            retry_after=relay_retry_after)
                    self._write(body_bytes)
                    srv.note_request(requested, route.label, status, 0.0, failovers)
                    return

                # ---- 200, non-streaming: buffer, then check for a silent downgrade ----
                if not is_stream:
                    body_bytes = self._drain(resp)
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
                    self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                    self._write(body_bytes)
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
                    self._send_resp_headers(502, "application/json", route.label, failovers, False)
                    self._write(json.dumps(
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
                self._send_resp_headers(200, ctype, route.label, failovers, obs.pseudo_success)
                full = list(head)
                ok = all(self._write(c) for c in head)
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
                        ok = self._write(c)
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


class GatewayProxyServer(socketserver.ThreadingMixIn, http.server.HTTPServer):
    """A loopback OpenAI-compatible proxy in front of one or many upstreams.

    Single-upstream: pass ``upstream_base`` + ``api_key``. Multi-provider pools
    (failover across providers): pass ``routes`` mapping the agent-facing model id
    to its ``UpstreamRoute`` (base, key, optional upstream model-id rewrite); the
    single upstream, if also given, is the fallback."""

    daemon_threads = True
    allow_reuse_address = True

    def __init__(
        self,
        upstream_base: str | None = None,
        api_key: str | None = None,
        observer: GatewayProxy | None = None,
        routes: dict[str, UpstreamRoute] | None = None,
        host: str = "127.0.0.1",
        port: int = 0,
        fwd_timeout: float = 180.0,
        strip_v1: bool = True,
        token: str | None = None,
        model_ids: list[str] | None = None,
        pools: dict[str, list[UpstreamRoute]] | None = None,
        model_meta: dict[str, dict] | None = None,
        model_pricing: dict[str, dict] | None = None,
        max_body_bytes: int = 10 * 1024 * 1024,
        default_cooldown: float = 60.0,
        max_cooldown_s: float = 120.0,
        failover_log_path: str | None = None,
        failover_on_downgrade: bool = False,
        guardrails: Guardrails | None = None,
        semantic_cache: SemanticCache | None = None,
        response_normalizer: ResponseNormalizer | None = None,
        observability: Observability | None = None,
        quality_scorer: QualityScorer | None = None,
        spend_limiter: SpendLimiter | None = None,
        request_inspector: RequestInspector | None = None,
        session_affinity: SessionAffinity | None = None,
        speculative_executor: SpeculativeExecutor | None = None,
        consensus_router: ConsensusRouter | None = None,
        virtual_key_manager: VirtualKeyManager | None = None,
        policy_router: PolicyRouter | None = None,
    ) -> None:
        super().__init__((host, port), _ProxyHandler)
        self.upstream_base = upstream_base
        self.api_key = api_key
        self.routes = routes or {}
        self.observer = observer or GatewayProxy(model_pricing=model_pricing)
        self.fwd_timeout = fwd_timeout
        self.strip_v1 = strip_v1
        # Anti-DNS-rebinding: when bound to loopback, only accept requests whose Host
        # header is a loopback literal — a rebound attacker domain (Host: evil.com) is
        # rejected, so a malicious web page can't drive the ungated-loopback gateway
        # (security review HIGH). A non-loopback (tokened) bind relies on the token.
        self.require_loopback_host = is_loopback(host)
        # Gateway mode (ADR-0005 P1): a bearer token (None = open) and the
        # agent-facing model ids to serve at /v1/models (None = don't intercept).
        self.token = token
        self.model_ids = model_ids
        # Per-model metadata surfaced in /v1/models (context_window, max_tokens,
        # reasoning, vision, audio) — optional, never carries secrets.
        self.model_meta = model_meta or {}
        # Per-model pricing (cost_input, cost_output) for computing cost_usd when
        # the provider doesn't self-report — optional (SR-5b).
        self.model_pricing = model_pricing or {}
        # P2 failover: model id → ordered (cost-ranked) candidate chain; a
        # provider-keyed cooldown with Retry-After expiry (R7/R10c); and a bounded
        # in-memory failover event log (+ optional JSONL file) for visibility (D3).
        self.pools = pools or {}
        self.max_body_bytes = max_body_bytes
        self.default_cooldown = default_cooldown
        # Ceiling on any single cooldown, including a provider-reported Retry-After
        # (cooldown-anchor-demotion red): an upstream that returns an extreme backoff
        # (observed ~3420s / 57min) must never sideline a provider — anchor or not —
        # for tens of minutes. set_cooldown() clamps to this; the default-60s no-
        # Retry-After path is unaffected (60 < 120).
        self.max_cooldown_s = max_cooldown_s
        self.failover_log_path = failover_log_path
        # Operator toggle (SR-2): on a GENUINE silent downgrade, fail over to the next
        # provider to try for the asked model instead of serving the downgrade. The
        # discarded attempt is recorded with count_usage=True (visible, not the old
        # silent double-bill). Default False → serve the downgrade once, billed once.
        self.failover_on_downgrade = failover_on_downgrade
        self.guardrails = guardrails
        self.semantic_cache = semantic_cache
        self.response_normalizer = response_normalizer
        self.observability = observability
        self.quality_scorer = quality_scorer
        self.spend_limiter = spend_limiter
        self.request_inspector = request_inspector
        self.session_affinity = session_affinity
        self.speculative_executor = speculative_executor
        self.consensus_router = consensus_router
        self.virtual_key_manager = virtual_key_manager
        self.policy_router = policy_router
        self._cooldown: dict[str, float] = {}
        self._cooldown_lock = threading.Lock()
        self.failover_events: collections.deque[dict] = collections.deque(maxlen=200)
        # per-provider counters for the console (P4): label → served/failed/cost.
        self.provider_stats: dict[str, dict] = {}
        # Optional web-setup write handler (Setup phase): callable(action, payload) ->
        # (status, dict). None (default) keeps the console READ-ONLY. The gateway wires
        # this only for the user-config-dir flow; it writes config + reloads routes.
        self.setup_handler = None

    def route_for(self, model: str) -> UpstreamRoute | None:
        """Which upstream serves ``model``: an explicit route, else the single
        upstream fallback, else None (no route → 502)."""
        if model in self.routes:
            return self.routes[model]
        if self.upstream_base:
            return UpstreamRoute(self.upstream_base, self.api_key)
        return None

    def apply_routes(self, routes: dict, pools: dict, model_ids: list[str],
                     model_meta: dict[str, dict] | None = None,
                     model_pricing: dict[str, dict] | None = None) -> None:
        """Atomically swap the live routing config (web-setup hot-reload) under the
        same lock ``chain_for`` reads — so an in-flight request never sees a torn
        (mixed old/new) routes-vs-pools view (security review LOW). Also refreshes
        the observer's pricing so a live config reload updates cost_usd too (SR-5b)."""
        with self._cooldown_lock:
            self.routes = routes
            self.pools = pools
            self.model_ids = model_ids
            self.model_meta = model_meta or {}
            self.model_pricing = model_pricing or {}
            self.observer.set_pricing(self.model_pricing)

    def chain_for(self, model: str) -> list[UpstreamRoute]:
        """The ordered failover chain for ``model``: a configured pool (multiple
        cost-ranked providers), else a single route/upstream (a chain of one), else
        ``[]`` (no route → 502). A 1-element chain never fails over — exactly the
        pre-P2 single-upstream behavior."""
        with self._cooldown_lock:  # paired with apply_routes → consistent snapshot
            if model in self.pools:
                return list(self.pools[model])
            if (self.policy_router is not None and model.startswith("policy/")):
                policy_name = model[len("policy/"):]
                return self.policy_router.resolve(policy_name, self.routes,
                                                  self.pools)
            single = self.route_for(model)
            return [single] if single is not None else []

    def order_by_cooldown(self, chain: list[UpstreamRoute]) -> list[UpstreamRoute]:
        """Try providers NOT in active cooldown first; keep cooled ones as a
        last resort so a stale cooldown never permanently blocks a request (R7).
        Within the cooled bucket, order by soonest-to-recover first (ascending
        remaining cooldown) — cooldown-anchor-demotion red: among several cooled
        providers, prefer the one closest to coming back rather than an arbitrary
        (insertion) order."""
        now = time.monotonic()
        with self._cooldown_lock:
            fresh = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) <= now]
            cooled = [r for r in chain if self._cooldown.get(r.upstream_base, 0.0) > now]
            cooled.sort(key=lambda r: self._cooldown.get(r.upstream_base, 0.0))
        return fresh + cooled

    def retry_after_hint(self, chain: list[UpstreamRoute]) -> int:
        """Seconds until the soonest member of ``chain`` recovers — a bounded
        ``Retry-After`` for the terminal 503 (P1). Reads the same ``_cooldown``
        map as ``order_by_cooldown`` (under the same lock): the soonest remaining
        cooldown among cooled members, falling back to ``default_cooldown`` when
        none is cooled, clamped to ``[1, max_cooldown_s]``. No routing/spend
        effect — purely a header hint."""
        now = time.monotonic()
        with self._cooldown_lock:
            remaining = [self._cooldown[r.upstream_base] - now
                         for r in chain
                         if self._cooldown.get(r.upstream_base, 0.0) > now]
        soonest = min(remaining) if remaining else self.default_cooldown
        return int(max(1.0, min(soonest, self.max_cooldown_s)))

    def set_cooldown(self, route: UpstreamRoute, retry_after: int | None) -> None:
        """Mark a provider out-of-capacity until ``Retry-After`` (or a default),
        keyed by provider (upstream_base) — a 429 is account-level, so all of that
        provider's models are skipped, not just the one (R10c). The Retry-After-
        derived duration is clamped to ``max_cooldown_s`` (cooldown-anchor-demotion
        red): upstreams occasionally report extreme backoffs (observed ~3420s /
        57min) that would otherwise sideline a provider — anchor or not — for far
        longer than a transient rate limit warrants."""
        secs = float(retry_after) if (retry_after and retry_after > 0) else self.default_cooldown
        secs = min(secs, self.max_cooldown_s)
        with self._cooldown_lock:
            self._cooldown[route.upstream_base] = time.monotonic() + secs

    def note_request(self, model: str, served_by: str, status, cost: float,
                     failovers: list[dict]) -> None:
        """Account one finished request (called on EVERY exit path): bump the served
        provider's served/cost counters and each failed-over provider's failure
        counter (per-provider visibility, D3/P4), and — when failover happened —
        append a failover event (ring buffer + optional JSONL)."""
        def _slot(stats, label):
            return stats.setdefault(label, {"served": 0, "failed": 0, "errors": 0,
                                            "cost": 0.0, "last_status": None})
        with self._cooldown_lock:
            s = _slot(self.provider_stats, served_by)
            if status == 200:
                s["served"] += 1   # a real success
                s["cost"] += cost
            else:
                s["errors"] += 1   # terminal failure/relayed error — NOT a success (P4 review)
            s["last_status"] = status
            for f in failovers:
                fs = _slot(self.provider_stats, f["provider"])
                fs["failed"] += 1
                fs["last_status"] = f["status"]
            if failovers:
                self.failover_events.append(
                    {"model": model, "served_by": served_by, "status": status,
                     "failovers": list(failovers)})
        if failovers and self.failover_log_path:
            try:
                with open(self.failover_log_path, "a", encoding="utf-8") as fh:
                    fh.write(json.dumps(
                        {"model": model, "served_by": served_by, "failovers": failovers}) + "\n")
            except OSError:
                pass

    def status_snapshot(self) -> dict:
        """A JSON-able view for the console (P4): pool config, per-provider stats +
        cooldown, cumulative usage, and the recent failover events."""
        now = time.monotonic()
        with self._cooldown_lock:
            cooled = {base: round(t - now, 1) for base, t in self._cooldown.items() if t > now}
            stats = {k: dict(v) for k, v in self.provider_stats.items()}
            events = list(self.failover_events)
        pools = {vid: [r.label for r in chain] for vid, chain in self.pools.items()}
        for mid, r in self.routes.items():
            pools.setdefault(mid, [r.label])
        # map a provider label → seconds of cooldown remaining (via its base url)
        label_cooldown: dict[str, float] = {}
        for chain in list(self.pools.values()) + [[r] for r in self.routes.values()]:
            for r in chain:
                if r.upstream_base in cooled:
                    label_cooldown[r.label] = cooled[r.upstream_base]
        u = self.observer.cumulative_usage()
        return {
            "pools": pools,
            "providers": stats,
            "cooldown_seconds": label_cooldown,
            "usage": {"tokens_in": u.tokens_in, "tokens_out": u.tokens_out,
                      "cost_usd": round(u.cost_usd, 6)},
            "recent_failovers": events[-50:],
            # Running build/version (baked into the image by SR-10); None outside a build.
            "build_sha": os.environ.get("CHARON_BUILD_SHA"),
        }

    @property
    def url(self) -> str:
        host, port = self.server_address[0], self.server_address[1]
        if isinstance(host, bytes):
            host = host.decode()
        return f"http://{host}:{port}"

    def serve_in_thread(self) -> threading.Thread:
        t = threading.Thread(target=self.serve_forever, daemon=True)
        t.start()
        return t
