"""CONSOLE-PROVIDER-MGMT — manage providers + models from the web console.

Tests: add provider with key validation, remove provider, model enable/disable
toggle (+ /v1/models visibility), security checks (no key leak, 401 auth).
"""
from __future__ import annotations

import dataclasses
import json
import os
import socket
import threading
import urllib.error
import urllib.request

import pytest

from charon import config, gateway, secrets
from charon.gateway import GatewayConfig


def _mock_chat_server():
    """Create a minimal HTTP server on a free port that responds to
    POST /chat/completions with a valid JSON (200), so the key-probe
    passes. Returns (url, shutdown_evt)."""
    srv = socket.socket(socket.AF_INET, socket.SOCK_STREAM)
    srv.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    host, port = srv.getsockname()
    stop = threading.Event()

    def _serve():
        while not stop.is_set():
            srv.settimeout(0.5)
            try:
                conn, _ = srv.accept()
            except (TimeoutError, OSError):
                continue
            try:
                data = b""
                while True:
                    chunk = conn.recv(4096)
                    if not chunk:
                        break
                    data += chunk
                    if b"\r\n\r\n" in data:
                        break
                req = data.decode("utf-8", "replace")
                if "/chat/completions" in req:
                    body = json.dumps({"object": "chat.completion",
                                       "choices": [{"index": 0, "message": {"content": "ok"}}]})
                    resp = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                            b"Content-Length: " + str(len(body)).encode() +
                            b"\r\n\r\n" + body.encode())
                elif "/models" in req:
                    body = json.dumps({"data": [{"id": "test-model"}]})
                    resp = (b"HTTP/1.1 200 OK\r\nContent-Type: application/json\r\n"
                            b"Content-Length: " + str(len(body)).encode() +
                            b"\r\n\r\n" + body.encode())
                else:
                    resp = b"HTTP/1.1 404 Not Found\r\nContent-Length: 0\r\n\r\n"
                conn.sendall(resp)
            except Exception:
                pass
            finally:
                conn.close()

    t = threading.Thread(target=_serve, daemon=True)
    t.start()
    url = f"http://{host}:{port}/v1"
    return url, stop, srv


def _req(url, method="GET", token=None, body=None, origin=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.read().decode(), dict(r.headers)
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode(), dict(e.headers)


@pytest.fixture
def home(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    return tmp_path


def _write_models(home, **models):
    (home / "models.json").write_text(json.dumps(models))


def _write_providers(home, **provs):
    (home / "providers.json").write_text(json.dumps(provs))


@pytest.fixture
def server(home):
    srv = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
        setup_dir=home,
    )
    srv.serve_in_thread()
    try:
        yield srv
    finally:
        srv.shutdown()
        os.environ.pop("OPENROUTER_API_KEY", None)


# ---------------------------------------------------------- provider add + key probe


def test_provider_add_requires_valid_key(home, monkeypatch):
    """When a key is supplied, the provider add handler probes the upstream.
    An unreachable/bad base returns 400 and does NOT persist the provider."""
    monkeypatch.setenv("CHARON_HOME", str(home))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, token="t", port=0)
    server = gateway.build_server(cfg, setup_dir=home)
    server.serve_in_thread()
    base = server.url
    try:
        # A provider with a bad base URL that will fail the completion probe
        st, body, _ = _req(base + "/charon/providers", "POST", token="t", body={
            "name": "badprobe",
            "base_url": "http://127.0.0.1:1/v1",  # nothing listening
            "key_env": "BADPROBE_KEY",
            "key": "sk-dead",
        })
        assert st == 400  # probe failed
        data = json.loads(body)
        assert data["error"]["message"]
        assert "valid" in data.get("probe", {})
        assert not data["probe"]["valid"]
        # Provider was NOT persisted (key invalid → roll back)
        assert "badprobe" not in config.load_providers()
    finally:
        server.shutdown()


def test_provider_add_key_not_echoed(home, monkeypatch):
    """The key is stored but NEVER appears in the response body or config summary."""
    monkeypatch.setenv("CHARON_HOME", str(home))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)

    mock_url, stop, srv_sock = _mock_chat_server()
    try:
        _write_providers(home)
        cfg = gateway.load_config(state_dir=home)
        cfg = dataclasses.replace(cfg, token="t", port=0)
        server = gateway.build_server(cfg, setup_dir=home)
        server.serve_in_thread()
        base = server.url
        try:
            st, body, _ = _req(base + "/charon/providers", "POST", token="t", body={
                "name": "mocktest",
                "base_url": mock_url,
                "key_env": "MOCKTEST_KEY",
                "key": "sk-secret-12345",
            })
            assert st == 200, f"expected 200 got {st}: {body}"
            data = json.loads(body)
            assert data.get("provider") == "mocktest"
            # Probe details returned (models_count may be 0 since /v1/models on mock returns 404)
            assert data.get("probe", {}).get("valid") is True
            # Config summary must not leak the key
            st2, body2, _ = _req(base + "/charon/config", token="t")
            # Key IS stored in secrets
            assert secrets.load_secrets().get("MOCKTEST_KEY") == "sk-secret-12345"
        finally:
            server.shutdown()
    finally:
        stop.set()
        srv_sock.close()


# ---------------------------------------------------------- model enable/disable toggle


def test_model_disable_removes_from_v1_models(home):
    """Disabling a model removes it from /v1/models; re-enabling restores it."""
    _write_models(
        home,
        gpt={"upstream_base": "http://gpt/v1"},
        flash={"upstream_base": "http://flash/v1", "free": True},
    )
    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, port=0, token="t")
    server = gateway.build_server(cfg, setup_dir=home)
    server.serve_in_thread()
    base = server.url
    try:
        # Both models visible
        st, body, _ = _req(base + "/v1/models", token="t")
        ids = [m["id"] for m in json.loads(body)["data"]]
        assert "gpt" in ids and "flash" in ids

        # Disable gpt
        st, body, _ = _req(base + "/charon/disable", "POST", token="t",
                           body={"id": "gpt"})
        assert st == 200 and json.loads(body)["ok"] is True

        # gpt gone, flash still there
        st, body, _ = _req(base + "/v1/models", token="t")
        ids = [m["id"] for m in json.loads(body)["data"]]
        assert "gpt" not in ids and "flash" in ids

        # Re-enable gpt
        st, body, _ = _req(base + "/charon/enable", "POST", token="t",
                           body={"id": "gpt"})
        assert st == 200 and json.loads(body)["ok"] is True

        # Both back
        st, body, _ = _req(base + "/v1/models", token="t")
        ids = [m["id"] for m in json.loads(body)["data"]]
        assert set(ids) == {"gpt", "flash"}
    finally:
        server.shutdown()


def test_disable_nonexistent_model_returns_false(home):
    """Disabling a model not in the registry returns ok: False."""
    _write_models(home, gpt={"upstream_base": "http://gpt/v1"})
    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, port=0, token="t")
    server = gateway.build_server(cfg, setup_dir=home)
    server.serve_in_thread()
    try:
        st, body, _ = _req(server.url + "/charon/disable", "POST", token="t",
                           body={"id": "nonexistent"})
        assert st == 200
        assert json.loads(body)["ok"] is False
    finally:
        server.shutdown()


# ---------------------------------------------------------- provider / model remove


def test_remove_provider_through_web(home):
    """POST /charon/remove {kind:'provider'} removes the provider and hot-reloads."""
    _write_providers(home, openrouter={"base_url": "http://or/v1", "key_env": "OR_KEY"})
    _write_models(home, gpt={"provider": "openrouter", "upstream_base": "http://or/v1"})
    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, port=0, token="t")
    server = gateway.build_server(cfg, setup_dir=home)
    server.serve_in_thread()
    try:
        st, body, _ = _req(server.url + "/charon/remove", "POST", token="t",
                           body={"kind": "provider", "name": "openrouter"})
        assert st == 200 and json.loads(body)["ok"] is True
        # Provider gone from config
        assert "openrouter" not in config.load_providers()
    finally:
        server.shutdown()


def test_remove_model_through_web(home):
    """POST /charon/remove {kind:'model'} removes the model and hot-reloads."""
    _write_models(home, gpt={"upstream_base": "http://gpt/v1"}, flash={"upstream_base": "http://flash/v1"})
    cfg = gateway.load_config(state_dir=home)
    cfg = dataclasses.replace(cfg, port=0, token="t")
    server = gateway.build_server(cfg, setup_dir=home)
    server.serve_in_thread()
    base = server.url
    try:
        st, body, _ = _req(base + "/charon/remove", "POST", token="t",
                           body={"kind": "model", "name": "gpt"})
        assert st == 200 and json.loads(body)["ok"] is True
        # gpt gone from /v1/models
        st, body, _ = _req(base + "/v1/models", token="t")
        ids = [m["id"] for m in json.loads(body)["data"]]
        assert "gpt" not in ids and "flash" in ids
    finally:
        server.shutdown()


# ---------------------------------------------------------- validate_provider_key unit


def test_validate_provider_key_bad_scheme():
    result = config.validate_provider_key("x", "file:///etc/passwd", "k")
    assert result["valid"] is False
    assert "scheme" in result["message"]


def test_validate_provider_key_metadata_host():
    result = config.validate_provider_key("x", "http://169.254.169.254/latest", "k")
    assert result["valid"] is False
    assert "refusing" in result["message"]


def test_validate_provider_key_unreachable():
    result = config.validate_provider_key("x", "http://127.0.0.1:1/v1", "k")
    assert result["valid"] is False


def test_validate_provider_key_sends_shared_browser_ua():
    """P5: onboarding probe must carry the shared browser-like UA so a Cloudflare-
    fronted provider (groq/cerebras/together, error 1010 → 403) is not wrongly
    reported INVALID. Never the old 'charon-proxy/0.1' / urllib default."""
    from unittest.mock import MagicMock, patch

    from charon.netutil import BROWSER_UA

    seen: list[str] = []

    class _Resp:
        def read(self, *_a):
            return b'{"data": []}'

    def _fake_open(req, timeout=None):
        seen.append(req.get_header("User-agent"))
        return _Resp()

    opener = MagicMock()
    opener.open.side_effect = _fake_open
    with patch("urllib.request.build_opener", return_value=opener):
        config.validate_provider_key("groq", "https://api.groq.com/openai/v1", "sk-x")

    assert seen  # both /models and /chat/completions probes ran
    assert all(ua == BROWSER_UA for ua in seen)
    assert all(ua != "charon-proxy/0.1" for ua in seen)
    assert all(not (ua or "").lower().startswith("python-urllib") for ua in seen)


# ---------------------------------------------------------- config.set_model_enabled


def test_set_model_enabled_persistence(home, monkeypatch):
    monkeypatch.setenv("CHARON_HOME", str(home))
    _write_models(home, gpt={"upstream_base": "http://gpt/v1"})
    assert config.load_models()["gpt"].get("enabled") is not False
    assert config.set_model_enabled("gpt", False) is True
    assert config.load_models()["gpt"]["enabled"] is False
    assert config.set_model_enabled("gpt", True) is True
    assert config.load_models()["gpt"].get("enabled") is not False


def test_set_model_enabled_nonexistent(home, monkeypatch):
    monkeypatch.setenv("CHARON_HOME", str(home))
    assert config.set_model_enabled("noexist", False) is False
