"""Setup phase — the read-WRITE web setup page: token-gated writes that persist
config + hot-reload the running gateway, with a CSRF/Origin guard and no key leak.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from charon import config, gateway, secrets
from charon.gateway import GatewayConfig


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


def test_web_setup_writes_config_and_hot_reloads(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("OPENROUTER_API_KEY", raising=False)
    server = gateway.build_server(GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
                                 setup_dir=tmp_path)
    server.serve_in_thread()
    base = server.url
    try:
        # setup page loads (gateway mode + handler wired), self-contained
        st, html, hdrs = _req(base + "/charon/setup", token="t")
        assert st == 200 and "Charon Setup" in html
        assert "http://" not in html and "https://" not in html

        # write a provider (preset) + its key
        st, _, _ = _req(base + "/charon/providers", "POST", token="t",
                        body={"name": "openrouter", "key": "sk-or"})
        assert st == 200
        assert config.load_providers()["openrouter"]["key_env"] == "OPENROUTER_API_KEY"
        assert secrets.load_secrets()["OPENROUTER_API_KEY"] == "sk-or"

        # write a model referencing it
        st, _, _ = _req(base + "/charon/models", "POST", token="t",
                        body={"id": "gpt", "provider": "openrouter", "upstream_model": "gpt-4o"})
        assert st == 200

        # HOT RELOAD: /v1/models now lists the new model with no restart
        st, body, _ = _req(base + "/v1/models", token="t")
        assert st == 200 and "gpt" in [m["id"] for m in json.loads(body)["data"]]

        # config summary exposes key_set + presets, never the key value
        st, body, _ = _req(base + "/charon/config", token="t")
        s = json.loads(body)
        assert st == 200 and s["providers"]["openrouter"]["key_set"] is True
        assert "openrouter" in s["presets"] and "sk-or" not in body
    finally:
        server.shutdown()
        os.environ.pop("OPENROUTER_API_KEY", None)


def test_web_setup_requires_token(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    server = gateway.build_server(GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
                                 setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        # no token → 401 on both read and write
        assert _req(server.url + "/charon/setup")[0] == 401
        assert _req(server.url + "/charon/providers", "POST", body={"name": "x"})[0] == 401
    finally:
        server.shutdown()


def test_web_setup_rejects_cross_origin_write(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    server = gateway.build_server(GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]),
                                 setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        st, _, _ = _req(server.url + "/charon/providers", "POST", token="t",
                        body={"name": "openrouter", "key": "x"}, origin="http://evil.example")
        assert st == 403  # CSRF: cross-origin write refused even with a (leaked) token
    finally:
        server.shutdown()


def test_web_setup_disabled_when_no_handler(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # no setup_dir → setup_handler is None → setup endpoints are not served (read-only)
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]))
    server.serve_in_thread()
    try:
        # /charon/setup falls through to the forward path → no route → 502 (not the page)
        st, body, _ = _req(server.url + "/charon/setup", token="t")
        assert st != 200 or "Charon Setup" not in body
        st, _, _ = _req(server.url + "/charon/providers", "POST", token="t", body={"name": "x"})
        assert st != 200  # write endpoint not available
    finally:
        server.shutdown()
