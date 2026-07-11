"""R3-WIRE — CapabilityMatrix wired into forwarder route eligibility.

(a) reasoning-required request proactively skips reasoning-incapable providers.
(b) when ALL providers are known-incapable, the no-strand fallback kicks in.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request

from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.routing_policy.matrix import CapabilityMatrix


class _Prog(http.server.BaseHTTPRequestHandler):
    """Programmable mock upstream."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))      # type: ignore[attr-defined]
        payload = json.dumps({
            "model": srv.return_model,                # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                      "cost": srv.cost},             # type: ignore[attr-defined]
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(return_model="m", cost=0.0):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.return_model, srv.cost = return_model, cost  # type: ignore[attr-defined]
    srv.received = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read()), dict(resp.headers)


def test_reasoning_request_skips_incapable_provider():
    """A body with ``reasoning_effort`` skips openrouter (incapable) and routes
    straight to the capable deepseek provider — no failover, no waste."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="openrouter"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="deepseek"),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    gw.capability_matrix = CapabilityMatrix()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "reasoning_effort": "high", "messages": []}
        )
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        assert hdrs["X-Charon-Failovers"] == "0"
        # openrouter was proactively excluded — never called
        assert a.received == []
        # deepseek served the request
        assert b.received == ["mb"]
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_incapable_fallback_not_stranded():
    """CRITICAL SAFETY: when EVERY provider is reasoning-incapable, the forwarder
    MUST NOT strand the request — it falls back to the full chain."""
    a, base_a = _up(return_model="ma")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="openrouter"),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    gw.capability_matrix = CapabilityMatrix()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "reasoning_effort": "high", "messages": []}
        )
        assert status == 200, "request was stranded instead of falling back"
        assert a.received == ["ma"]
    finally:
        gw.shutdown()
        a.shutdown()


def test_non_reasoning_request_uses_all_providers():
    """Without a reasoning/thinking signal, capability filtering is NOT applied
    and openrouter remains eligible."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="openrouter"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="deepseek"),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    gw.capability_matrix = CapabilityMatrix()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status == 200
        # No capability signal → normal ordering, openrouter (first) is used
        assert a.received == ["ma"]
        assert b.received == []
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_capability_detection_keys():
    """Unit-level: every known reasoning/thinking flag maps to 'reasoning'."""
    from charon.forwarder import _required_capability

    assert _required_capability({"reasoning": True}) == "reasoning"
    assert _required_capability({"thinking": {"type": "enabled"}}) == "reasoning"
    assert _required_capability({"reasoning_effort": "high"}) == "reasoning"
    assert _required_capability({"reasoning_config": {}}) == "reasoning"
    assert _required_capability({"messages": []}) is None
    assert _required_capability({"reasoning": False}) is None
    assert _required_capability({"thinking": False}) is None
