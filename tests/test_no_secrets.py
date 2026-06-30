"""DTC-3 — meta-test: no HTTP response body from the gateway leaks a known secret."""

from __future__ import annotations

import json
import re
import urllib.error
import urllib.request

import pytest

from charon.gateway import GatewayConfig, build_server
from charon.proxy_server import UpstreamRoute

_LITERAL_SECRETS = [
    "TOPSECRET",
    "TOKEN1",
    "sk-secret-12345",
    "sk-or",
    "sk-dead",
    "sk-xyz",
    "sk-LEAKED",
    "sk-test-api-key-",
]

_SECRET_REGEX = [
    re.compile(r"\bsk-[a-zA-Z0-9\-_]{20,}\b"),
    re.compile(r"Bearer [A-Za-z0-9+/=]{32,}"),
]


def _req(url, method="GET", token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


_GET_ENDPOINTS = [
    "/v1/models",
    "/charon/config",
    "/charon/setup",
    "/charon/status",
    "/",
    "/charon",
]

_POST_ENDPOINTS = [
    ("/charon/providers", {"name": "openrouter"}),
    ("/charon/models", {"id": "testmodel"}),
    ("/charon/models/import", {"provider": "openrouter"}),
    ("/charon/pools", {"id": "auto", "members": ["m1"]}),
    ("/charon/tiers", {}),
    ("/charon/fallback", {}),
    ("/charon/enable", {"id": "m1"}),
    ("/charon/disable", {"id": "m1"}),
    ("/charon/remove", {"kind": "model", "name": "m1"}),
]


@pytest.fixture
def gateway_with_secrets(monkeypatch, tmp_path, mock_upstream):
    mock_url, _, _ = mock_upstream
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    api_key = "sk-test-api-key-0123456789abcdef"
    token = "gateway-token-secret"

    cfg = GatewayConfig(
        host="127.0.0.1",
        port=0,
        token=token,
        routes={"m1": UpstreamRoute(mock_url, api_key=api_key)},
        model_ids=["m1"],
    )
    server = build_server(cfg, setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        yield server, token, api_key
    finally:
        server.shutdown()


def _check_secrets(body, label, all_secrets, patterns):
    for secret in all_secrets:
        assert secret not in body, (
            f"{label}: response body leaked {secret!r}"
        )
    for pattern in patterns:
        match = pattern.search(body)
        assert not match, (
            f"{label}: response body matched secret pattern {pattern.pattern!r}: "
            f"{match.group(0)!r}"
        )


@pytest.mark.parametrize("path", _GET_ENDPOINTS)
def test_get_endpoint_response_no_secrets(gateway_with_secrets, path):
    server, token, api_key = gateway_with_secrets
    status, body = _req(server.url + path, token=token)
    all_secrets = [api_key, token] + _LITERAL_SECRETS
    _check_secrets(body, f"GET {path} (status {status})", all_secrets, _SECRET_REGEX)


@pytest.mark.parametrize("path,payload", _POST_ENDPOINTS)
def test_post_endpoint_response_no_secrets(gateway_with_secrets, path, payload):
    server, token, api_key = gateway_with_secrets
    status, body = _req(server.url + path, method="POST", token=token, body=payload)
    all_secrets = [api_key, token] + _LITERAL_SECRETS
    _check_secrets(body, f"POST {path} (status {status})", all_secrets, _SECRET_REGEX)


def test_chat_completions_response_no_secrets(gateway_with_secrets):
    server, token, api_key = gateway_with_secrets
    status, body = _req(
        server.url + "/v1/chat/completions",
        method="POST",
        token=token,
        body={"model": "m1", "messages": [{"role": "user", "content": "hello"}]},
    )
    all_secrets = [api_key, token] + _LITERAL_SECRETS
    _check_secrets(body, "POST /v1/chat/completions", all_secrets, _SECRET_REGEX)
