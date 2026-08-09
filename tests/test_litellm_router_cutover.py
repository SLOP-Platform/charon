"""FAIL-ON-REVERT tests for LITELLM-ROUTER-CUTOVER (D-019) --- the live wiring.

Every test is FAIL-ON-REVERT: reverting the cutover turns the corresponding test RED.

Acceptance tests:
  (1) FAILOVER across legs via the Router's fallbacks + X-Charon headers.
  (2) D-012: fully-parked pool -> real 503 all_legs_parked, zero upstream calls.
  (3) D-018: park does NOT keep never-strand; a parked-only pool 503s.
  (4) IMPORTER EXISTS: build_server constructs a litellm.Router.
  (5) FUNDING-DERIVED: a drained (balance=0) provider is excluded from the model_list.

litellm required; skipped when absent.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

import pytest

pytest.importorskip("litellm")

from charon.balance import BalanceTracker  # noqa: E402
from charon.gateway import GatewayConfig, build_server  # noqa: E402
from charon.proxy_server import UpstreamRoute  # noqa: E402


class _Prog(http.server.BaseHTTPRequestHandler):
    protocol_version = "HTTP/1.1"
    def log_message(self, *a) -> None: pass
    def do_POST(self) -> None:
        srv = self.server
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        srv.calls += 1
        idx = min(srv.calls - 1, len(srv.responses) - 1)
        entry = srv.responses[idx]
        status = entry[0]
        if status == 200:
            model = entry[1] if len(entry) > 1 else "m"
            content = entry[2] if len(entry) > 2 else "ok"
            payload = json.dumps({"id": "c", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant", "content": content},
                             "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2}}).encode()
        else:
            msg = entry[1] if len(entry) > 1 else "error"
            payload = json.dumps({"error": {"message": msg}}).encode()
        self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True

def _up(responses):
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.responses = responses
    srv.calls = 0
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}/v1"

def _req(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token: headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=30)
        return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)

def _gw(pools, *, token=None, balance_tracker=None, use_litellm_router=True):
    cfg = GatewayConfig(host="127.0.0.1", port=0, token=token, pools=pools,
                        model_ids=list(pools.keys()), balance_tracker=balance_tracker,
                        use_litellm_router=use_litellm_router)
    srv = build_server(cfg)
    srv.serve_in_thread()
    return srv


# (4) IMPORTER EXISTS
def test_build_server_imports_litellm_plane():
    a, base_a = _up([(200, "m", "ok")])
    try:
        cfg = GatewayConfig(host="127.0.0.1", port=0, pools={"m": [UpstreamRoute(base_a, "k")]})
        srv = build_server(cfg)
        try:
            assert srv.router is not None, "litellm_plane has NO production importer"
            assert srv.router_chains, "router_chains must be populated"
        finally:
            srv.server_close()
    finally:
        a.shutdown()

def test_import_opt_out_keeps_hand_rolled_path():
    a, base_a = _up([(200, "m", "ok")])
    try:
        cfg = GatewayConfig(host="127.0.0.1", port=0, pools={"m": [UpstreamRoute(base_a, "k")]},
                            use_litellm_router=False)
        srv = build_server(cfg)
        try:
            assert srv.router is None, "use_litellm_router=False must NOT construct a Router"
        finally:
            srv.server_close()
    finally:
        a.shutdown()


# (1) FAILOVER ACROSS LEGS
def test_e2e_failover_across_legs_with_x_charon_headers():
    a, base_a = _up([(402, "insufficient credits")])
    b, base_b = _up([(200, "mb", "served-by-b")])
    pools = {"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", upstream_model="mb")]}
    srv = _gw(pools)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions",
            {"model": "v", "messages": [{"role": "user", "content": "hi"}]})
        assert status == 200, f"expected 200 via failover, got {status}: {body!r}"
        assert body["model"] == "mb"
        assert body["choices"][0]["message"]["content"] == "served-by-b"
        assert hdrs.get("X-Charon-Failovers") == "1", f"got {hdrs.get('X-Charon-Failovers')!r}"
        reasons = hdrs.get("X-Charon-Failover-Reasons", "")
        assert "402" in reasons, f"failed leg's 402 not in reasons: {reasons!r}"
        assert a.calls == 1 and b.calls == 1
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()

def test_e2e_all_exhausted_returns_structured_503():
    a, base_a = _up([(402, "drained")])
    b, base_b = _up([(402, "drained")])
    pools = {"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", upstream_model="mb")]}
    srv = _gw(pools)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions",
            {"model": "v", "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        assert body["error"]["requested_model"] == "v"
        assert len(body["error"]["providers_tried"]) == 2
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


# (2) D-012 — fully-parked pool -> terminal 503
def test_d012_fully_parked_returns_503_not_200_via_router():
    a, base_a = _up([(200, "ma", "should-never-be-served")])
    b, base_b = _up([(200, "mb", "should-never-be-served")])
    bt = BalanceTracker(config={
        "a": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 3},
        "b": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 1},
    })
    bt.park("a"); bt.park("b")
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="b", upstream_model="mb")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions",
            {"model": "v", "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503, f"D-012 VIOLATION: fully-parked pool served {status}, not 503"
        assert body["error"]["no_provider_reason"] == "all_legs_parked"
        tried = body["error"]["providers_tried"]
        assert len(tried) == 2
        assert a.calls == 0 and b.calls == 0, "upstream called despite full park — money leak"
        assert hdrs.get("X-Charon-Failovers") == "0"
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


# (3) D-018 — park does NOT keep never-strand
def test_d018_parked_leg_not_served_even_when_sole_leg():
    a, base_a = _up([(200, "ma", "parked-but-served")])
    bt = BalanceTracker(config={"a": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 3}})
    bt.park("a")
    pools = {"solo": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions",
            {"model": "solo", "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503, f"D-018 VIOLATION: parked-only pool served {status}"
        assert body["error"]["no_provider_reason"] == "all_legs_parked"
        assert a.calls == 0, f"parked leg was served (calls={a.calls}) — spend leak"
    finally:
        srv.shutdown(); a.shutdown()


# (5) FUNDING-DERIVED — a drained (balance=0) provider is excluded
def test_drained_provider_excluded_from_model_list():
    """D-019: a provider with balance=0 (deterministic 402) must NOT appear in the
    generated model_list. The model_list is DERIVED from capability + funding, not
    from the static pools.json chain."""
    from charon.litellm_plane import litellm_router as lr
    a, base_a = _up([(200, "ma", "funded")])
    b, base_b = _up([(200, "mb", "drained")])
    bt = BalanceTracker(config={
        "a": {"mode": "fixed", "starting_balance": 10.0, "funding_class": 3},
        "b": {"mode": "fixed", "starting_balance": 0.0, "funding_class": 3},
    })
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="b", upstream_model="mb")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        # The model_list should contain only provider "a" (funded), NOT "b" (drained).
        ml = srv.router.model_list
        providers_in_list = set()
        for entry in ml:
            mi = entry.get("model_info") or {}
            providers_in_list.add(mi.get("provider"))
        assert "a" in providers_in_list, "funded provider must be in the model_list"
        assert "b" not in providers_in_list, "drained provider must NOT be in the model_list"
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()