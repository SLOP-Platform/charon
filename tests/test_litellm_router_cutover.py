"""FAIL-ON-REVERT tests for LITELLM-ROUTER-CUTOVER (D-019) — the live wiring.

Proves the cutover LANDED: ``litellm_plane`` has a production importer
(``gateway.build_server`` → ``_build_router``) and the live money-path dispatches
through the adopted ``litellm.Router`` with the money-path invariants preserved.

Every test is FAIL-ON-REVERT: reverting the cutover (dropping
``forwarder.forward_via_router``, ``gateway.build_server``'s ``_build_router`` call,
or the ``complete_via_router_tracked`` dispatch) turns the corresponding test RED.

Acceptance tests (the brief's set):
  (1) FAILOVER ACROSS LEGS — a 402 from one leg FAILS OVER via the Router's
      ``fallbacks``; X-Charon headers report the truth. Revert → RED.
  (2) D-012 — fully-parked pool → real 503 ``all_legs_parked``, never a 200.
  (3) D-018 — park does NOT keep never-strand; a parked leg is excluded.
  (4) IMPORTER EXISTS — build_server imports litellm_plane (zero-importer was the
      failure). Revert → RED.

E2E proof: a real request through the live gateway, failover across legs with
X-Charon headers — not a unit test alone. litellm required; skipped when absent.
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
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        srv.calls += 1  # type: ignore[attr-defined]
        idx = min(srv.calls - 1, len(srv.responses) - 1)  # type: ignore[attr-defined]
        entry = srv.responses[idx]  # type: ignore[attr-defined]
        status = entry[0]
        if status == 200:
            model = entry[1] if len(entry) > 1 else "m"
            content = entry[2] if len(entry) > 2 else "ok"
            payload = json.dumps({
                "id": "c", "object": "chat.completion", "model": model,
                "choices": [{"index": 0, "message": {"role": "assistant",
                             "content": content}, "finish_reason": "stop"}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
            }).encode()
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
    srv.responses = responses  # type: ignore[attr-defined]
    srv.calls = 0  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}/v1"


def _req(url, payload, token=None):
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=json.dumps(payload).encode(),
                                 headers=headers, method="POST")
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


# (4) IMPORTER EXISTS --------------------------------------------------------


def test_build_server_imports_litellm_plane():
    """build_server constructs a litellm.Router via litellm_plane.make_router — the
    production importer that was missing. FAIL-ON-REVERT: dropping _build_router →
    srv.router is None → assertion fails. This is the brief's done-bar: 'if
    litellm_plane still has no production importer when you finish, you have not
    done this ticket.'"""
    a, base_a = _up([(200, "m", "ok")])
    try:
        cfg = GatewayConfig(host="127.0.0.1", port=0, pools={"m": [UpstreamRoute(base_a, "k")]})
        srv = build_server(cfg)
        try:
            assert srv.router is not None, (
                "litellm_plane has NO production importer — build_server did not construct"
                " a Router; the cutover did not land")
            assert srv.router_chains, "router_chains must be populated"
        finally:
            srv.server_close()
    finally:
        a.shutdown()


def test_import_opt_out_keeps_hand_rolled_path():
    """use_litellm_router=False leaves srv.router is None — the hand-rolled forwarder
    path runs (security tests opt out). Proves the flag is the opt-out, not a broken
    default."""
    a, base_a = _up([(200, "m", "ok")])
    try:
        cfg = GatewayConfig(host="127.0.0.1", port=0, pools={"m": [UpstreamRoute(base_a, "k")]},
                            use_litellm_router=False)
        srv = build_server(cfg)
        try:
            assert srv.router is None, (
                "use_litellm_router=False must NOT construct a Router")
        finally:
            srv.server_close()
    finally:
        a.shutdown()


# (1) FAILOVER ACROSS LEGS ---------------------------------------------------


def test_e2e_failover_across_legs_with_x_charon_headers():
    """A 402 from leg 0 fails over to leg 1 via the Router's fallbacks; the served 200
    carries X-Charon-Failovers: 1 and X-Charon-Failover-Reasons naming the failed leg.
    E2E proof: a real request through the live gateway with failover + X-Charon
    headers. FAIL-ON-REVERT: dropping forward_via_router → stuck on leg 0 → RED."""
    a, base_a = _up([(402, "This request requires more credits, or fewer max_tokens. "
                            "You requested up to 65536 tokens, but can only afford 345 tokens.")])
    b, base_b = _up([(200, "mb", "served-by-b")])
    pools = {"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", upstream_model="mb")]}
    srv = _gw(pools)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "v",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 200, f"expected 200 via failover, got {status}: {body!r}"
        assert body["object"] == "chat.completion"
        assert "choices" in body and body.get("usage")
        assert body["model"] == "mb"
        assert body["choices"][0]["message"]["content"] == "served-by-b"
        assert hdrs.get("X-Charon-Failovers") == "1", (
            f"expected 1 failover, got {hdrs.get('X-Charon-Failovers')!r}")
        assert "X-Charon-Provider" in hdrs, "X-Charon-Provider header missing"
        reasons = hdrs.get("X-Charon-Failover-Reasons", "")
        assert "402" in reasons, f"failed leg's 402 not in reasons: {reasons!r}"
        assert a.calls == 1 and b.calls == 1
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


def test_e2e_all_exhausted_returns_structured_503():
    """When EVERY leg fails (both 402), the client sees a 503 all_providers_exhausted
    with providers_tried naming each leg — NOT a 200, NOT a bare error. FAIL-ON-REVERT:
    dropping the exhaustion-envelope synthesis → bare litellm exception → 500 → RED."""
    a, base_a = _up([(402, "drained")])
    b, base_b = _up([(402, "drained")])
    pools = {"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", upstream_model="mb")]}
    srv = _gw(pools)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "v",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        assert body["error"]["requested_model"] == "v"
        tried = body["error"]["providers_tried"]
        assert len(tried) == 2
        assert hdrs.get("X-Charon-Failovers") == "2"
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


# (2) D-012 — fully-parked → 503, never 200 ---------------------------------


def test_d012_fully_parked_returns_503_not_200_via_router():
    """D-012 on the Router path: EVERY leg parked → routes_by_model returns EMPTY → no
    deployment → 503 all_legs_parked WITHOUT an upstream call (zero spend). NEVER a 200.
    FAIL-ON-REVERT: restoring `live or list(chain)` in _preorder_chain re-admits parked
    legs → Router bills them → 200 → the 503 assertion RED."""
    a, base_a = _up([(200, "ma", "should-never-be-served")])
    b, base_b = _up([(200, "mb", "should-never-be-served")])
    bt = BalanceTracker(config={
        "a": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 3},
        "b": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 1},
    })
    bt.park("a")
    bt.park("b")
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="b", upstream_model="mb")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "v",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503, (
            f"D-012 VIOLATION: fully-parked pool served {status}, not 503 — money leak")
        assert body["error"]["type"] == "all_providers_exhausted"
        assert body["error"]["no_provider_reason"] == "all_legs_parked"
        tried = body["error"]["providers_tried"]
        assert len(tried) == 2
        by_prov = {t["provider"]: t for t in tried}
        assert by_prov["a"]["status"] == "parked"
        assert by_prov["a"]["class"] == "drain-then-park"
        assert by_prov["b"]["class"] == "free-recurring"
        assert a.calls == 0 and b.calls == 0, (
            f"upstream called despite full park: a={a.calls} b={b.calls} — money leak")
        assert hdrs.get("X-Charon-Failovers") == "0"
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


def test_d012_one_unparked_leg_serves_normally():
    """D-012 anti-over-block: a pool with ONE unparked leg still serves normally."""
    from charon import secrets
    import tempfile, os
    tmp = tempfile.mkdtemp(); os.environ["CHARON_HOME"] = tmp
    a, base_a = _up([(200, "ma", "served-by-a")])
    b, base_b = _up([(200, "mb", "should-not-be-needed")])
    secrets.set_provider_key("a", "ka", base_url=base_a)
    secrets.set_provider_key("b", "kb", base_url=base_b)
    bt = BalanceTracker(config={
        "a": {"mode": "fixed", "starting_balance": 5.0, "funding_class": 3},
        "b": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 3},
    })
    bt.park("b")
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="b", upstream_model="mb")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "v",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 200, f"expected 200, got {status}: {body!r}"
        assert body["model"] == "ma"
        assert a.calls == 1
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()


# (3) D-018 — park does NOT keep never-strand --------------------------------


def test_d018_parked_leg_not_served_even_when_sole_leg():
    """D-018: park does NOT keep the never-strand guard. A parked-only pool returns the
    D-012 503 — NOT restored to the selectable set. FAIL-ON-REVERT: making
    _preorder_chain fall back to `live or list(chain)` restores the parked leg → Router
    serves it → 200 → the 503 assertion RED."""
    a, base_a = _up([(200, "ma", "parked-but-served")])
    bt = BalanceTracker(config={"a": {"mode": "fixed", "starting_balance": 1.0,
                                     "funding_class": 3}})
    bt.park("a")
    pools = {"solo": [UpstreamRoute(base_a, "ka", provider="a", upstream_model="ma")]}
    srv = _gw(pools, balance_tracker=bt)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "solo",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 503, (
            f"D-018 VIOLATION: parked-only pool served {status}, not 503")
        assert body["error"]["no_provider_reason"] == "all_legs_parked"
        assert a.calls == 0, f"parked leg was served (calls={a.calls}) — spend leak"
    finally:
        srv.shutdown(); a.shutdown()


def test_router_path_hand_rolled_fallback_when_no_router():
    """use_litellm_router=False → the hand-rolled forwarder path runs (failover loop,
    X-Charon headers, D-012 guard). Proves the two paths coexist (Router preferred,
    hand-roll fallback) per D-019's REPLACE → cut over → DELETE."""
    a, base_a = _up([(402, "drained")])
    b, base_b = _up([(200, "mb", "served-by-b")])
    pools = {"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", upstream_model="mb")]}
    srv = _gw(pools, use_litellm_router=False)
    try:
        status, body, hdrs = _req(srv.url + "/v1/chat/completions", {"model": "v",
                              "messages": [{"role": "user", "content": "hi"}]})
        assert status == 200
        assert body["model"] == "mb"
        assert hdrs.get("X-Charon-Failovers") == "1"
    finally:
        srv.shutdown(); a.shutdown(); b.shutdown()