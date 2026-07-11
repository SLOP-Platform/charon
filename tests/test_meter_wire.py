"""R4 meter-wire — per-(model, provider) cost is NON-EMPTY under real traffic.

Integration tests through the live gateway forward path. Asserts that a
request forwarded through a TWO-provider pool records DISTINCT
per-(model, provider) meter entries with no cross-talk, and that an
optional BalanceTracker receives the same spend.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute


class _Prog(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))  # type: ignore[attr-defined]
        if srv.status == 200:  # type: ignore[attr-defined]
            payload = json.dumps({
                "model": srv.return_model,  # type: ignore[attr-defined]
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1,
                          "cost": srv.cost},  # type: ignore[attr-defined]
            }).encode()
            self.send_response(200)
        else:
            err = {"error": {"metadata": {"error_type": "rate_limit_exceeded"}}}
            payload = json.dumps(err).encode()
            self.send_response(srv.status)  # type: ignore[attr-defined]
            if srv.status == 429:  # type: ignore[attr-defined]
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
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    return resp.status, json.loads(resp.read()), dict(resp.headers)


def _gw(pools, balance_tracker=None):
    gw = GatewayProxyServer(pools=pools, balance_tracker=balance_tracker)
    gw.serve_in_thread()
    return gw


# ── core assertions ─────────────────────────────────────────────────────

def test_served_200_records_per_model_provider_meter() -> None:
    """A 200 on route A records cost under (model, routeA.label) only."""
    a, base_a = _up(status=200, return_model="ma", cost=0.03)
    b, base_b = _up(status=200, return_model="mb", cost=0.05)
    bt = BalanceTracker()
    gw = _gw({
        "v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="prov-a"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="prov-b"),
        ]
    }, balance_tracker=bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        assert hdrs["X-Charon-Failovers"] == "0"
        # Only prov-a was called (first in chain succeeds)
        assert a.received == ["ma"] and b.received == []
        # Per-(model, provider) meter
        assert gw.observer.model_provider_cost("v", "prov-a") == 0.03
        assert gw.observer.model_provider_cost("v", "prov-b") == 0.0
        # BalanceTracker also wired
        assert bt.model_spend("v", "prov-a") == 0.03
        assert bt.model_spend("v", "prov-b") == 0.0
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_failover_records_distinct_model_provider_meter() -> None:
    """After a failover to route B, meters for A and B are independent;
    no cross-talk between provider labels."""
    a, base_a = _up(status=429, return_model="ma", cost=0.0)
    b, base_b = _up(status=200, return_model="mb", cost=0.05)
    bt = BalanceTracker()
    gw = _gw({
        "v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="prov-a"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="prov-b"),
        ]
    }, balance_tracker=bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        assert hdrs["X-Charon-Failovers"] == "1"
        # A exhausted, B served
        assert a.received == ["ma"] and b.received == ["mb"]
        # A metered $0 (count_usage=False on 429 — not billed)
        assert gw.observer.model_provider_cost("v", "prov-a") == 0.0
        # B metered real cost
        assert gw.observer.model_provider_cost("v", "prov-b") == 0.05
        # BalanceTracker mirrors
        assert bt.model_spend("v", "prov-a") == 0.0
        assert bt.model_spend("v", "prov-b") == 0.05
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_balance_tracker_none_does_not_crash() -> None:
    """balance_tracker=None (default) is safe — no crash, no metering side effect."""
    a, base_a = _up(status=200, return_model="ma", cost=0.02)
    gw = _gw({
        "v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="prov-a"),
        ]
    }, balance_tracker=None)
    try:
        status, _, _ = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # Observer still gets provider label
        assert gw.observer.model_provider_cost("v", "prov-a") == 0.02
    finally:
        gw.shutdown()
        a.shutdown()
