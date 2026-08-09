"""Integration tests for the litellm Router dispatch path (PR #266 cutover).

These tests exercise the live Router money-path — ``forward_via_router`` and its
sub-components — against a mock provider. Every covered line here is a line the
diff-coverage gate would otherwise flag as unreachable.

Tests are parametrised on ``use_litellm_router``: True exercises the Router path;
False keeps the hand-rolled path as a control to prove the mock works regardless.
"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from charon import gateway
from charon.gateway import GatewayConfig

# ── mock provider: serves /models and /chat/completions ───────────────────


class _MockProvider(http.server.BaseHTTPRequestHandler):
    """A stand-in provider that serves valid chat completions."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "good-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
        self.server.seen_auths.append(self.server.seen_auth)  # type: ignore[attr-defined]
        body = json.dumps({
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 1,
            "model": "good-model",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello from mock"},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 5,
                "total_tokens": 10,
            },
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── helpers ───────────────────────────────────────────────────────────────


def _start():
    import socketserver

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _MockProvider)
    srv.seen_auth = None  # type: ignore[attr-defined]
    srv.seen_auths = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _base(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def _req(url, method="GET", token=None, body=None):
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)  # nosec B310 — test-only mock URL open
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _serve(tmp_path, *, use_litellm_router: bool = True):
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[],
                      use_litellm_router=use_litellm_router),
        setup_dir=tmp_path)
    server.serve_in_thread()
    return server


# ── the happy-path integration test ───────────────────────────────────────


@pytest.mark.parametrize("use_litellm_router", [False, True])
def test_router_happy_path_successful_completion(
        monkeypatch, tmp_path, use_litellm_router):
    """A legit provider registered with a key, a model added, and a completion
    proxied through the gateway — asserts the provider received the key, the
    response is a 200, and the model matches.

    When ``use_litellm_router=True``, this exercises the full Router dispatch
    path: ``forward_via_router`` → ``complete_via_router_tracked`` →
    ``make_router`` / ``_install_no_redirect_patch`` → 200 post-serve hooks.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    server = _serve(tmp_path, use_litellm_router=use_litellm_router)
    try:
        # Register provider
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "good", "base_url": _base(legit), "key": "sk-good"})
        assert st == 200, f"provider registration failed: {body}"

        # Register model
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "my-model", "provider": "good", "upstream_model": "good-model"})
        assert st == 200, f"model registration failed: {body}"

        # Send completion
        st, body_str = _req(server.url + "/v1/chat/completions", "POST", token="t",
                            body={"model": "my-model",
                                  "messages": [{"role": "user", "content": "hi"}]})
        assert st == 200, f"completion failed (status {st}): {body_str[:500]}"
        body = json.loads(body_str)
        assert body.get("model") == "good-model", (
            f"expected model 'good-model', got {body.get('model')!r}")
        assert legit.seen_auth == "Bearer sk-good", (
            f"provider did not receive the key: {legit.seen_auth!r}")
        assert len(legit.seen_auths) >= 1, "provider received no requests"
    finally:
        server.shutdown()
        legit.shutdown()


def test_router_build_router_handles_exception(monkeypatch, tmp_path):
    """``_build_router`` exception handler (proxy_server.py:653-654) logs a
    warning when ``make_router`` raises — covered by monkeypatching
    ``litellm.Router`` to raise on construction.

    The monkeypatch is installed BEFORE ``build_server`` so the Router is
    never successfully constructed; the server starts cleanly with the
    hand-rolled fallback."""
    pytest.importorskip("litellm")
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    import litellm
    _orig_router = litellm.Router

    def _bad_router(*args, **kwargs):
        raise RuntimeError("simulated Router construction failure")
    litellm.Router = _bad_router  # type: ignore[assignment,misc]

    try:
        server = gateway.build_server(
            GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[],
                          use_litellm_router=True),
            setup_dir=tmp_path)
        # Router construction failed → router is None (hand-rolled fallback)
        assert server.router is None, (
            f"router should be None when Router construction fails, got {server.router!r}")
    finally:
        litellm.Router = _orig_router  # type: ignore[assignment,misc]


def test_enrich_registry_called_in_load_config(monkeypatch, tmp_path):
    """``gateway.py:209`` — ``enrich_registry`` is called during ``load_config``
    when loading from a models.json file. After enrichment, the model is still
    present in the routes table."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # Write a minimal models.json with a known model
    import os
    os.makedirs(tmp_path, exist_ok=True)
    models = {"gpt-4o": {"provider": "openai"}}
    with open(tmp_path / "models.json", "w") as f:
        json.dump(models, f)

    cfg = gateway.load_config(state_dir=str(tmp_path))
    # The enriched registry should still contain the model (enrich_registry is
    # additive — it never removes entries, only adds cost_input/cost_output).
    assert "gpt-4o" in cfg.routes, (
        f"model should be in routes after enrichment, got {list(cfg.routes)}")


# ── pure-function unit tests ──────────────────────────────────────────────


def test_spend_to_record_from_branches():
    """Cover all four branches of ``_spend_to_record_from``."""
    from charon.forwarder import _spend_to_record_from
    est = 0.005

    # Branch 1: usage not a dict → est_cost
    assert _spend_to_record_from({}, est) == est
    assert _spend_to_record_from({"usage": "bad"}, est) == est

    # Branch 2: cost > 0 → cost
    assert _spend_to_record_from({"usage": {"cost": 0.01}}, est) == 0.01
    assert _spend_to_record_from({"usage": {"total_cost": 0.02}}, est) == 0.02

    # Branch 3: usage has tokens but cost ≤ 0 → 0.0
    assert _spend_to_record_from(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}, est) == 0.0
    assert _spend_to_record_from({"usage": {"total_tokens": 15}}, est) == 0.0

    # Branch 4: usage is a dict with no tokens → est_cost
    assert _spend_to_record_from({"usage": {}}, est) == est
    assert _spend_to_record_from({"usage": {"cost": 0.0, "total_cost": 0.0}}, est) == est


def test_has_assistant_turn():
    """Cover all branches of ``_has_assistant_turn``."""
    from charon.forwarder import _has_assistant_turn

    assert _has_assistant_turn(None) is False
    assert _has_assistant_turn([]) is False
    assert _has_assistant_turn([{"role": "user", "content": "hi"}]) is False
    assert _has_assistant_turn([{"role": "assistant", "content": "hello"}]) is True
    assert _has_assistant_turn([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]) is True


def test_gateway_json_use_litellm_router(monkeypatch, tmp_path):
    """Cover loading ``use_litellm_router`` from gateway.json (gateway.py:209)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # Write models.json so the state_dir branch loads
    (tmp_path / "models.json").write_text(json.dumps({"gpt-4o": {"provider": "openai"}}))
    # Write gateway.json with use_litellm_router: false
    (tmp_path / "gateway.json").write_text(json.dumps({"use_litellm_router": False}))

    cfg = gateway.load_config(state_dir=str(tmp_path))
    assert cfg.use_litellm_router is False, "gateway.json use_litellm_router should be read"

    # Verify the hand-rolled path: server built without Router
    server = gateway.build_server(cfg)
    assert server.router is None, "Router should be None when use_litellm_router=False"


def test_router_happy_path_with_default_params(monkeypatch, tmp_path):
    """Cover ``_build_upstream_req`` default-params injection (forwarder.py:217-224)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    server = _serve(tmp_path, use_litellm_router=True)
    try:
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "good", "base_url": _base(legit), "key": "sk-good"})
        assert st == 200, f"provider registration failed: {body}"

        # Register model with default_params
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "my-model", "provider": "good", "upstream_model": "good-model",
            "default_params": {"thinking": {"type": "disabled"}}})
        assert st == 200, f"model registration failed: {body}"

        # Multi-turn request (has assistant turn) — triggers reasoning suppression
        st, body_str = _req(server.url + "/v1/chat/completions", "POST", token="t",
                            body={"model": "my-model",
                                  "messages": [
                                      {"role": "user", "content": "hi"},
                                      {"role": "assistant", "content": "hello"},
                                      {"role": "user", "content": "again"},
                                  ]})
        assert st == 200, f"completion failed (status {st}): {body_str[:500]}"
    finally:
        server.shutdown()
        legit.shutdown()
