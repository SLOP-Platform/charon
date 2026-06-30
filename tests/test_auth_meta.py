"""DTC-3 — meta-test: every gateway write endpoint rejects unauthenticated POST."""

from __future__ import annotations

import json
import urllib.error
import urllib.request

import pytest

from charon.gateway import GatewayConfig, build_server

_WRITE_ENDPOINTS = [
    "providers",
    "models",
    "models/import",
    "pools",
    "tiers",
    "fallback",
    "enable",
    "disable",
    "remove",
]


@pytest.fixture
def charon_gateway(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    cfg = GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[])
    server = build_server(cfg, setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        yield server
    finally:
        server.shutdown()


@pytest.mark.parametrize("action", _WRITE_ENDPOINTS)
def test_write_endpoint_rejects_unauthenticated(charon_gateway, action):
    path = f"/charon/{action}"
    data = json.dumps({"dummy": True}).encode()
    req = urllib.request.Request(
        charon_gateway.url + path,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        r = urllib.request.urlopen(req, timeout=10)
        status = r.status
    except urllib.error.HTTPError as e:
        status = e.code
    assert status == 401, f"POST {path} without auth returned {status}, expected 401"
