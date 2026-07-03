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
