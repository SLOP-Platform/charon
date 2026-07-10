"""MVP #5 — the observing proxy's HTTP server, end-to-end on loopback.

A mock upstream stands in for a real gateway; the proxy sits in front of it; a
client calls the proxy. Proves the serving shell forwards (injecting the key),
observes (cost on 200, exhaustion on 429), and relays the response unchanged —
the same path a real OpenCode→proxy→OpenCode-Go call takes.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request

from charon.proxy import _SESSION_USAGE_MAX, GatewayProxy, ProxyObservation
from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.types import Usage

_SEEN_AUTH: list[str] = []
_SEEN_UA: list[str] = []  # User-Agent the upstream actually received
_SEEN: list[dict] = []  # (which upstream, model received) for the routing test


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        _SEEN_AUTH.append(self.headers.get("Authorization", ""))
        _SEEN_UA.append(self.headers.get("User-Agent", ""))
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        model = body.get("model", "")
        if model == "ratelimited":
            err = {"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}
            payload = json.dumps(err).encode()
            self.send_response(429)
            self.send_header("Retry-After", "42")
        else:
            payload = json.dumps({
                "model": model,
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 11, "completion_tokens": 7, "cost": 0.01},
            }).encode()
            self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _post(url: str, payload: dict):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
        return exc.code, json.loads(exc.read())


def test_proxy_forwards_observes_and_relays() -> None:
    upstream = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]

    proxy = GatewayProxyServer(upstream_base=f"http://{up_host}:{up_port}",
                               api_key="secret-key")
    proxy.serve_in_thread()
    try:
        # 200: usage observed + cost summed, response relayed unchanged
        _SEEN_AUTH.clear()
        status, body = _post(proxy.url + "/v1/chat/completions", {"model": "kimi-k2.7-code"})
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        assert proxy.observer.cumulative_usage().cost_usd == 0.01
        assert proxy.observer.cumulative_usage().tokens == 18
        assert not proxy.observer.is_exhausted("kimi-k2.7-code")
        # the proxy injected the upstream key (creds in the control plane)
        assert _SEEN_AUTH and _SEEN_AUTH[-1] == "Bearer secret-key"

        # 429: relayed AND recorded as exhaustion for failover
        status, _ = _post(proxy.url + "/v1/chat/completions", {"model": "ratelimited"})
        assert status == 429
        assert proxy.observer.is_exhausted("ratelimited")
    finally:
        proxy.shutdown()
        upstream.shutdown()


def test_proxy_normalizes_banned_user_agent() -> None:
    """The proxy must not leak a library-default UA upstream: Cloudflare bans
    ``Python-urllib`` (error 1010 → 403), which broke Charon's own pre-flight
    probe live. A real agent UA passes through unchanged."""
    upstream = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]
    proxy = GatewayProxyServer(upstream_base=f"http://{up_host}:{up_port}", api_key="k")
    proxy.serve_in_thread()

    def _post_ua(ua: str | None):
        hdrs = {"Content-Type": "application/json"}
        if ua is not None:
            hdrs["User-Agent"] = ua
        req = urllib.request.Request(
            proxy.url + "/v1/chat/completions",
            data=json.dumps({"model": "kimi-k2.7-code"}).encode(),
            headers=hdrs, method="POST")
        urllib.request.urlopen(req, timeout=10).read()

    try:
        _SEEN_UA.clear()
        _post_ua("Python-urllib/3.12")           # library default → normalized
        _post_ua("opencode/1.17.10")              # real agent UA → forwarded as-is
        _post_ua(None)                            # urllib still injects a default
        # library-default UA → normalized to the browser-like default (P5): NOT the
        # old non-browser "charon-proxy/0.1" (Cloudflare 1010), NOT python-urllib.
        assert not _SEEN_UA[0].lower().startswith("python-urllib")
        assert _SEEN_UA[0] != "charon-proxy/0.1"
        assert _SEEN_UA[0].startswith("Mozilla/")
        assert _SEEN_UA[1] == "opencode/1.17.10"
        assert not _SEEN_UA[2].lower().startswith("python-urllib")
        assert _SEEN_UA[2].startswith("Mozilla/")
    finally:
        proxy.shutdown()
        upstream.shutdown()


class _RecordingUpstream(http.server.BaseHTTPRequestHandler):
    tag = "?"

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _SEEN.append({"tag": self.server.tag, "model": body.get("model")})  # type: ignore[attr-defined]
        payload = json.dumps({"model": body.get("model"),
                              "choices": [{"message": {"content": "ok"}}],
                              "usage": {"prompt_tokens": 1}}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _mk_upstream(tag: str):
    srv = _Threaded(("127.0.0.1", 0), _RecordingUpstream)
    srv.tag = tag  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def test_multi_upstream_routes_by_model_and_rewrites() -> None:
    _SEEN.clear()
    up_a, base_a = _mk_upstream("A")
    up_b, base_b = _mk_upstream("B")
    routes = {
        "openrouter/qwen:free": UpstreamRoute(base_a, "key-a", upstream_model="qwen/real:free"),
        "opencode-go/kimi": UpstreamRoute(base_b, "key-b"),
    }
    proxy = GatewayProxyServer(routes=routes)
    proxy.serve_in_thread()
    try:
        _post(proxy.url + "/v1/chat/completions", {"model": "openrouter/qwen:free"})
        _post(proxy.url + "/v1/chat/completions", {"model": "opencode-go/kimi"})
        by_tag = {s["tag"]: s["model"] for s in _SEEN}
        assert by_tag["A"] == "qwen/real:free"   # routed to A + model rewritten
        assert by_tag["B"] == "opencode-go/kimi"  # routed to B, no rewrite
    finally:
        proxy.shutdown()
        up_a.shutdown()
        up_b.shutdown()


def test_unknown_model_with_no_fallback_is_502() -> None:
    proxy = GatewayProxyServer(routes={"known": UpstreamRoute("http://127.0.0.1:1/v1")})
    proxy.serve_in_thread()
    try:
        status, body = _post(proxy.url + "/v1/chat/completions", {"model": "unknown"})
        assert status == 502
        msg = body["error"]["message"]
        assert "no route" in msg
        assert "charon setup" in msg  # remediation hint for fresh users
    finally:
        proxy.shutdown()


def _post_full(url: str, payload: dict):
    """POST and return (status, headers, raw_bytes) — used where the response is a
    stream (non-JSON) or where the failover-visibility headers matter."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, dict(resp.headers), resp.read()


class _DowngradeUpstream(http.server.BaseHTTPRequestHandler):
    """Always answers 200 but echoes a DIFFERENT model family than requested — a
    GENUINE silent downgrade (not a namespace echo). Counts its invocations."""
    calls = 0

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": "haiku",  # asked for "opus" → real downgrade
            "choices": [{"message": {"content": "downgraded-but-complete"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.02},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _CountingUpstream(http.server.BaseHTTPRequestHandler):
    """A well-behaved 200 upstream that counts calls — the alternative provider we
    must NOT fall over to (and re-bill) once a completed 200 is in hand."""
    calls = 0

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = json.dumps({
            "model": body.get("model"),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 5, "completion_tokens": 1, "cost": 0.05},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _spawn(handler_cls):
    handler_cls.calls = 0
    srv = _Threaded(("127.0.0.1", 0), handler_cls)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def test_genuine_downgrade_is_served_not_rebilled() -> None:
    """SR-2: a genuine downgrade is a COMPLETED, already-billed 200. Serve it with
    the X-Charon-Downgrade header instead of discarding it and re-billing the next
    provider — assert the alternative upstream is NEVER called (the double-bill)."""
    down, base_down = _spawn(_DowngradeUpstream)
    alt, base_alt = _spawn(_CountingUpstream)
    proxy = GatewayProxyServer(pools={
        "opus": [UpstreamRoute(base_down, "kd"), UpstreamRoute(base_alt, "ka")],
    })
    proxy.serve_in_thread()
    try:
        status, headers, raw = _post_full(
            proxy.url + "/v1/chat/completions", {"model": "opus"})
        body = json.loads(raw)
        assert status == 200
        # the downgraded-but-complete response is what we served
        assert body["choices"][0]["message"]["content"] == "downgraded-but-complete"
        # the downgrade is disclosed to the client
        assert headers.get("X-Charon-Downgrade")
        # served the first, completed 200 exactly once; NEVER failed over/re-billed
        assert _DowngradeUpstream.calls == 1
        assert _CountingUpstream.calls == 0
        # billed once for the served completion (no discard-and-refetch)
        assert proxy.observer.cumulative_usage().cost_usd == 0.02
    finally:
        proxy.shutdown()
        down.shutdown()
        alt.shutdown()


class _StreamUpstream(http.server.BaseHTTPRequestHandler):
    """Streams a small SSE completion (model in the first chunk, usage in the
    last), like an agent-facing streaming provider. Counts invocations."""
    calls = 0

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = (
            b'data: {"model": "kimi", "choices": [{"delta": {"content": "ok"}}]}\n\n'
            b'data: {"model": "kimi", "usage": {"prompt_tokens": 4, '
            b'"completion_tokens": 2, "cost": 0.03}}\n\n'
            b'data: [DONE]\n\n'
        )
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_streaming_200_populates_cache() -> None:
    """SR-2: streaming 200s must be cacheable too (only non-stream was cached).
    Two identical stream requests → the upstream is hit exactly once; the second
    is served from the semantic cache."""
    from charon.cache import SemanticCache

    up, base = _spawn(_StreamUpstream)
    proxy = GatewayProxyServer(routes={"kimi": UpstreamRoute(base, "k")},
                               semantic_cache=SemanticCache())
    proxy.serve_in_thread()
    try:
        s1, _, raw1 = _post_full(
            proxy.url + "/v1/chat/completions", {"model": "kimi", "stream": True})
        assert s1 == 200
        assert b'"model": "kimi"' in raw1
        assert proxy.semantic_cache.stats().size == 1  # the stream got cached
        # identical second request → cache HIT, upstream not called again
        s2, _, raw2 = _post_full(
            proxy.url + "/v1/chat/completions", {"model": "kimi", "stream": True})
        assert s2 == 200
        assert _StreamUpstream.calls == 1
        assert proxy.semantic_cache.stats().hits >= 1
    finally:
        proxy.shutdown()
        up.shutdown()


def test_downgrade_is_not_cached() -> None:
    """SR-2 DTC BLOCKER #1: a served downgrade must NEVER enter the cache — the
    cache-HIT path can't disclose X-Charon-Downgrade, so a cached downgrade would
    silently re-serve the wrong model for the whole TTL. Enable the cache and assert
    a 2nd byte-identical request re-probes upstream and still discloses the downgrade
    (i.e. it was not served silently from cache)."""
    from charon.cache import SemanticCache

    down, base_down = _spawn(_DowngradeUpstream)
    proxy = GatewayProxyServer(routes={"opus": UpstreamRoute(base_down, "kd")},
                               semantic_cache=SemanticCache())
    proxy.serve_in_thread()
    try:
        s1, h1, _ = _post_full(proxy.url + "/v1/chat/completions", {"model": "opus"})
        assert s1 == 200 and h1.get("X-Charon-Downgrade")
        assert proxy.semantic_cache.stats().size == 0  # the downgrade was NOT cached
        # identical 2nd request → re-probes upstream (not a silent cached wrong-model)
        # and STILL carries the downgrade disclosure.
        s2, h2, _ = _post_full(proxy.url + "/v1/chat/completions", {"model": "opus"})
        assert s2 == 200
        assert _DowngradeUpstream.calls == 2
        assert h2.get("X-Charon-Downgrade")
    finally:
        proxy.shutdown()
        down.shutdown()


class _TruncatedChunkedServer(socketserver.ThreadingMixIn, socketserver.TCPServer):
    daemon_threads = True
    allow_reuse_address = True
    calls = 0


class _TruncatedChunkedHandler(socketserver.BaseRequestHandler):
    """Raw HTTP/1.1 chunked upstream that DROPS mid-body: it sends one large first
    chunk carrying `model` (so the proxy commits the head), then a chunk header
    promising more bytes than it delivers before closing — the proxy's next read
    RAISES IncompleteRead (a genuine upstream drop, not a clean EOF). The truncated
    blob must NEVER be cached (DTC BLOCKER #2)."""

    def handle(self) -> None:
        type(self.server).calls += 1  # type: ignore[attr-defined]
        data = b""
        while b"\r\n\r\n" not in data:  # consume request headers
            chunk = self.request.recv(4096)
            if not chunk:
                return
            data += chunk
        # First chunk is EXACTLY one 8192-byte read: the proxy's read returns the
        # whole (parseable) chunk carrying `model` at the chunk boundary and commits
        # the head, WITHOUT greedily crossing into the truncated 2nd chunk.
        prefix = b'data: {"model": "kimi", "choices": [{"delta": {"content": "'
        suffix = b'"}}]}\n\n'
        first = prefix + b"x" * (8192 - len(prefix) - len(suffix)) + suffix
        out = (b"HTTP/1.1 200 OK\r\nContent-Type: text/event-stream\r\n"
               b"Transfer-Encoding: chunked\r\n\r\n")
        out += hex(len(first))[2:].encode() + b"\r\n" + first + b"\r\n"
        out += b"3e7\r\npartial"  # promise 0x3e7=999 bytes, send 7, then close → drop
        self.request.sendall(out)


def test_truncated_stream_is_not_cached() -> None:
    """SR-2 DTC BLOCKER #2: a stream that ends via an upstream drop (read raises),
    not a clean EOF, is TRUNCATED — it must never be cached and later served as a
    complete 200."""
    from charon.cache import SemanticCache

    _TruncatedChunkedServer.calls = 0
    up = _TruncatedChunkedServer(("127.0.0.1", 0), _TruncatedChunkedHandler)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"
    proxy = GatewayProxyServer(routes={"kimi": UpstreamRoute(base, "k")},
                               semantic_cache=SemanticCache())
    proxy.serve_in_thread()
    try:
        s1, _, raw1 = _post_full(
            proxy.url + "/v1/chat/completions", {"model": "kimi", "stream": True})
        assert s1 == 200
        assert b'"model": "kimi"' in raw1  # the head was served to the client
        assert proxy.semantic_cache.stats().size == 0  # truncated blob NOT cached
        # identical 2nd request → re-probes upstream (no partial served from cache)
        _post_full(proxy.url + "/v1/chat/completions",
                   {"model": "kimi", "stream": True})
        assert _TruncatedChunkedServer.calls == 2
    finally:
        proxy.shutdown()
        up.shutdown()


def test_failover_on_downgrade_toggle_fails_over_and_bills_visibly() -> None:
    """SR-2 toggle True: a genuine downgrade FAILS OVER to the next provider (to try
    for the asked model) AND the discarded downgrade attempt is recorded with
    count_usage=True — the honest/VISIBLE accounting, not the old silent double-bill.
    The billed total = the discarded downgrade (0.02) + the served alt (0.05)."""
    down, base_down = _spawn(_DowngradeUpstream)
    alt, base_alt = _spawn(_CountingUpstream)
    proxy = GatewayProxyServer(
        pools={"opus": [UpstreamRoute(base_down, "kd"), UpstreamRoute(base_alt, "ka")]},
        failover_on_downgrade=True)
    proxy.serve_in_thread()
    try:
        status, headers, raw = _post_full(
            proxy.url + "/v1/chat/completions", {"model": "opus"})
        body = json.loads(raw)
        assert status == 200
        # failed over to the alternative provider and served ITS honest response
        assert body["choices"][0]["message"]["content"] == "ok"
        assert _DowngradeUpstream.calls == 1
        assert _CountingUpstream.calls == 1
        # the failover was disclosed to the client
        assert int(headers.get("X-Charon-Failovers", "0")) == 1
        # BOTH attempts billed — the discarded downgrade is VISIBLE (count_usage=True),
        # not the old silent count_usage=False that hid the double-bill.
        assert proxy.observer.cumulative_usage().cost_usd == 0.02 + 0.05
    finally:
        proxy.shutdown()
        down.shutdown()
        alt.shutdown()


def test_status_snapshot_surfaces_build_sha(monkeypatch) -> None:
    """SR-10 rider: /charon/status exposes the running build via CHARON_BUILD_SHA."""
    proxy = GatewayProxyServer(routes={"m": UpstreamRoute("http://127.0.0.1:1/v1")})
    try:
        monkeypatch.setenv("CHARON_BUILD_SHA", "deadbeef123")
        assert proxy.status_snapshot()["build_sha"] == "deadbeef123"
        monkeypatch.delenv("CHARON_BUILD_SHA", raising=False)
        assert proxy.status_snapshot()["build_sha"] is None
    finally:
        proxy.server_close()


class _NoCostUpstream(http.server.BaseHTTPRequestHandler):
    """Returns 200 with usage but NO cost field — the provider didn't self-report."""
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": "m",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_zero_cost_response_still_advances_spend_cap(monkeypatch, tmp_path) -> None:
    """SR-7: a zero-priced but SERVED response records the pre-flight estimated
    cost so the universal monthly cap can't be bypassed by uncosted calls."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon.spend_limits import SpendLimiter

    up = _Threaded(("127.0.0.1", 0), _NoCostUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    limiter = SpendLimiter(monthly_limit_usd=100.0)
    proxy = GatewayProxyServer(routes={"m": UpstreamRoute(base, "k")},
                                spend_limiter=limiter)
    proxy.serve_in_thread()
    try:
        # a 200 with no cost field → computed cost is 0
        status, body = _post(proxy.url + "/v1/chat/completions", {"model": "m"})
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        # the spend cap must have advanced despite zero computed cost
        assert limiter._spent_usd > 0
        assert limiter.remaining() < 100.0
    finally:
        proxy.shutdown()
        up.shutdown()


def test_priced_zero_provider_cost_advances_cap_with_real_cost(monkeypatch, tmp_path) -> None:
    """SR-5b + SR-7: a served response whose provider reports NO cost but whose model
    IS priced advances the universal spend cap by the REAL computed cost (per-token),
    not the nominal pre-flight floor — SR-7's guarantee holds with real cost."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon.spend_limits import SpendLimiter

    up = _Threaded(("127.0.0.1", 0), _NoCostUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    limiter = SpendLimiter(monthly_limit_usd=100.0)
    # _NoCostUpstream returns prompt_tokens=10, completion_tokens=5 with no cost.
    # Priced at 0.001/token → computed cost = 10*0.001 + 5*0.001 = 0.015.
    proxy = GatewayProxyServer(
        routes={"m": UpstreamRoute(base, "k")},
        spend_limiter=limiter,
        model_pricing={"m": {"cost_input": 0.001, "cost_output": 0.001}})
    proxy.serve_in_thread()
    try:
        status, body = _post(proxy.url + "/v1/chat/completions", {"model": "m"})
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        # cap advanced by the REAL computed cost, not the nominal floor (~1.5e-4).
        assert abs(limiter._spent_usd - 0.015) < 1e-9
    finally:
        proxy.shutdown()
        up.shutdown()


def test_pre_flight_estimate_resolves_namespaced_pricing() -> None:
    """SR-5b: the pre-flight spend estimate resolves a namespaced model id against
    pricing stored under the bare final segment (parity with _lookup_pricing), not
    the nominal per-token floor."""
    from charon.proxy_server import _pre_flight_estimate

    srv = GatewayProxyServer(
        routes={"deepseek-v4-pro": UpstreamRoute("http://127.0.0.1:1/v1", "k")},
        model_pricing={"deepseek-v4-pro": {"cost_input": 0.00002,
                                           "cost_output": 0.00004}})
    try:
        est = _pre_flight_estimate("deepseek/deepseek-v4-pro", 1000, srv)
        # rate = max(2e-5, 4e-5) = 4e-5 → 1000 * 4e-5 = 0.04, not the 0.0000015 floor.
        assert abs(est - 0.04) < 1e-9
        # an unknown model falls back to the nominal floor.
        floor = _pre_flight_estimate("totally-unknown", 1000, srv)
        assert abs(floor - 1000 * 0.0000015) < 1e-12
    finally:
        srv.server_close()


# ---------------------------------------------------------------------------
# #5 — strip output-only fields (reasoning_content) from inbound messages
# ---------------------------------------------------------------------------

# Captured messages the upstream actually received, for assertion.
_SEEN_MESSAGES: list[list[dict]] = []


class _MessageCapturingUpstream(http.server.BaseHTTPRequestHandler):
    """A 200 upstream that records the messages array it actually received."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _SEEN_MESSAGES.append(body.get("messages", []))
        payload = json.dumps({
            "model": body.get("model", ""),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_proxy_strips_reasoning_content_before_forwarding() -> None:
    """#5: the proxy MUST strip assistant ``reasoning_content`` from the
    forwarded body — another provider (Groq-style) rejects it otherwise."""
    _SEEN_MESSAGES.clear()
    up = _Threaded(("127.0.0.1", 0), _MessageCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    proxy = GatewayProxyServer(routes={"m": UpstreamRoute(base, "k")})
    proxy.serve_in_thread()
    try:
        status, _ = _post(proxy.url + "/v1/chat/completions", {
            "model": "m",
            "messages": [
                {"role": "user", "content": "hi"},
                {"role": "assistant", "content": "hello",
                 "reasoning_content": "internal thoughts"},
                {"role": "user", "content": "again"},
            ],
        })
        assert status == 200
        assert len(_SEEN_MESSAGES) == 1
        forwarded = _SEEN_MESSAGES[0]
        assert forwarded[1] == {"role": "assistant", "content": "hello"}
        assert "reasoning_content" not in forwarded[1]
    finally:
        proxy.shutdown()
        up.shutdown()


def test_proxy_preserves_tool_calls_when_stripping() -> None:
    """#5: tool_calls on assistant messages survive the strip — only
    output-only fields are removed."""
    _SEEN_MESSAGES.clear()
    up = _Threaded(("127.0.0.1", 0), _MessageCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    proxy = GatewayProxyServer(routes={"m": UpstreamRoute(base, "k")})
    proxy.serve_in_thread()
    try:
        status, _ = _post(proxy.url + "/v1/chat/completions", {
            "model": "m",
            "messages": [
                {
                    "role": "assistant",
                    "content": None,
                    "reasoning_content": "thinking",
                    "tool_calls": [
                        {"id": "call_1", "type": "function",
                         "function": {"name": "f", "arguments": "{}"}},
                    ],
                },
            ],
        })
        assert status == 200
        forwarded = _SEEN_MESSAGES[0]
        assert "reasoning_content" not in forwarded[0]
        assert forwarded[0]["tool_calls"] == [
            {"id": "call_1", "type": "function",
             "function": {"name": "f", "arguments": "{}"}},
        ]
    finally:
        proxy.shutdown()
        up.shutdown()


def _post_with_session(url: str, payload: dict, session: str | None):
    headers = {"Content-Type": "application/json"}
    if session is not None:
        headers["X-Charon-Session"] = session
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read())


def test_session_cost_isolated_across_sessions_and_from_global() -> None:
    """SESSION-COST: a caller-supplied ``X-Charon-Session`` header attributes cost
    to a private per-session bucket that concurrent traffic under a DIFFERENT (or
    absent) session id can never pollute — the gap the benchmark hit reading the
    gateway-global ``usage.cost_usd`` while other traffic shared the same gateway.
    The global counter keeps summing everything, unchanged."""
    upstream = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]

    proxy = GatewayProxyServer(upstream_base=f"http://{up_host}:{up_port}",
                               api_key="secret-key", model_ids=["kimi-k2.7-code"])
    proxy.serve_in_thread()
    try:
        # session "a" served twice ($0.01 each), session "b" once, and one
        # request with NO session header at all (must not land in either bucket).
        _post_with_session(proxy.url + "/v1/chat/completions",
                          {"model": "kimi-k2.7-code"}, "a")
        _post_with_session(proxy.url + "/v1/chat/completions",
                          {"model": "kimi-k2.7-code"}, "b")
        _post_with_session(proxy.url + "/v1/chat/completions",
                          {"model": "kimi-k2.7-code"}, "a")
        _post_with_session(proxy.url + "/v1/chat/completions",
                          {"model": "kimi-k2.7-code"}, None)

        usage_a = proxy.observer.session_usage("a")
        usage_b = proxy.observer.session_usage("b")
        assert round(usage_a.cost_usd, 6) == 0.02
        assert round(usage_b.cost_usd, 6) == 0.01
        # an unseen session id is zero, never an error / never another session's total
        assert proxy.observer.session_usage("never-seen").cost_usd == 0.0
        # global cumulative keeps summing EVERYTHING (4 requests × $0.01), unaffected
        # by session tracking — a pure read-only addition, not a billing change.
        assert round(proxy.observer.cumulative_usage().cost_usd, 6) == 0.04

        # the read-only GET /charon/cost?session=<id> surface agrees with the
        # in-process reader, and omitting ?session= falls back to the global total.
        with urllib.request.urlopen(proxy.url + "/charon/cost?session=a", timeout=10) as r:
            body = json.loads(r.read())
        assert body == {"session": "a", "tokens_in": 22, "tokens_out": 14,
                        "cost_usd": 0.02}
        with urllib.request.urlopen(proxy.url + "/charon/cost?session=b", timeout=10) as r:
            body_b = json.loads(r.read())
        assert body_b["cost_usd"] == 0.01
        with urllib.request.urlopen(proxy.url + "/charon/cost", timeout=10) as r:
            body_global = json.loads(r.read())
        assert body_global["session"] is None
        assert body_global["cost_usd"] == 0.04
    finally:
        proxy.shutdown()
        upstream.shutdown()


def _record_session(observer: GatewayProxy, session: str, cost: float = 0.01) -> None:
    obs = ProxyObservation(
        requested_model="m", returned_model="m", status=200,
        exhausted=False, pseudo_success=False,
        usage=Usage(tokens_in=1, tokens_out=1, cost_usd=cost),
    )
    observer.record(obs, count_usage=True, session=session)


def test_session_usage_bounded_lru_eviction() -> None:
    """SESSION-COST bucket is keyed by the caller-supplied ``X-Charon-Session``
    header on an open-by-default gateway — an unbounded dict there is a
    memory-leak / DoS vector (a client can mint unlimited distinct session ids).
    ``_session_usage`` must therefore be a bounded LRU: inserting more than
    ``_SESSION_USAGE_MAX`` distinct ids evicts the OLDEST (least-recently-used),
    while a session touched recently survives."""
    observer = GatewayProxy()

    # Fill to the cap.
    for i in range(_SESSION_USAGE_MAX):
        _record_session(observer, f"s{i}")
    assert len(observer._session_usage) == _SESSION_USAGE_MAX

    # Touch "s0" (the oldest) again so it becomes most-recently-used, then push
    # one brand-new session past the cap — the LRU evicted must be "s1" (the
    # next-oldest untouched entry), NOT "s0".
    _record_session(observer, "s0")
    _record_session(observer, "s-new")

    assert len(observer._session_usage) == _SESSION_USAGE_MAX
    assert observer.session_usage("s0").cost_usd > 0.0  # recently used -> survives
    assert observer.session_usage("s1").cost_usd == 0.0  # oldest untouched -> evicted
    assert observer.session_usage("s-new").cost_usd > 0.0  # newest -> present

    # Isolation still holds under eviction pressure: two live (unevicted)
    # sessions never see each other's cost.
    _record_session(observer, "alive-a", cost=0.02)
    _record_session(observer, "alive-b", cost=0.05)
    assert round(observer.session_usage("alive-a").cost_usd, 6) == 0.02
    assert round(observer.session_usage("alive-b").cost_usd, 6) == 0.05


def test_proxy_forwards_normal_body_unchanged() -> None:
    """#5: a body with no output-only fields is forwarded verbatim."""
    _SEEN_MESSAGES.clear()
    up = _Threaded(("127.0.0.1", 0), _MessageCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    proxy = GatewayProxyServer(routes={"m": UpstreamRoute(base, "k")})
    proxy.serve_in_thread()
    try:
        original = [
            {"role": "system", "content": "be helpful"},
            {"role": "user", "content": "hello"},
        ]
        status, _ = _post(proxy.url + "/v1/chat/completions", {
            "model": "m",
            "messages": original,
        })
        assert status == 200
        assert _SEEN_MESSAGES[0] == original
    finally:
        proxy.shutdown()
        up.shutdown()



# ── P1: bounded Retry-After on terminal 503 / 402·429·503 relays ────────────

def _post_capture(url: str, payload: dict):
    """POST and return (status, headers, raw_bytes) even for a non-2xx — needed
    to inspect the Retry-After header on a 503/402/429/4xx response."""
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, dict(resp.headers), resp.read()
    except urllib.error.HTTPError as exc:  # type: ignore[name-defined]
        return exc.code, dict(exc.headers), exc.read()


class _PaymentRequiredUpstream(http.server.BaseHTTPRequestHandler):
    """Always 402 (out of balance) — the dual-402 exhaustion case."""
    calls = 0

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({"error": {"message": "insufficient balance"}}).encode()
        self.send_response(402)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _RateLimitHugeRetryUpstream(http.server.BaseHTTPRequestHandler):
    """Single upstream 429 advertising an extreme Retry-After (3420s ≈ 57min) —
    the gateway must re-bound it to <= max_cooldown_s before relaying."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({"error": {"message": "rate limited"}}).encode()
        self.send_response(429)
        self.send_header("Retry-After", "3420")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ClientErrorUpstream(http.server.BaseHTTPRequestHandler):
    """Relays a client/auth error whose code is encoded in the requested model
    (``err400``/``err401``/``err403``) — these must NOT carry a Retry-After."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        code = int(str(body.get("model", "err400")).replace("err", ""))
        payload = json.dumps({"error": {"message": "client error"}}).encode()
        self.send_response(code)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_dual_402_terminal_503_carries_bounded_retry_after() -> None:
    """P1: a pool whose members all 402 → terminal 503 must carry a
    gateway-owned, integer, bounded Retry-After (1 ≤ v ≤ 120 = max_cooldown_s) so
    a Retry-After-respecting client never falls into its own ~8h backoff."""
    a, base_a = _spawn(_PaymentRequiredUpstream)
    b, base_b = _spawn(_PaymentRequiredUpstream)
    proxy = GatewayProxyServer(pools={
        "gpt-5.4": [UpstreamRoute(base_a, "ka"), UpstreamRoute(base_b, "kb")],
    })
    proxy.serve_in_thread()
    try:
        status, headers, raw = _post_capture(
            proxy.url + "/v1/chat/completions", {"model": "gpt-5.4"})
        assert status == 503
        assert json.loads(raw)["error"]["type"] == "all_providers_exhausted"
        ra = headers.get("Retry-After")
        assert ra is not None, "terminal 503 must carry a Retry-After"
        assert ra == str(int(ra))          # integer-valued
        assert 1 <= int(ra) <= 120         # bounded to max_cooldown_s
    finally:
        proxy.shutdown()
        a.shutdown()
        b.shutdown()


def test_single_upstream_429_retry_after_is_clamped() -> None:
    """P1: a single-upstream 429 whose upstream Retry-After is 3420 is relayed
    with the header clamped to <= 120 (max_cooldown_s) — the gateway never lets a
    provider's extreme backoff stall the client."""
    up, base = _spawn(_RateLimitHugeRetryUpstream)
    proxy = GatewayProxyServer(upstream_base=base, api_key="k")
    proxy.serve_in_thread()
    try:
        status, headers, _ = _post_capture(
            proxy.url + "/v1/chat/completions", {"model": "anything"})
        assert status == 429
        ra = headers.get("Retry-After")
        assert ra is not None
        assert int(ra) <= 120
        assert int(ra) >= 1
    finally:
        proxy.shutdown()
        up.shutdown()


def test_client_error_relay_has_no_retry_after() -> None:
    """P1: a 400/401/403 relay is a client/auth error — retrying does not help,
    so NO Retry-After header is emitted."""
    up, base = _spawn(_ClientErrorUpstream)
    proxy = GatewayProxyServer(upstream_base=base, api_key="k")
    proxy.serve_in_thread()
    try:
        for code in ("err400", "err401", "err403"):
            status, headers, _ = _post_capture(
                proxy.url + "/v1/chat/completions", {"model": code})
            assert status == int(code.replace("err", ""))
            assert "Retry-After" not in headers, f"{code} must not carry Retry-After"
    finally:
        proxy.shutdown()
        up.shutdown()


def test_serve_path_default_ua_is_browser_like() -> None:
    """P5: with no client UA, the upstream request carries the shared browser-like
    default (not the old non-browser 'charon-proxy/0.1', not python-urllib) so a
    Cloudflare-fronted provider (groq/cerebras/together) is not 1010-blocked."""
    upstream = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=upstream.serve_forever, daemon=True).start()
    up_host, up_port = upstream.server_address[0], upstream.server_address[1]
    proxy = GatewayProxyServer(upstream_base=f"http://{up_host}:{up_port}", api_key="k")
    proxy.serve_in_thread()
    try:
        _SEEN_UA.clear()
        # no User-Agent header supplied → serve-path falls back to _DEFAULT_UA
        req = urllib.request.Request(
            proxy.url + "/v1/chat/completions",
            data=json.dumps({"model": "kimi-k2.7-code"}).encode(),
            headers={"Content-Type": "application/json"}, method="POST")
        # strip urllib's own default so the proxy sees the absent-UA path
        req.add_unredirected_header("User-Agent", "python-urllib/3.12")
        urllib.request.urlopen(req, timeout=10).read()
        seen = _SEEN_UA[-1]
        assert seen != "charon-proxy/0.1"
        assert not seen.lower().startswith("python-urllib")
        assert seen.startswith("Mozilla/")
    finally:
        proxy.shutdown()
        upstream.shutdown()


# ── SR-6: Anthropic prompt-cache breakpoint injection ──────────────────────────
# Captured FULL request bodies the upstream actually received, for byte-level
# pass-through / enrichment assertions.
_SEEN_BODIES: list[dict] = []

# A system prompt over the ~2048-token (≈8192-char) cacheable minimum.
_SR6_BIG_SYSTEM = "You are a meticulous coding assistant. " * 400


class _BodyCapturingUpstream(http.server.BaseHTTPRequestHandler):
    """A 200 upstream that records the entire JSON body it received."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        _SEEN_BODIES.append(body)
        payload = json.dumps({
            "model": body.get("model", ""),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _anthropic_body(system):
    return {
        "model": "claude-x",
        "system": system,
        "messages": [{"role": "user", "content": "hi"}],
    }


def test_anthropic_wire_route_gets_one_cache_breakpoint() -> None:
    """An anthropic-wire route with a large stable prefix receives exactly one
    cache_control breakpoint on the last system block (flag default ON)."""
    _SEEN_BODIES.clear()
    up = _Threaded(("127.0.0.1", 0), _BodyCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"
    proxy = GatewayProxyServer(
        routes={"claude-x": UpstreamRoute(base, "k", wire="anthropic")})
    proxy.serve_in_thread()
    try:
        status, _ = _post(proxy.url + "/v1/chat/completions",
                          _anthropic_body([{"type": "text", "text": _SR6_BIG_SYSTEM}]))
        assert status == 200
        fwd = _SEEN_BODIES[-1]
        assert fwd["system"][-1]["cache_control"] == {"type": "ephemeral"}
    finally:
        proxy.shutdown()
        up.shutdown()


def test_openai_wire_route_is_byte_for_byte_passthrough() -> None:
    """Regression guard: an OpenAI-wire route (the default) is NEVER enriched —
    even with a large system block it forwards no cache_control."""
    _SEEN_BODIES.clear()
    up = _Threaded(("127.0.0.1", 0), _BodyCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"
    # default wire == "openai"
    proxy = GatewayProxyServer(routes={"claude-x": UpstreamRoute(base, "k")})
    proxy.serve_in_thread()
    try:
        status, _ = _post(proxy.url + "/v1/chat/completions",
                          _anthropic_body([{"type": "text", "text": _SR6_BIG_SYSTEM}]))
        assert status == 200
        fwd = _SEEN_BODIES[-1]
        assert "cache_control" not in fwd["system"][-1]
    finally:
        proxy.shutdown()
        up.shutdown()


def test_flag_off_leaves_anthropic_body_unenriched() -> None:
    """With anthropic_prompt_cache=False an anthropic-wire body is forwarded
    without a breakpoint (byte-identical passthrough)."""
    _SEEN_BODIES.clear()
    up = _Threaded(("127.0.0.1", 0), _BodyCapturingUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"
    proxy = GatewayProxyServer(
        routes={"claude-x": UpstreamRoute(base, "k", wire="anthropic")},
        anthropic_prompt_cache=False)
    proxy.serve_in_thread()
    try:
        status, _ = _post(proxy.url + "/v1/chat/completions",
                          _anthropic_body([{"type": "text", "text": _SR6_BIG_SYSTEM}]))
        assert status == 200
        fwd = _SEEN_BODIES[-1]
        assert "cache_control" not in fwd["system"][-1]
    finally:
        proxy.shutdown()
        up.shutdown()


def test_upstream_route_wire_defaults_openai() -> None:
    assert UpstreamRoute("http://x/v1").wire == "openai"
    assert UpstreamRoute("http://x/v1", wire="anthropic").wire == "anthropic"


# ── RESPONSE-ADAPTER-UNIVERSAL: per-provider response-shape adapter ──────────

class _ClineWrappedUpstream(http.server.BaseHTTPRequestHandler):
    """Emulates cline-pass: a NON-streaming 200 whose body is wrapped as
    {"data": <openai obj>, "success": true} with NO top-level choices/usage."""
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        inner = {
            "id": "cmpl-cline",
            "object": "chat.completion",
            "model": body.get("model"),
            "choices": [{"index": 0,
                         "message": {"role": "assistant", "content": "unwrapped-ok"},
                         "finish_reason": "stop"}],
            "usage": {"prompt_tokens": 9, "completion_tokens": 4, "cost": 0.03},
        }
        payload = json.dumps({"data": inner, "success": True}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def test_proxy_nonstream_cline_shaped_upstream_returns_openai_body(
        monkeypatch, tmp_path) -> None:
    """FAIL-ON-REVERT: a route with adapter='cline' unwraps a wrapped Cline body so
    the CLIENT sees top-level `choices` AND the real usage/cost ($0.03) is metered.
    Revert the shim → the served body lacks `choices` and cost falls back to the
    nominal pre-flight floor (~$0.00015) instead of $0.03 → RED."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon.spend_limits import SpendLimiter

    up = _Threaded(("127.0.0.1", 0), _ClineWrappedUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    limiter = SpendLimiter(monthly_limit_usd=100.0)
    proxy = GatewayProxyServer(
        routes={"cline-model": UpstreamRoute(base, "k", adapter="cline")},
        spend_limiter=limiter)
    proxy.serve_in_thread()
    try:
        status, body = _post(proxy.url + "/v1/chat/completions", {"model": "cline-model"})
        assert status == 200
        # client-observable body is the canonical OpenAI object (top-level choices)
        assert "choices" in body and "data" not in body
        assert body["choices"][0]["message"]["content"] == "unwrapped-ok"
        # the REAL unwrapped cost ($0.03) was metered — NOT the nominal pre-flight
        # floor. Revert the shim → no top-level usage → cost falls back to ~$0.00015
        # → this discriminating assertion goes RED.
        assert abs(limiter._spent_usd - 0.03) < 1e-6
    finally:
        proxy.shutdown()
        up.shutdown()


class _ByteExactUpstream(http.server.BaseHTTPRequestHandler):
    """Returns a canonical body with unusual spacing so any re-encode changes bytes."""
    PAYLOAD = (b'{"id":"x", "object":"chat.completion",  "model":"m",'
               b'"choices":[{"index":0,"message":{"role":"assistant","content":"ok"},'
               b'"finish_reason":"stop"}],"usage":{"prompt_tokens":1}}')

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(self.PAYLOAD)))
        self.end_headers()
        self.wfile.write(self.PAYLOAD)


def test_identity_provider_body_byte_identical() -> None:
    """The default (no-adapter) path relays the upstream body BYTE-for-byte — the
    IDENTITY guard never re-encodes."""
    up = _Threaded(("127.0.0.1", 0), _ByteExactUpstream)
    threading.Thread(target=up.serve_forever, daemon=True).start()
    base = f"http://{up.server_address[0]}:{up.server_address[1]}"

    proxy = GatewayProxyServer(routes={"m": UpstreamRoute(base, "k")})  # adapter=None
    proxy.serve_in_thread()
    try:
        status, _hdrs, raw = _post_full(proxy.url + "/v1/chat/completions", {"model": "m"})
        assert status == 200
        assert raw == _ByteExactUpstream.PAYLOAD  # byte-identical, no re-serialize
    finally:
        proxy.shutdown()
        up.shutdown()


def test_cline_pass_config_flows_adapter_to_route() -> None:
    """Config-flow: `provider: cline-pass` compiles to an UpstreamRoute whose
    .adapter == 'cline' (guards the wire-style plumbing end-to-end)."""
    from charon.gateway import _build_routes_and_pools

    registry = {"glm": {"provider": "cline-pass", "upstream_model": "glm-5.2"}}
    routes, _pools, _ids = _build_routes_and_pools(registry, {})
    assert routes["glm"].adapter == "cline"


def test_upstream_route_adapter_defaults_none() -> None:
    assert UpstreamRoute("http://x/v1").adapter is None
    assert UpstreamRoute("http://x/v1", adapter="cline").adapter == "cline"
