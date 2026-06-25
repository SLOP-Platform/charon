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
_SEEN: list[dict] = []  # (which upstream, model received) for the routing test


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        _SEEN_AUTH.append(self.headers.get("Authorization", ""))
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
        assert status == 502 and "no route" in body["error"]["message"]
    finally:
        proxy.shutdown()
