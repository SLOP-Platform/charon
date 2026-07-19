"""METER-DOC-RECONCILE: executable refutation of the "meter is inert" doc lie.

src/charon/proxy.py's money-path docstrings claimed the per-(model, provider)
cost ledger was Wave-2-deferred and "EMPTY under real traffic today". It is
not: forwarder.py passes ``provider=route.label`` at its 8 metering sites and
the ledger is read live by cost-rank routing (forwarder.py, via
``all_model_provider_costs``) and the gateway status surface (gateway.py).

Two FAIL-ON-REVERT tests:
  (1) BEHAVIOR — drive a real forward through the gateway and assert the
      ledger is NON-EMPTY and keyed by (model, provider). Reverting the
      forwarder's ``provider=route.label`` wiring → ledger empty → RED.
  (2) DOC-DRIFT GUARD — assert proxy.py contains NONE of the falsified
      strings, valid for as long as ``all_model_provider_costs`` has >=1 live
      reader outside proxy.py (asserted in the same test, so deleting the
      readers can never satisfy the guard). Re-introducing the stale
      docstring → RED.

GREEN-IS-NOT-PROOF: the whole suite passed while the docstrings were false —
docstrings are never executed. Only these two tests bind the doc claims to
the actual wiring.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.request
from pathlib import Path

from charon.proxy_server import GatewayProxyServer, UpstreamRoute

_SRC = Path(__file__).resolve().parent.parent / "src" / "charon"


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    """Mock upstream returning a 200 with a REAL ``cost`` in the usage block,
    so the served response carries metered spend into the observer ledger."""

    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        payload = json.dumps({
            "model": "m1",
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 5,
                      "cost": 0.25},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _ThreadedHTTP(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _boot_mock():
    srv = _ThreadedHTTP(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _send_chat(url: str, model: str) -> dict:
    req = urllib.request.Request(
        url + "/v1/chat/completions",
        data=json.dumps({"model": model, "messages": []}).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    resp = urllib.request.urlopen(req, timeout=10)
    body = json.loads(resp.read())
    resp.close()
    return body


class TestMeterIsLiveUnderRealTraffic:
    """(1) BEHAVIOR — the executable refutation of "EMPTY under real traffic"."""

    def test_forward_populates_model_provider_ledger(self) -> None:
        """Drive ONE real forward through the gateway → the per-(model,
        provider) ledger is NON-EMPTY and keyed by (model, provider).

        FAIL-ON-REVERT: reverting the forwarder's ``provider=route.label``
        metering wiring leaves the ledger empty → RED."""
        up, base = _boot_mock()
        try:
            pool_routes = {
                "m1": [UpstreamRoute(base, api_key="k", provider="prov-a")],
            }
            gw = GatewayProxyServer(pools=pool_routes)
            gw.serve_in_thread()
            try:
                _send_chat(gw.url, "m1")
                costs = gw.observer.all_model_provider_costs()
                assert costs, (
                    "LEDGER EMPTY after a real served forward — the "
                    "forwarder's provider=route.label metering wiring has "
                    "been reverted (the old proxy.py docstring lie is now "
                    "true again)")
                assert ("m1", "prov-a") in costs, (
                    f"ledger keys {list(costs)} — expected (model, provider) "
                    "key ('m1', 'prov-a')")
                assert costs[("m1", "prov-a")] == 0.25
            finally:
                gw.shutdown()
        finally:
            up.shutdown()


class TestDocDriftGuard:
    """(2) DOC-DRIFT GUARD — proxy.py must never re-claim the meter is inert
    while the ledger has live readers."""

    FALSIFIED = (
        "EMPTY under real traffic",
        "WAVE-2 DEFERRED",
        "deferred to Wave 2",
    )

    def test_proxy_docs_do_not_reclaim_meter_is_inert(self) -> None:
        """proxy.py contains NONE of the falsified strings, enforced FOR AS
        LONG AS ``all_model_provider_costs`` has >=1 live reader outside
        proxy.py — asserted here first, so the guard can never be satisfied
        by deleting the readers.

        FAIL-ON-REVERT: re-introducing any stale docstring → RED."""
        reader_count = 0
        for py in _SRC.rglob("*.py"):
            if py.name == "proxy.py":
                continue
            reader_count += py.read_text().count("all_model_provider_costs")
        assert reader_count > 0, (
            "all_model_provider_costs has NO live readers outside proxy.py — "
            "this guard's premise is void; re-evaluate the meter docs "
            "instead of deleting this test")

        proxy_src = (_SRC / "proxy.py").read_text()
        stale = [s for s in self.FALSIFIED if s in proxy_src]
        assert not stale, (
            f"DOC DRIFT: proxy.py re-introduced falsified claim(s) {stale} "
            f"while all_model_provider_costs has {reader_count} live "
            "reader(s) (forwarder.py cost-rank routing, gateway.py status "
            "surface). The ledger is populated under real traffic — fix the "
            "docstring, not this test")
