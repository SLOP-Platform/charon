"""R2 router-core — dynamic cheapest-first routing from LIVE metered cost.

End-to-end tests through the gateway forward path.  Asserts:
  1. Live metered cost reorders providers cheapest-first.
  2. Reasoning request skips a reasoning-incapable provider (R3-wire).
  3. Failover to the next-cheapest works.
  4. Empty meter → falls back to configured order (no behavior change).
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute
from charon.routing_policy.matrix import CapabilityMatrix


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


def _gw(pools, **extra):
    gw = GatewayProxyServer(pools=pools, **extra)
    gw.serve_in_thread()
    return gw


# ── core assertions ─────────────────────────────────────────────────────

def test_empty_meter_falls_back_to_configured_order() -> None:
    """When the meter is empty, providers keep their static configured order."""
    a, base_a = _up(status=200, return_model="ma", cost=0.03)
    b, base_b = _up(status=200, return_model="mb", cost=0.03)
    # Configured order: A first, B second
    gw = _gw({
        "v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="prov-a"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="prov-b"),
        ]
    })
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        assert hdrs["X-Charon-Failovers"] == "0"
        # A served first (configured order preserved)
        assert a.received == ["ma"] and b.received == []
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_live_meter_orders_cheapest_first() -> None:
    """With live metered cost data, the CHEAPER provider is tried first."""
    expensive, base_exp = _up(status=200, return_model="m-expensive", cost=0.10)
    cheap, base_cheap = _up(status=200, return_model="m-cheap", cost=0.01)
    # Configured order: expensive first, cheap second
    gw = _gw({
        "v": [
            UpstreamRoute(base_exp, "ke", upstream_model="m-expensive",
                          provider="prov-expensive", model_id="v"),
            UpstreamRoute(base_cheap, "kc", upstream_model="m-cheap",
                          provider="prov-cheap", model_id="v"),
        ]
    })
    # Seed the meter: expensive already cost $0.50, cheap only $0.05
    gw.observer._model_provider_cost[("v", "prov-expensive")] = 0.50
    gw.observer._model_provider_cost[("v", "prov-cheap")] = 0.05
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # Because cheap has lower metered cost, it should be ordered first
        assert cheap.received == ["m-cheap"], f"cheap received {cheap.received}"
        assert expensive.received == [], f"expensive received {expensive.received}"
    finally:
        gw.shutdown()
        expensive.shutdown()
        cheap.shutdown()


def test_failover_to_next_cheapest() -> None:
    """If the cheapest fails, failover proceeds to the next-cheapest."""
    cheap, base_cheap = _up(status=429, return_model="m-cheap", cost=0.0)
    mid, base_mid = _up(status=429, return_model="m-mid", cost=0.0)
    expensive, base_exp = _up(status=200, return_model="m-expensive", cost=0.10)
    # Configured order: cheap, mid, expensive
    gw = _gw({
        "v": [
            UpstreamRoute(base_cheap, "kc", upstream_model="m-cheap",
                          provider="prov-cheap"),
            UpstreamRoute(base_mid, "km", upstream_model="m-mid",
                          provider="prov-mid"),
            UpstreamRoute(base_exp, "ke", upstream_model="m-expensive",
                          provider="prov-expensive"),
        ]
    })
    # Seed meter: cheap=$0.01 (lowest), mid=$0.05, expensive=$0.50 (highest)
    gw.observer._model_provider_cost[("v", "prov-cheap")] = 0.01
    gw.observer._model_provider_cost[("v", "prov-mid")] = 0.05
    gw.observer._model_provider_cost[("v", "prov-expensive")] = 0.50
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        assert hdrs["X-Charon-Failovers"] == "2"
        # cheap served first (cheapest), then mid, then expensive
        assert cheap.received == ["m-cheap"], f"cheap received {cheap.received}"
        assert mid.received == ["m-mid"], f"mid received {mid.received}"
        assert expensive.received == ["m-expensive"], (
            f"expensive received {expensive.received}")
    finally:
        gw.shutdown()
        cheap.shutdown()
        mid.shutdown()
        expensive.shutdown()


def test_reasoning_request_skips_incapable_provider() -> None:
    """A reasoning request skips a provider known to be reasoning-incapable
    (R3-wire); the remaining capable provider is used, honoring cheapest-first."""
    capable, base_cap = _up(status=200, return_model="m-cap", cost=0.05)
    incapable, base_inc = _up(status=200, return_model="m-inc", cost=0.01)
    gw = _gw({
        "v": [
            UpstreamRoute(base_inc, "ki", upstream_model="m-inc",
                          provider="novita"),   # known reasoning-incapable
            UpstreamRoute(base_cap, "kc", upstream_model="m-cap",
                          provider="deepseek"), # capable
        ]
    })
    # Seed meter: novita cheaper, but it's incapable
    gw.observer._model_provider_cost[("v", "novita")] = 0.01
    gw.observer._model_provider_cost[("v", "deepseek")] = 0.10
    # Inject capability matrix (R3)
    gw.capability_matrix = CapabilityMatrix()
    try:
        status, body, hdrs = _req(
            gw.url + "/v1/chat/completions",
            {"model": "v", "reasoning": True})
        assert status == 200
        # novita skipped because reasoning-incapable → deepseek serves
        assert incapable.received == [], f"incapable received {incapable.received}"
        assert capable.received == ["m-cap"], f"capable received {capable.received}"
    finally:
        gw.shutdown()
        capable.shutdown()
        incapable.shutdown()


def test_live_meter_with_balance_tracker_composes() -> None:
    """Balance tracker mirrors the metered cost; live sorting still works."""
    a, base_a = _up(status=200, return_model="ma", cost=0.02)
    b, base_b = _up(status=200, return_model="mb", cost=0.01)
    bt = BalanceTracker()
    gw = _gw({
        "v": [
            UpstreamRoute(base_a, "ka", upstream_model="ma", provider="prov-a",
                          model_id="v"),
            UpstreamRoute(base_b, "kb", upstream_model="mb", provider="prov-b",
                          model_id="v"),
        ]
    }, balance_tracker=bt)
    # Seed meter: B cheaper than A
    gw.observer._model_provider_cost[("v", "prov-a")] = 0.50
    gw.observer._model_provider_cost[("v", "prov-b")] = 0.10
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        # B is cheaper → tried first
        assert b.received == ["mb"] and a.received == []
        # Both ledgers updated (seed 0.10 + response cost 0.01 = 0.11 cumulative)
        assert gw.observer.model_provider_cost("v", "prov-b") == 0.11
        assert bt.model_spend("v", "prov-b") == 0.01
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
