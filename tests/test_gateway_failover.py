"""P2 — transparent in-request failover across a cost-ranked provider pool.

Covers ADR-0005 R1/R6/R7/R10: fail over on capacity, SERVE a genuine downgrade with
the X-Charon-Downgrade header (SR-2 — never discard-and-rebill a completed 200),
DON'T fail over a client error, per-attempt body remap (R10b), no cost double-count
(R10a), provider cooldown, visibility headers, and the terminal "pool exhausted" relay.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import time
import urllib.error
import urllib.request

from charon.proxy_server import GatewayProxyServer, UpstreamRoute


class _Prog(http.server.BaseHTTPRequestHandler):
    """Programmable mock upstream — status/returned-model/cost set on the server."""
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))      # type: ignore[attr-defined]
        if srv.status == 200:                        # type: ignore[attr-defined]
            payload = json.dumps({
                "model": srv.return_model,           # type: ignore[attr-defined]
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "cost": srv.cost},          # type: ignore[attr-defined]
            }).encode()
            self.send_response(200)
        else:
            err = {"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}
            payload = json.dumps(err).encode()
            self.send_response(srv.status)            # type: ignore[attr-defined]
            if srv.status == 429:                     # type: ignore[attr-defined]
                self.send_header("Retry-After", "30")
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(status=200, return_model="m", cost=0.0):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.status, srv.return_model, srv.cost = status, return_model, cost  # type: ignore[attr-defined]
    srv.received = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def _gw(pools):
    gw = GatewayProxyServer(pools=pools)
    gw.serve_in_thread()
    return gw


def _get(url):
    resp = urllib.request.urlopen(urllib.request.Request(url, method="GET"), timeout=10)
    return resp.status, resp.read().decode(), dict(resp.headers)


def test_console_and_status_endpoints():
    a, ba = _up(status=429)
    b, bb = _up(status=200, return_model="mb", cost=0.02)
    gw = GatewayProxyServer(
        pools={"v": [UpstreamRoute(ba, "ka"), UpstreamRoute(bb, "kb", upstream_model="mb")]},
        model_ids=["v"])
    gw.serve_in_thread()
    try:
        _req(gw.url + "/v1/chat/completions", {"model": "v"})  # 429 → 200 failover
        # self-contained console HTML (zero egress)
        st, html, hdrs = _get(gw.url + "/")
        assert st == 200 and "Charon Gateway" in html
        assert "text/html" in hdrs["Content-Type"]
        assert "http://" not in html and "https://" not in html
        # status JSON: pools, per-provider stats, usage, failover events
        st, body, _ = _get(gw.url + "/charon/status")
        snap = json.loads(body)
        assert st == 200 and "v" in snap["pools"]
        assert snap["usage"]["cost_usd"] == 0.02           # only the served provider billed
        assert snap["recent_failovers"]                    # failover recorded for the console
        assert any(v["served"] > 0 for v in snap["providers"].values())
        assert any(v["failed"] > 0 for v in snap["providers"].values())
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_failover_on_429_serves_next_and_is_visible():
    a, base_a = _up(status=429)
    b, base_b = _up(status=200, return_model="mb", cost=0.02)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["choices"][0]["message"]["content"] == "ok"
        assert hdrs["X-Charon-Failovers"] == "1"
        assert hdrs["X-Charon-Provider"] == base_b.split("//")[1]  # served by B
        # R10b: each upstream got ITS OWN model id, not the other's
        assert a.received == ["ma"] and b.received == ["mb"]
        # only the served provider's cost is billed
        assert gw.observer.cumulative_usage().cost_usd == 0.02
        assert gw.failover_events and gw.failover_events[-1]["failovers"][0]["status"] == 429
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_genuine_downgrade_is_served_not_rebilled():
    # SR-2: A returns 200 with a DIFFERENT model than asked (genuine downgrade) at
    # cost 0.05. A completed 200 is already billed — SERVE it with the
    # X-Charon-Downgrade header; do NOT discard it and re-bill provider B.
    a, base_a = _up(status=200, return_model="downgraded", cost=0.05)
    b, base_b = _up(status=200, return_model="mb", cost=0.02)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "0"
        assert hdrs.get("X-Charon-Downgrade")           # downgrade disclosed
        assert body["model"] == "downgraded"            # A's completion is what we served
        assert b.received == []                          # B never called → never re-billed
        # billed A's 0.05 once (the served completion); no discard-and-refetch
        assert gw.observer.cumulative_usage().cost_usd == 0.05
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_client_error_is_not_failed_over():
    a, base_a = _up(status=400)
    b, base_b = _up(status=200, return_model="mb")
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, _, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 400                       # R6: returned immediately
        assert hdrs["X-Charon-Failovers"] == "0"
        assert b.received == []                     # B never tried
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_unreachable_provider_fails_over():
    b, base_b = _up(status=200, return_model="mb")
    gw = _gw({"v": [UpstreamRoute("http://127.0.0.1:1/v1", "ka"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, _, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "1"
        assert hdrs["X-Charon-Failover-Reasons"].endswith("unreachable")
    finally:
        gw.shutdown()
        b.shutdown()


class _SSE(http.server.BaseHTTPRequestHandler):
    """Streaming mock: a first chunk carrying `model`+content, a final chunk with
    usage (the `include_usage` tail), then [DONE]. Content == the model id so a test
    can assert which provider's bytes reached the client."""
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        s = self.server  # type: ignore[assignment]
        self.rfile.read(int(self.headers.get("Content-Length") or 0))
        self.send_response(200)
        self.send_header("Content-Type", "text/event-stream")
        self.end_headers()
        m = s.return_model  # type: ignore[attr-defined]
        if s.send_model:    # type: ignore[attr-defined]
            head = f'data: {{"model": "{m}", "choices": [{{"delta": {{"content": "{m}"}}}}]}}\n\n'
            self.wfile.write(head.encode())
        else:
            self.wfile.write(b'data: {"choices": [{"delta": {"content": "x"}}]}\n\n')
        self.wfile.flush()
        tail = f'data: {{"model": "{m}", "usage": {{"prompt_tokens": 1, "cost": {s.cost}}}}}\n\n'
        self.wfile.write(tail.encode())
        self.wfile.write(b"data: [DONE]\n\n")
        self.wfile.flush()


def _sse(return_model="m", cost=0.0, send_model=True):
    srv = _Threaded(("127.0.0.1", 0), _SSE)
    srv.return_model, srv.cost, srv.send_model = return_model, cost, send_model  # type: ignore[attr-defined]
    srv.received = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _stream_req(url, payload):
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, dict(resp.headers), resp.read().decode()


def test_streaming_served_bills_usage_once():
    b, base_b = _sse(return_model="mb", cost=0.03)
    gw = _gw({"v": [UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, hdrs, text = _stream_req(gw.url + "/v1/chat/completions",
                                         {"model": "v", "stream": True})
        assert status == 200 and "mb" in text and hdrs["X-Charon-Failovers"] == "0"
        assert gw.observer.cumulative_usage().cost_usd == 0.03  # billed exactly once
    finally:
        gw.shutdown()
        b.shutdown()


def test_streaming_genuine_downgrade_is_served_not_rebilled():
    # SR-2: A streams a DIFFERENT model than asked (genuine downgrade). The head is a
    # completed, already-billed 200 — commit and SERVE it with X-Charon-Downgrade
    # rather than discarding it and re-billing B.
    a, base_a = _sse(return_model="downgraded", cost=0.05)
    b, base_b = _sse(return_model="mb", cost=0.03)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, hdrs, text = _stream_req(gw.url + "/v1/chat/completions",
                                         {"model": "v", "stream": True})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "0"
        assert hdrs.get("X-Charon-Downgrade")           # downgrade disclosed
        # A's bytes ARE served; B is never called (no re-bill)
        assert "downgraded" in text and b.received == []
        assert gw.observer.cumulative_usage().cost_usd == 0.05  # A billed once
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_streaming_without_model_is_served_not_hung():
    b, base_b = _sse(return_model="mb", cost=0.01, send_model=False)
    gw = _gw({"v": [UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, _, text = _stream_req(gw.url + "/v1/chat/completions",
                                      {"model": "v", "stream": True})
        assert status == 200 and "x" in text  # served, did not hang on the missing model
    finally:
        gw.shutdown()
        b.shutdown()


def test_402_and_404_also_fail_over():
    for code in (402, 404):
        a, ba = _up(status=code)
        b, bb = _up(status=200, return_model="mb")
        gw = _gw({"v": [UpstreamRoute(ba, "k"), UpstreamRoute(bb, "k", upstream_model="mb")]})
        try:
            status, _, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
            assert status == 200 and hdrs["X-Charon-Failovers"] == "1"
        finally:
            gw.shutdown()
            a.shutdown()
            b.shutdown()


def test_set_cooldown_clamps_huge_retry_after():
    # cooldown-anchor-demotion red: an upstream-reported Retry-After of ~3420s
    # (~57min, the observed real-world value that sidelined the anchor) must be
    # clamped to max_cooldown_s, not honored verbatim.
    gw = GatewayProxyServer(max_cooldown_s=120.0)
    try:
        route = UpstreamRoute("http://127.0.0.1:1", "k")
        gw.set_cooldown(route, 3420)
        remaining = gw._cooldown[route.upstream_base] - time.monotonic()
        assert 0 < remaining <= 120.0
    finally:
        gw.server_close()


def test_set_cooldown_default_unaffected_by_clamp():
    # No Retry-After header → falls back to default_cooldown (60s), which is
    # below the default max_cooldown_s (120s) — the clamp must be a no-op here.
    gw = GatewayProxyServer()
    try:
        route = UpstreamRoute("http://127.0.0.1:1", "k")
        gw.set_cooldown(route, None)
        remaining = gw._cooldown[route.upstream_base] - time.monotonic()
        assert 55 < remaining <= 60.0
    finally:
        gw.server_close()


def test_order_by_cooldown_orders_cooled_bucket_by_remaining_time():
    # cooldown-anchor-demotion red (fix 2): among cooled providers, the one
    # closest to recovering should be preferred, not left in arbitrary order.
    gw = GatewayProxyServer()
    try:
        soon = UpstreamRoute("http://127.0.0.1:1", "k1")   # short remaining cooldown
        later = UpstreamRoute("http://127.0.0.1:2", "k2")  # long remaining cooldown
        gw.set_cooldown(later, 100)
        gw.set_cooldown(soon, 5)
        ordered = gw.order_by_cooldown([later, soon])  # deliberately reverse input order
        assert [r.upstream_base for r in ordered] == [soon.upstream_base, later.upstream_base]
    finally:
        gw.server_close()


def test_order_by_cooldown_fresh_before_cooled_no_regression():
    # No regression to the existing fresh-before-cooled bucketing (R7): a fresh
    # (never cooled) provider still always sorts ahead of any cooled provider,
    # regardless of the new within-bucket ordering.
    gw = GatewayProxyServer()
    try:
        fresh = UpstreamRoute("http://127.0.0.1:1", "k1")
        cooled = UpstreamRoute("http://127.0.0.1:2", "k2")
        gw.set_cooldown(cooled, 30)
        ordered = gw.order_by_cooldown([cooled, fresh])  # cooled listed first in input
        assert [r.upstream_base for r in ordered] == [fresh.upstream_base, cooled.upstream_base]
    finally:
        gw.server_close()


def test_whole_pool_exhausted_synthesizes_terminal():
    # RED failover-401-not-classified (part 3): when the LAST provider also fails
    # over-eligibly, EVERY provider is exhausted/unsupported — relaying that one
    # provider's raw upstream error is misleading. Synthesize a terminal
    # "all providers exhausted" response that carries the tracked failover reasons.
    # On master this relayed the last raw 429 instead (real last error, not synthesized).
    a, base_a = _up(status=429)
    b, base_b = _up(status=429)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka"), UpstreamRoute(base_b, "kb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503                              # synthesized terminal, NOT the raw 429
        assert body["error"]["type"] == "all_providers_exhausted"
        # every provider (both) is named in the tracked failover reasons
        assert len(body["error"]["failover_reasons"]) == 2
        assert hdrs["X-Charon-Failovers"] == "2"
        assert hdrs["X-Charon-Failover-Reasons"].count("429") == 2
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
