"""PROVIDER-CATALOG-REFRESH — FAIL-ON-REVERT tests.

These drive the REAL routing path (``GatewayProxyServer.chain_for`` /
``routing_policy.order_pool_by_live_cost`` / ``forward_with_failover``) — never a
re-implementation of the sort — against HONESTLY-constructed mock provider
``/models`` responses (no vendored/doctored fixture).

Guards, each RED if the named wire is reverted:
  1. A mock provider advertising a NEW model → after one refresh the real router
     resolves a chain to that provider with ZERO manual mapping. Revert the
     cache→router bridge (``CatalogRefresher.bridge`` / its ``apply_routes``) →
     the model is unroutable (``chain_for`` returns ``[]``) → RED.
  2. The poll is NEVER called from ``forward_with_failover`` — driving real
     traffic leaves ``poll_count`` at 0. Wire the poll into the request path → RED.
  3. Meter-observed per-(model,provider) cost SUPERSEDES the quoted price in the
     real cheapest-first selector.
  4. A provider whose poll fails degrades to STALE-BUT-USABLE last-good (still
     routable), never emptying the catalog.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager

from charon.proxy_server import GatewayProxyServer
from charon.routing_policy import order_pool_by_live_cost
from charon.routing_policy.catalog_refresh import CatalogRefresher


@contextmanager
def _server(**kw) -> Iterator[GatewayProxyServer]:
    """A gateway server bound to an ephemeral port; closed on exit. Not served
    unless the test calls ``serve_in_thread`` itself."""
    srv = GatewayProxyServer(**kw)
    try:
        yield srv
    finally:
        try:
            srv.server_close()
        except Exception:  # noqa: BLE001
            pass


# ── mock upstream (honest OpenAI-shaped 200) for the off-hot-path test ──────
class _Echo(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:  # silence
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": self.server.return_model,  # type: ignore[attr-defined]
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


@contextmanager
def _mock_upstream(return_model: str) -> Iterator[str]:
    up = _Threaded(("127.0.0.1", 0), _Echo)
    up.return_model = return_model  # type: ignore[attr-defined]
    threading.Thread(target=up.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{up.server_port}"
    finally:
        up.shutdown()


def _send(url: str, payload: dict) -> None:
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    resp.read()
    resp.close()


# ── 1. discovered model becomes routable via the REAL router ────────────────
def test_discovered_model_routable_with_no_hand_edit() -> None:
    providers_cfg = {"mockprov": {"base_url": "http://mock.test/v1"}}

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        assert name == "mockprov"
        return [{"id": "wonder-model-9", "free": False,
                 "cost_input": 1e-6, "cost_output": 2e-6}]

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)

        # Refresh alone does NOT route it — the cache→router BRIDGE is the
        # load-bearing wire. Revert ``bridge``/its ``apply_routes`` and the model
        # stays unroutable here → RED.
        r.refresh_now()
        assert srv.chain_for("wonder-model-9") == [], (
            "poll alone must not route; only the bridge makes it routable")

        r.bridge()
        chain = srv.chain_for("wonder-model-9")
        assert chain, "discovered model must be routable with zero manual mapping"
        route = chain[0]
        assert route.provider == "mockprov"
        assert route.upstream_model == "wonder-model-9"
        assert route.upstream_base == "http://mock.test/v1"

        # And it flows through the REAL cheapest-first selector (not a re-impl).
        registry = {route.model_id: {"cost_input": 1e-6, "cost_output": 2e-6}}
        ordered = order_pool_by_live_cost(chain, registry=registry, metered_costs={})
        assert [x.provider for x in ordered] == ["mockprov"]


# ── 2. the poll is OFF the hot path (forward_with_failover never polls) ─────
def test_poll_not_called_on_forward_with_failover() -> None:
    with _mock_upstream("served-model") as base:
        providers_cfg = {"mockprov": {"base_url": base}}

        def fake_list(name: str, overrides: dict | None) -> list[dict]:
            return [{"id": "served-model", "free": True}]

        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        # Reachable as srv.catalog_refresh (F29 modules): a hypothetical poll call
        # added to the request path would increment poll_count and fail this test.
        with _server(modules={"catalog_refresh": r}) as srv:
            r.bind(srv)
            r.refresh_and_bridge()             # background discovery + bridge
            assert srv.chain_for("served-model"), "setup: model must be routable"
            r.poll_count = 0                    # baseline: count only what traffic triggers

            srv.serve_in_thread()
            try:
                for _ in range(3):
                    _send(srv.url + "/v1/chat/completions",
                          {"model": "served-model",
                           "messages": [{"role": "user", "content": "hi"}]})
            finally:
                srv.shutdown()

            assert r.poll_count == 0, (
                "forward_with_failover must NEVER poll a provider — routing reads "
                f"the bridged cache only (poll_count={r.poll_count})")


# ── 3. live meter supersedes the quoted price in the real selector ──────────
def test_meter_supersedes_quoted_price() -> None:
    providers_cfg = {
        "cheapquote": {"base_url": "http://a.test/v1"},
        "expensivequote": {"base_url": "http://b.test/v1"},
    }

    def fake_list(name: str, overrides: dict | None) -> list[dict]:
        if name == "cheapquote":
            return [{"id": "m", "cost_input": 1e-7, "cost_output": 1e-7}]
        return [{"id": "m", "cost_input": 9e-6, "cost_output": 9e-6}]

    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=fake_list)
        r.bind(srv)
        r.refresh_and_bridge()

        chain = srv.chain_for("m")
        assert {rt.provider for rt in chain} == {"cheapquote", "expensivequote"}

        # Build the registry from what the router actually holds (srv.model_pricing),
        # keyed by member id — exactly as forwarder.py's R2 block does.
        registry = {rt.model_id: dict(srv.model_pricing.get(rt.model_id, {}))
                    for rt in chain}

        # Quote order (as compiled): the cheap-quote provider is first.
        assert chain[0].provider == "cheapquote"

        # Now the meter INVERTS the economics — cheap-quote has become expensive in
        # real traffic, expensive-quote cheap. The real selector must follow the
        # METER, not the quote.
        by_id = {rt.model_id: rt for rt in chain}
        cheap_id = next(m for m in by_id if by_id[m].provider == "cheapquote")
        exp_id = next(m for m in by_id if by_id[m].provider == "expensivequote")
        metered = {(cheap_id, "cheapquote"): 9e-6, (exp_id, "expensivequote"): 1e-9}

        ordered = order_pool_by_live_cost(chain, registry=registry, metered_costs=metered)
        assert ordered[0].provider == "expensivequote", (
            "live metered cost must SUPERSEDE the quoted price")


# ── 4. stale-but-usable on a provider poll failure ──────────────────────────
def test_stale_but_usable_on_provider_down() -> None:
    state = {"up": True}

    def flaky_list(name: str, overrides: dict | None) -> list[dict]:
        if not state["up"]:
            raise urllib.error.URLError("provider unreachable")
        return [{"id": "keep-me", "free": True}]

    providers_cfg = {"flaky": {"base_url": "http://f.test/v1"}}
    with _server(routes={}, pools={}) as srv:
        r = CatalogRefresher(providers_cfg=providers_cfg, list_models_fn=flaky_list)
        r.bind(srv)
        r.refresh_and_bridge()
        assert srv.chain_for("keep-me"), "setup: model routable after first poll"

        # Provider goes down: the next poll raises. The catalog must retain the
        # last-good entry (stale-but-usable) — never emptied, routing never blocked.
        state["up"] = False
        r.refresh_and_bridge()  # must not raise
        assert srv.chain_for("keep-me"), (
            "a failed refresh must keep last-good entries (stale-but-usable)")
