"""R7 — CAPABILITY-ENGINE acceptance tests.

(a) max_context: a request whose token estimate exceeds a provider's declared
    max_context must SKIP that provider and route to a larger-context one.
(b) max_concurrency: when a provider is at its declared max_concurrency, a
    concurrent request must SPILL to the next eligible provider.
(c) NEVER strand: if ALL providers are too small, fall back to the full chain
    with a warning (same safety pattern as R3-wire).
(d) None-safe: missing capability data does NOT exclude a route.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.request

from charon.proxy_server import GatewayProxyServer, UpstreamRoute


class _Prog(http.server.BaseHTTPRequestHandler):
    """Programmable mock upstream that echoes the model field."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))      # type: ignore[attr-defined]
        payload = json.dumps({
            "model": srv.return_model,               # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(return_model="m"):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.return_model, srv.received = return_model, []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read()), dict(resp.headers)


def _big_body(token_target):
    """Build a request body whose len//4 token estimate is ~token_target."""
    # Each char counts as ~0.25 tokens in the estimate (len(raw_body)//4).
    # To hit a target, use raw_body length ≈ token_target * 4.
    b = json.dumps({"model": "v", "messages": [{"role": "user", "content": "x" * (token_target * 4)}]}).encode()
    return b


# ────────────────────────────────────────────────────────────────── max_context


def test_large_request_skips_small_context_provider():
    """A 64K-token request routed to a pool with 32K and 128K context providers
    must reach the 128K provider on the first attempt — zero failovers for 32K."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="small",
                          max_context=32000),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="large",
                          max_context=128000),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        body = json.dumps({
            "model": "v",
            "messages": [{"role": "user", "content": "x" * (64000 * 4)}],
        }).encode()
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        hdrs = dict(resp.headers)
        resp.read()
        resp.close()
        assert status == 200
        assert hdrs["X-Charon-Failovers"] == "0"
        # small provider was proactively excluded — never called
        assert a.received == []
        # large provider served the request
        assert b.received == ["mb"]
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_small_request_uses_all_providers():
    """A tiny request fits everyone; normal ordering without capability hit."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="small",
                          max_context=32000),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="large",
                          max_context=128000),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status == 200
        # No size exclusion → first provider serves
        assert a.received == ["ma"]
        assert b.received == []
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_too_small_never_strands():
    """CRITICAL SAFETY: when EVERY provider is too small, the forwarder MUST NOT
    strand — it falls back to the full chain."""
    a, base_a = _up(return_model="ma")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="tiny",
                          max_context=1000),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        body = json.dumps({
            "model": "v",
            "messages": [{"role": "user", "content": "x" * (5000 * 4)}],
        }).encode()
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        hdrs = dict(resp.headers)
        resp.read()
        resp.close()
        assert status == 200, "request was stranded instead of falling back"
        assert a.received == ["ma"]
    finally:
        gw.shutdown()
        a.shutdown()


def test_missing_max_context_no_exclusion():
    """None-safe: a provider without max_context is NOT excluded."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="unlimited",
                          max_context=None),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="limit",
                          max_context=32000),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        # big request: 64K tokens — unlimited has None (unknown, safe), limit has 32K (too small)
        body = json.dumps({
            "model": "v",
            "messages": [{"role": "user", "content": "x" * (64000 * 4)}],
        }).encode()
        req = urllib.request.Request(
            gw.url + "/v1/chat/completions", data=body,
            headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        resp.read()
        resp.close()
        assert status == 200
        # unlimited provider (None) remains eligible, serves first
        assert a.received == ["ma"]
        assert b.received == []
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


# ─────────────────────────────────────────────────────────────── max_concurrency


class _SlowProg(http.server.BaseHTTPRequestHandler):
    """Upstream that delays response so requests overlap."""

    delay = 0.3

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        time.sleep(_SlowProg.delay)
        payload = json.dumps({
            "model": "m",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _slow_up():
    srv = _Threaded(("127.0.0.1", 0), _SlowProg)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req_async(url, payload, results, idx):
    """Threaded wrapper for fire-and-hold concurrent requests."""
    try:
        req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                     headers={"Content-Type": "application/json"}, method="POST")
        resp = urllib.request.urlopen(req, timeout=10)
        status = resp.status
        hdrs = dict(resp.headers)
        resp.read()
        resp.close()
        results[idx] = (status, hdrs)
    except Exception as exc:  # noqa: BLE001
        results[idx] = exc


def test_max_concurrency_spills_to_next():
    """When provider A is already at its max_concurrency=1, a second concurrent
    request must spill to provider B."""
    a, base_a = _slow_up()
    b, base_b = _slow_up()
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="a",
                          max_concurrency=1),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="b",
                          max_concurrency=1),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        results: list = [None, None]
        url = gw.url + "/v1/chat/completions"
        payload = {"model": "v", "messages": []}
        t1 = threading.Thread(target=_req_async, args=(url, payload, results, 0))
        t2 = threading.Thread(target=_req_async, args=(url, payload, results, 1))
        t1.start()
        # Small stagger so t1 has entered the try block and incremented inflight.
        time.sleep(0.05)
        t2.start()
        t1.join(timeout=10)
        t2.join(timeout=10)

        for r in results:
            assert isinstance(r, tuple), f"unexpected error: {r!r}"
            assert r[0] == 200

        providers = [r[1].get("X-Charon-Provider") for r in results]
        # One on A, one on B (order may vary because both start before either finishes)
        assert sorted(providers) == ["a", "b"], (
            f"expected one request on a and one on b, got {providers}")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_at_max_concurrency_never_strands():
    """CRITICAL SAFETY: when ALL providers are at max_concurrency, fall back to
    full chain so the request is never stranded."""
    a, base_a = _up(return_model="ma")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="a",
                          max_concurrency=1),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        # First request consumes the single slot
        status1, _, _ = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status1 == 200

        # Second request — A is at cap, no other provider
        # NEVER STRAND -> fallback to full chain, serve it anyway
        status2, _, hdrs2 = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status2 == 200, "request stranded when all at max_concurrency"
        assert hdrs2.get("X-Charon-Provider") == "a"
    finally:
        gw.shutdown()
        a.shutdown()


def test_missing_max_concurrency_no_exclusion():
    """None-safe: a provider without max_concurrency is NOT excluded."""
    a, base_a = _up(return_model="ma")
    b, base_b = _up(return_model="mb")
    gw = GatewayProxyServer(
        pools={"v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="a",
                          max_concurrency=None),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="b",
                          max_concurrency=1),
        ]},
        model_ids=["v"],
    )
    gw.serve_in_thread()
    try:
        # Load A to cap (None means unbounded, so it never hits cap)
        status1, _, hdrs1 = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status1 == 200
        assert hdrs1.get("X-Charon-Provider") == "a"

        status2, _, hdrs2 = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "messages": []}
        )
        assert status2 == 200
        # A is still eligible because max_concurrency is None (unbounded)
        assert hdrs2.get("X-Charon-Provider") == "a"
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
