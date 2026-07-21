"""Fail-on-revert e2e for the Router-path silent-downgrade guard (GW-BRIDGE-1).

This is the Router-path analogue of the hand-rolled forwarder's SR-1/SR-2 handling: when the
adopted ``litellm.Router`` serves a 200 whose returned model differs from the model litellm
actually SENT, the guard must (a) flag it a genuine downgrade and attach the SAME
``X-Charon-Downgrade`` marker the money path emits, and (b) serve that already-billed 200
AS-IS — never discard-and-refetch (the 2026-07-03 double-bill, DECISIONS D025).

GREEN-IS-NOT-PROOF: these drive a real ``Router.completion`` against a stub upstream and assert
the OBSERVABLE gating — marker present on a genuine downgrade, ABSENT on an honest echo, and
the upstream hit EXACTLY once (no second billable call). The downgrade verdict is produced by
the canonical ``proxy.GatewayProxy.classify`` (the SAME SR-1 final-segment/quant-tolerant
compare forwarder.py uses), imported — not re-implemented — inside the guard.

Revert-RED: neuter the guard in ``litellm_router.complete_via_router_guarded`` (drop the
``if obs.pseudo_success:`` marker block, or compare against ``requested`` instead of the SENT
model) and ``test_downgrade_served_with_marker_and_billed_once`` goes RED — the marker
assertion fails, or the honest-echo test false-flags.

litellm is required for the real call; skipped when absent.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("litellm")

from charon import secrets  # noqa: E402
from charon.litellm_plane import litellm_router as lr  # noqa: E402
from charon.proxy_server import GatewayProxyServer, UpstreamRoute  # noqa: E402


class _Upstream(BaseHTTPRequestHandler):
    """An OpenAI-compatible stub that echoes a CONFIGURABLE ``model`` in its 200 and COUNTS
    how many completions it served — so a test can prove the guard neither re-fetches nor
    re-bills a served downgrade (the upstream is hit exactly once)."""

    returned_model: str = "ma"
    calls: int = 0

    def log_message(self, *a):  # keep test output clean
        pass

    def do_POST(self):
        type(self).calls += 1
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
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
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def upstream():
    _Upstream.calls = 0
    _Upstream.returned_model = "ma"
    httpd = HTTPServer(("127.0.0.1", 0), _Upstream)
    threading.Thread(target=httpd.serve_forever, daemon=True).start()
    try:
        yield f"http://127.0.0.1:{httpd.server_address[1]}/v1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _router(upstream_base, tmp_path, monkeypatch):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY", base_url=upstream_base)
    # upstream_model "ma" is what litellm SENDS; a downgrade = the upstream echoing something else.
    route = UpstreamRoute(upstream_base=upstream_base, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = GatewayProxyServer(host="127.0.0.1", port=0, pools={"m1": [route]},
                             default_cooldown=45.0)
    try:
        return lr.make_router(srv), srv
    except Exception:
        srv.server_close()
        raise


def test_downgrade_served_with_marker_and_billed_once(upstream, monkeypatch, tmp_path):
    """A 200 whose returned model != the SENT model is served WITH ``X-Charon-Downgrade`` and
    the upstream is hit EXACTLY once — the already-billed 200 is served as-is, never
    discard-and-rebilled (D025 / SR-2)."""
    _Upstream.returned_model = "free-tier-downgrade"  # != sent "ma" => genuine downgrade
    router, srv = _router(upstream, tmp_path, monkeypatch)
    try:
        result = lr.complete_via_router_guarded(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        })
    finally:
        srv.server_close()

    # (1) genuine downgrade detected via the canonical SR-1 compare
    assert result.downgrade is True
    # (2) the SAME marker the hand-rolled serve path emits is attached
    assert lr.DOWNGRADE_HEADER in result.headers
    assert result.headers[lr.DOWNGRADE_HEADER] == "served a different model than requested"
    # (3) the already-billed 200 is served AS-IS (the downgraded body, unchanged) — assert
    #     the client-observable top-level OpenAI contract, not only content nested in choices.
    assert result.response["object"] == "chat.completion"
    assert "choices" in result.response and result.response.get("usage")
    assert result.response["model"] == "free-tier-downgrade"
    assert result.response["choices"][0]["message"]["content"] == "pong"
    # (4) NO discard-and-rebill: the upstream served exactly one completion
    assert _Upstream.calls == 1


def test_honest_echo_is_not_flagged(upstream, monkeypatch, tmp_path):
    """An honest 200 echoing the SENT model carries NO marker — the SR-1 fix that stopped
    false-flagging namespace/quant echoes (the false-positive that drove the double-bill)."""
    _Upstream.returned_model = "ma"  # == sent "ma"
    router, srv = _router(upstream, tmp_path, monkeypatch)
    try:
        result = lr.complete_via_router_guarded(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        })
    finally:
        srv.server_close()

    assert result.downgrade is False
    assert lr.DOWNGRADE_HEADER not in result.headers
    assert _Upstream.calls == 1


def test_namespaced_echo_is_not_flagged(upstream, monkeypatch, tmp_path):
    """A provider-namespaced echo of the SAME model (``accounts/x/models/ma`` vs sent ``ma``)
    is NOT a downgrade — proves the guard reuses the SR-1 final-``/``-segment compare, not a
    raw ``!=`` that would false-flag and re-bill an honest 200."""
    _Upstream.returned_model = "accounts/fireworks/models/ma"  # same model, namespaced
    router, srv = _router(upstream, tmp_path, monkeypatch)
    try:
        result = lr.complete_via_router_guarded(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        })
    finally:
        srv.server_close()

    assert result.downgrade is False
    assert lr.DOWNGRADE_HEADER not in result.headers
    assert _Upstream.calls == 1
