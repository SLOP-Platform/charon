"""End-to-end: a real request served THROUGH the adopted litellm.Router path.

Unlike ``test_litellm_router_adopt.py`` (unit-level control checks), this drives the FULL
path a live request takes — a real ``GatewayProxyServer`` config → :func:`make_router`
→ ``Router.completion`` → an httpx send to a real (stub) upstream → a served response — and
asserts the money-path security controls actually FIRE on that path:

  * #181 base-bound key READ        — the stub upstream receives exactly the key that was
                                      stored BOUND to its base
  * SSRF refusal                    — a metadata base is refused before the Router builds
  * preset egress allowlist         — an off-preset (attacker) base is refused (egress.py
                                      reconciliation: litellm_plane enforces the SAME allowlist
                                      the live route_from_spec path enforces)
  * SG-never-Anthropic              — an Anthropic-only model has no deployment to serve

litellm is required for this module (it makes the real call); skipped when absent.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("litellm")

from litellm.exceptions import BadRequestError  # noqa: E402

from charon import egress, secrets  # noqa: E402
from charon.litellm_plane import litellm_router as lr  # noqa: E402
from charon.proxy_server import GatewayProxyServer, UpstreamRoute  # noqa: E402


class _StubUpstream(BaseHTTPRequestHandler):
    """A minimal OpenAI-compatible upstream. Captures the Authorization header of the last
    request (so the test can prove the base-bound key was delivered) and returns a canned
    chat completion. Bound to loopback, which egress._is_local_host permits."""

    captured_auth: str | None = None
    captured_path: str | None = None

    def log_message(self, *a):  # keep test output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length)
        type(self).captured_auth = self.headers.get("Authorization")
        type(self).captured_path = self.path
        payload = json.dumps({
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": "ma",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def stub_upstream():
    _StubUpstream.captured_auth = None
    _StubUpstream.captured_path = None
    httpd = HTTPServer(("127.0.0.1", 0), _StubUpstream)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _make_gateway(pools):
    """A real GatewayProxyServer (loopback, ephemeral port), used purely as the config
    source make_router reads — never serve_forever'd here."""
    return GatewayProxyServer(host="127.0.0.1", port=0, pools=pools, default_cooldown=45.0)


def test_e2e_served_response_and_base_bound_key(stub_upstream, monkeypatch, tmp_path):
    """A full request is served through the adopted Router, and the stub upstream receives
    exactly the key stored BOUND to its base (the #181 read firing on the live path)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=stub_upstream)

    route = UpstreamRoute(upstream_base=stub_upstream, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = _make_gateway({"m1": [route]})
    try:
        router = lr.make_router(srv)
        resp = lr.complete_via_router(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        })
    finally:
        srv.server_close()

    # served response really came back through the router — assert the top-level
    # OpenAI envelope contract, not just content nested inside choices.
    assert resp.get("object") == "chat.completion"
    assert "choices" in resp and resp.get("usage")
    assert resp["choices"][0]["message"]["content"] == "pong"
    # #181: the base-bound key was read and delivered to its own base — nothing else
    assert _StubUpstream.captured_auth == "Bearer STUB-KEY-BOUND"
    assert _StubUpstream.captured_path.endswith("/chat/completions")


def test_e2e_ssrf_metadata_base_refused(monkeypatch, tmp_path):
    """A cloud-metadata base is refused BEFORE the Router is built — it never reaches litellm."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    bad = UpstreamRoute(upstream_base="http://169.254.169.254/v1", provider="evil")
    srv = _make_gateway({"m1": [bad]})
    try:
        with pytest.raises(lr.AdoptError):
            lr.make_router(srv)
    finally:
        srv.server_close()


def test_e2e_off_preset_base_refused_by_egress(monkeypatch, tmp_path):
    """egress.py reconciliation on the live path: a public, SSRF-clean base whose host is NOT
    a git-tracked preset is refused by the fail-closed egress allowlist before the Router
    builds — so litellm_plane cannot reach an arbitrary host the live path would reject."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    off = UpstreamRoute(upstream_base="https://attacker.example/v1", provider="x")
    srv = _make_gateway({"m1": [off]})
    try:
        with pytest.raises(egress.EgressPolicyError):
            lr.make_router(srv)
    finally:
        srv.server_close()


def test_e2e_anthropic_model_has_no_deployment(monkeypatch, tmp_path):
    """SG-never-Anthropic on the live path: an Anthropic-only model's legs are all dropped
    (the base host is preset-allowlisted, so egress passes — the SG guard is what drops it),
    so the Router has no deployment and the request cannot be served through Anthropic."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    claude = UpstreamRoute(upstream_base="https://api.anthropic.com/v1", provider="anthropic",
                           upstream_model="claude-3-opus")
    srv = _make_gateway({"claude-3-opus": [claude]})
    try:
        router = lr.make_router(srv)
        assert router.model_list == []
        # litellm raises BadRequestError ("No deployments available") when no leg survives.
        with pytest.raises(BadRequestError):
            lr.complete_via_router(router, {
                "model": "claude-3-opus",
                "messages": [{"role": "user", "content": "hi"}],
            })
    finally:
        srv.server_close()
