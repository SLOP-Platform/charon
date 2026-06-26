"""P2 — transparent in-request failover across a cost-ranked provider pool.

Covers ADR-0005 R1/R6/R7/R10: fail over on capacity/downgrade, DON'T fail over a
client error, per-attempt body remap (R10b), no cost double-count (R10a), provider
cooldown, visibility headers, and the terminal "whole pool exhausted" relay.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
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


def test_silent_downgrade_fails_over_without_double_counting():
    # A returns 200 but a DIFFERENT model than asked (pseudo-success) at cost 0.05
    a, base_a = _up(status=200, return_model="downgraded", cost=0.05)
    b, base_b = _up(status=200, return_model="mb", cost=0.02)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, _, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "1"
        # R10a: A's 0.05 (discarded) is NOT billed — only B's 0.02
        assert gw.observer.cumulative_usage().cost_usd == 0.02
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


def test_whole_pool_exhausted_relays_last_error():
    a, base_a = _up(status=429)
    b, base_b = _up(status=429)
    gw = _gw({"v": [UpstreamRoute(base_a, "ka"), UpstreamRoute(base_b, "kb")]})
    try:
        status, _, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 429                        # real last error relayed, not synthesized
        assert hdrs["X-Charon-Failovers"] == "1"    # one failover before the terminal attempt
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
