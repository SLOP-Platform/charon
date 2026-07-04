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

from charon.proxy_server import GatewayProxyServer, UpstreamRoute

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
        assert _SEEN_UA[0] == "charon-proxy/0.1"
        assert _SEEN_UA[1] == "opencode/1.17.10"
        assert not _SEEN_UA[2].lower().startswith("python-urllib")
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
