"""AUTH-302 — unauthenticated console requests must never return 302 + 0 bytes.

Decision procedure (RFC 7235-aligned):
  1. ``Authorization`` header present but rejected → 401 JSON, always.
  2. No credential AND ``Accept:`` contains ``text/html`` → 302 login (browser UX).
  3. Otherwise → 401 JSON.

This test file proves the fix is RED-then-GREEN on each branch and guards
against regressions in the /v1/* data plane (which stays token-only).
"""
from __future__ import annotations

import http.client
import json
from urllib.parse import urlsplit

from charon.proxy_server import GatewayProxyServer, _sign_session

KEY = "b" * 64
TOKEN = "s3cret-token"


def _server(**kw) -> GatewayProxyServer:
    srv = GatewayProxyServer(
        upstream_base="http://127.0.0.1:1/v1",
        token=TOKEN,
        session_key=KEY,
        model_ids=["m1"],
        host="127.0.0.1",
        **kw,
    )
    srv.serve_in_thread()
    return srv


def _req(srv, path, *, method="GET", headers=None, body=None):
    p = urlsplit(srv.url)
    c = http.client.HTTPConnection(p.hostname, p.port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read().decode("utf-8", "replace")
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, hdrs, data


# ---- Branch 1: invalid Authorization header → 401 JSON (always) -------------

def test_invalid_bearer_returns_401_not_302() -> None:
    srv = _server()
    try:
        st, hdrs, body = _req(srv, "/charon/status",
                               headers={"Authorization": "Bearer wrong-token"})
        assert st == 401, f"expected 401, got {st}"
        assert "text/html" not in hdrs.get("content-type", "")
        parsed = json.loads(body)
        assert parsed == {"error": {"message": "missing or invalid bearer token"}}
    finally:
        srv.shutdown()


def test_invalid_bearer_on_v1_returns_401() -> None:
    srv = _server()
    try:
        st, _, body = _req(srv, "/v1/models",
                            headers={"Authorization": "Bearer stale"})
        assert st == 401
        parsed = json.loads(body)
        assert parsed == {"error": {"message": "missing or invalid bearer token"}}
    finally:
        srv.shutdown()


def test_valid_bearer_on_v1_returns_200() -> None:
    srv = _server()
    try:
        st, _, _ = _req(srv, "/v1/models",
                         headers={"Authorization": f"Bearer {TOKEN}"})
        assert st == 200
    finally:
        srv.shutdown()


# ---- Branch 2: no credential + Accept: text/html → 302 login (browser) ------

def test_no_cred_accept_html_returns_302_to_login() -> None:
    srv = _server()
    try:
        st, hdrs, body = _req(srv, "/charon/status",
                               headers={"Accept": "text/html"})
        assert st == 302, f"expected 302, got {st}"
        assert hdrs.get("location") == "/charon/login"
        assert len(body) == 0
    finally:
        srv.shutdown()


def test_no_cred_accept_wildcard_returns_302_to_login() -> None:
    srv = _server()
    try:
        st, hdrs, _ = _req(srv, "/charon/status",
                            headers={"Accept": "*/*"})
        assert st == 302
        assert hdrs.get("location") == "/charon/login"
    finally:
        srv.shutdown()


# ---- Branch 3: no credential + no Accept: text/html → 401 JSON (script) ---

def test_no_cred_accept_json_returns_401_with_body() -> None:
    srv = _server()
    try:
        st, hdrs, body = _req(srv, "/charon/status",
                               headers={"Accept": "application/json"})
        assert st == 401, f"expected 401, got {st}"
        assert "text/html" not in hdrs.get("content-type", "")
        parsed = json.loads(body)
        assert parsed == {"error": {"message": "missing or invalid bearer token"}}
    finally:
        srv.shutdown()


def test_no_cred_accept_unspecified_returns_401() -> None:
    srv = _server()
    try:
        st, _, body = _req(srv, "/charon/status",
                            headers={"Accept": "application/octet-stream"})
        assert st == 401
        parsed = json.loads(body)
        assert parsed == {"error": {"message": "missing or invalid bearer token"}}
    finally:
        srv.shutdown()


# ---- Valid token on /charon/* still works -----------------------------------

def test_valid_bearer_on_console_returns_200() -> None:
    srv = _server()
    try:
        st, _, body = _req(srv, "/charon/status",
                            headers={"Authorization": f"Bearer {TOKEN}"})
        assert st == 200
        assert "Charon" in body
    finally:
        srv.shutdown()


# ---- Session cookie still works (TOFU UX, browser-only) --------------------

def test_valid_session_cookie_on_console_returns_200() -> None:
    srv = _server()
    try:
        sess = _sign_session(KEY, 9999999999)
        st, _, body = _req(srv, "/charon/status",
                            headers={"Cookie": f"charon_sess={sess}"})
        assert st == 200
        assert "Charon" in body
    finally:
        srv.shutdown()


def test_valid_session_cookie_on_v1_returns_401() -> None:
    srv = _server()
    try:
        sess = _sign_session(KEY, 9999999999)
        st, _, body = _req(srv, "/v1/models",
                            headers={"Cookie": f"charon_sess={sess}"})
        assert st == 401
        parsed = json.loads(body)
        assert parsed == {"error": {"message": "missing or invalid bearer token"}}
    finally:
        srv.shutdown()
