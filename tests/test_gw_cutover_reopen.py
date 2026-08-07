"""Fail-on-revert proof that the LIVE gateway route goes through litellm_plane.

GW-CUTOVER-REOPEN: the adopted litellm.Router substrate was built, merged, and marked done —
but the live route never pointed at it (zero production importers; the gateway data plane was
still the hand-rolled forwarder). This module proves the wiring: with the gateway's
``litellm_plane`` toggle on, a REAL request through the LIVE gateway is served via the Router,
proven by an OBSERVABLE effect (the wire body the upstream receives) — not a self-report.

GREEN-IS-NOT-PROOF — the observable discriminator: the Router path reaches the upstream via
litellm's OpenAI-compatible transport, whose User-Agent is ``OpenAI/Python <ver>``, while the
hand-rolled forwarder forwards the client's User-Agent verbatim (or the Mozilla ``BROWSER_UA``).
Asserting on the stub's captured User-Agent therefore proves WHICH path served the request.

Revert-RED (either is a RED gate):
  * drop the production wiring (gateway.build_server attach / forwarder dispatch) → no Router
    attached → the request is served by the hand-rolled forwarder → the stub sees the client's
    User-Agent, not ``OpenAI/Python`` → test_live_gateway_serves_via_router RED; the
    production-importer test RED.
  * the wiring survives but the D025 guard is dropped (discard-and-rebill, or no marker) →
    test_live_router_path_is_d025_safe RED (upstream hit twice, or no X-Charon-Downgrade).

litellm is required for the live call; skipped when absent (CI installs the ``router`` extra).
"""
from __future__ import annotations

import http.server
import json
import pathlib
import threading
import urllib.error
import urllib.request

import pytest

pytest.importorskip("litellm")

import charon  # noqa: E402
from charon import gateway, secrets  # noqa: E402
from charon.gateway import GatewayConfig  # noqa: E402
from charon.proxy_server import UpstreamRoute  # noqa: E402


class _StubUpstream(http.server.BaseHTTPRequestHandler):
    """An OpenAI-compatible stub that echoes a CONFIGURABLE ``model`` and records what it
    actually received (the outbound body ``model``, the User-Agent and the Authorization
    header) plus how many completions it served — so a test can prove (a) the request went
    through the Router (litellm's OpenAI-compatible transport signature) and (b) nothing was
    re-fetched or re-billed."""

    returned_model: str = "ma"
    calls: int = 0
    received_model: str | None = None
    received_ua: str | None = None
    received_auth: str | None = None

    def log_message(self, *a):  # keep test output clean
        pass

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        req = json.loads(self.rfile.read(length) or b"{}")
        type(self).received_model = req.get("model")
        type(self).received_ua = self.headers.get("User-Agent")
        type(self).received_auth = self.headers.get("Authorization")
        payload = json.dumps({
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": type(self).returned_model,
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2,
                      "cost": 0.01},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def stub_upstream():
    _StubUpstream.calls = 0
    _StubUpstream.returned_model = "ma"
    _StubUpstream.received_model = None
    _StubUpstream.received_ua = None
    _StubUpstream.received_auth = None
    httpd = http.server.HTTPServer(("127.0.0.1", 0), _StubUpstream)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _req(url, *, method="GET", payload=None, token=None, user_agent="gw-cutover-reopen-test"):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json", "User-Agent": user_agent}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=15)
        return resp.status, dict(resp.headers), json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, dict(exc.headers), json.loads(exc.read())


def _build_live_gateway(base, *, downgrade: bool, monkeypatch, tmp_path):
    """A REAL live gateway (gateway.build_server, loopback, ephemeral port) with the
    ``litellm_plane`` toggle ON — the production wiring under test."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=base)
    if downgrade:
        _StubUpstream.returned_model = "free-tier-downgrade"  # != sent "openai/ma"
    route = UpstreamRoute(upstream_base=base, api_key=None, provider="stub",
                          upstream_model="ma")
    cfg = GatewayConfig(
        port=0,
        token="s3cret",
        pools={"m1": [route]},
        model_ids=["m1"],
        litellm_plane=True,
    )
    server = gateway.build_server(cfg)
    server.serve_in_thread()
    return server


def test_live_gateway_serves_via_router(stub_upstream, monkeypatch, tmp_path):
    """A REAL request through the LIVE gateway is served via litellm_plane, proven by the
    wire body: the stub upstream receives ``openai/ma`` — the Router deployment's model — NOT
    the bare ``ma`` the hand-rolled forwarder would send. Revert the wiring → RED."""
    server = _build_live_gateway(stub_upstream, downgrade=False, monkeypatch=monkeypatch,
                                 tmp_path=tmp_path)
    try:
        status, headers, body = _req(
            server.url + "/v1/chat/completions",
            method="POST", payload={"model": "m1",
                                    "messages": [{"role": "user", "content": "ping"}]},
            token="s3cret")
    finally:
        server.shutdown()

    # the live request was served (200, OpenAI envelope)
    assert status == 200
    assert body["object"] == "chat.completion"
    assert body["choices"][0]["message"]["content"] == "pong"
    # OBSERVABLE PROOF it went through the litellm Router, not the hand-rolled forwarder:
    # litellm's OpenAI-compatible transport sends User-Agent "OpenAI/Python <ver>", while the
    # hand-rolled forwarder forwards the client's UA verbatim (or the Mozilla BROWSER_UA).
    assert (_StubUpstream.received_ua or "").startswith("OpenAI/Python"), (
        f"the stub upstream received User-Agent {_StubUpstream.received_ua!r}; the live route "
        f"did NOT go through litellm_plane (expected 'OpenAI/Python ...')")
    # the base-bound key (#181) rode along on the Router path
    assert _StubUpstream.received_auth == "Bearer STUB-KEY-BOUND"
    # metered exactly once through the canonical observer
    assert server.observer.cumulative_usage().cost_usd == 0.01
    # the Router is the live serving substrate, not a wrapper beside dead code
    assert server.litellm_router is not None
    assert len(server.litellm_router.model_list) == 1


def test_live_router_path_is_d025_safe(stub_upstream, monkeypatch, tmp_path):
    """The live Router path does NOT re-introduce the D025 silent-downgrade double-bill: a 200
    whose returned model != the sent model is served WITH X-Charon-Downgrade and the upstream
    is hit EXACTLY once (serve the already-billed 200 as-is, never discard-and-rebill)."""
    server = _build_live_gateway(stub_upstream, downgrade=True, monkeypatch=monkeypatch,
                                 tmp_path=tmp_path)
    try:
        status, headers, body = _req(
            server.url + "/v1/chat/completions",
            method="POST", payload={"model": "m1",
                                    "messages": [{"role": "user", "content": "ping"}]},
            token="s3cret")
    finally:
        server.shutdown()

    assert status == 200
    assert body["model"] == "free-tier-downgrade"  # the downgraded 200 served AS-IS
    assert headers.get("X-Charon-Downgrade") == "served a different model than requested"
    assert _StubUpstream.calls == 1, "a downgrade was re-fetched → the D025 double-bill"
    # billed once, never twice
    assert server.observer.cumulative_usage().cost_usd == 0.01


def test_plane_has_production_importers():
    """The accept criterion's grep: ``grep -rn litellm_plane src/`` must show a production
    importer on the serving path. Pinned against the two wiring seams (gateway.build_server
    attaches the Router; forwarder.forward_with_failover dispatches to it). Revert → RED."""
    src_dir = pathlib.Path(charon.__file__).parent
    for rel in ("gateway.py", "forwarder.py"):
        source = (src_dir / rel).read_text(encoding="utf-8")
        assert "litellm_plane" in source, (
            f"src/charon/{rel} no longer references litellm_plane — the live route's "
            f"production importer was reverted")
