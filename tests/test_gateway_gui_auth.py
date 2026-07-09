"""SR-13 — friendly session login for the /charon/* web console (AUTH-GUI-DESIGN
Option C: TOFU session, the token IS the credential).

Covers the cookie sign/verify core, the surface-aware auth gate (session cookie
authorizes /charon/* ONLY — /v1/* stays byte-for-byte token-only), the login /
logout / TOFU flows, the preserved CSRF + DNS-rebinding guards, and the
`charon login` / `charon logout --all` CLI. Stdlib only; a live loopback server.
"""
from __future__ import annotations

import argparse
import http.client
import json
import time
from urllib.parse import urlencode, urlsplit

from charon import proxy_server
from charon.proxy_server import (
    GatewayProxyServer,
    _sign_session,
    _strip_token_from_path,
    _verify_session,
)

KEY = "a" * 64  # explicit session key → construction never touches the filesystem
TOKEN = "s3cret-token"


# ---- unit: cookie sign / verify -------------------------------------------

def test_sign_verify_round_trip() -> None:
    exp = int(time.time()) + 1000
    raw = _sign_session(KEY, exp)
    assert raw.count(".") == 1
    assert _verify_session(KEY, raw) == exp


def test_tampered_mac_rejected() -> None:
    raw = _sign_session(KEY, int(time.time()) + 1000)
    payload, sig = raw.split(".")
    flipped = ("0" if sig[-1] != "0" else "1")
    assert _verify_session(KEY, f"{payload}.{sig[:-1]}{flipped}") is None


def test_tampered_payload_rejected() -> None:
    # Re-encode a later exp but keep the old MAC → signature no longer matches.
    raw = _sign_session(KEY, int(time.time()) + 10)
    _, sig = raw.split(".")
    forged = proxy_server._b64url(
        json.dumps({"exp": int(time.time()) + 999999, "v": 1},
                   separators=(",", ":")).encode())
    assert _verify_session(KEY, f"{forged}.{sig}") is None


def test_wrong_key_rejected() -> None:
    raw = _sign_session(KEY, int(time.time()) + 1000)
    assert _verify_session("b" * 64, raw) is None  # rotated key invalidates sessions


def test_expired_rejected() -> None:
    raw = _sign_session(KEY, int(time.time()) - 5)
    assert _verify_session(KEY, raw) is None


def test_malformed_rejected() -> None:
    assert _verify_session(KEY, "") is None
    assert _verify_session(KEY, "nodot") is None
    assert _verify_session(KEY, ".") is None
    assert _verify_session(KEY, "a.b.c") is None


def test_sliding_reissue_extends_exp() -> None:
    old = _sign_session(KEY, int(time.time()) + 60)
    time.sleep(1.01)
    new = _sign_session(KEY, int(time.time()) + proxy_server._SESSION_TTL)
    assert _verify_session(KEY, new) > _verify_session(KEY, old)


def test_strip_token_from_path() -> None:
    assert _strip_token_from_path("/charon?token=x") == "/charon"
    assert _strip_token_from_path("/charon/setup?token=x&a=1") == "/charon/setup?a=1"
    assert _strip_token_from_path("/charon") == "/charon"


# ---- integration helpers ---------------------------------------------------

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
    """One request, NO redirect-following, returning (status, headers, body)."""
    p = urlsplit(srv.url)
    c = http.client.HTTPConnection(p.hostname, p.port, timeout=10)
    c.request(method, path, body=body, headers=headers or {})
    r = c.getresponse()
    data = r.read().decode("utf-8", "replace")
    hdrs = {k.lower(): v for k, v in r.getheaders()}
    c.close()
    return r.status, hdrs, data


def _cookie_value(set_cookie: str | None) -> str:
    assert set_cookie and set_cookie.startswith("charon_sess=")
    return set_cookie.split(";", 1)[0][len("charon_sess="):]


# ---- integration: /v1/* stays token-only -----------------------------------

def test_v1_models_bearer_ok_wrong_absent_401() -> None:
    srv = _server()
    try:
        st, _, _ = _req(srv, "/v1/models",
                        headers={"Authorization": f"Bearer {TOKEN}"})
        assert st == 200
        st, _, _ = _req(srv, "/v1/models",
                        headers={"Authorization": "Bearer nope"})
        assert st == 401
        st, _, _ = _req(srv, "/v1/models")
        assert st == 401
    finally:
        srv.shutdown()


def test_session_cookie_does_not_authorize_v1() -> None:
    srv = _server()
    try:
        sess = _sign_session(KEY, int(time.time()) + 1000)
        st, _, _ = _req(srv, "/v1/models",
                        headers={"Cookie": f"charon_sess={sess}"})
        assert st == 401  # API surface is byte-for-byte token-only
    finally:
        srv.shutdown()


# ---- integration: GUI login / logout / TOFU --------------------------------

def test_unauth_gui_get_redirects_to_login() -> None:
    srv = _server()
    try:
        st, hdrs, _ = _req(srv, "/charon")
        assert st == 302 and hdrs["location"] == "/charon/login"
        st, _, body = _req(srv, "/charon/login")
        assert st == 200 and 'action="/charon/login"' in body
    finally:
        srv.shutdown()


def test_login_post_good_token_sets_cookie_and_redirects() -> None:
    srv = _server()
    srv.setup_handler = lambda action, payload: (200, {"ok": True})
    try:
        body = urlencode({"token": TOKEN})
        st, hdrs, _ = _req(srv, "/charon/login", method="POST", body=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        })
        assert st == 302 and hdrs["location"] == "/charon"
        sess = _cookie_value(hdrs.get("set-cookie"))
        assert _verify_session(KEY, sess) is not None
        assert "httponly" in hdrs["set-cookie"].lower()
        assert "samesite=lax" in hdrs["set-cookie"].lower()
        assert "secure" not in hdrs["set-cookie"].lower()
        # follow-up with ONLY the cookie (no token) → authorized
        st, hdrs2, _ = _req(srv, "/charon/config",
                            headers={"Cookie": f"charon_sess={sess}"})
        assert st == 200
    finally:
        srv.shutdown()


def test_login_post_bad_token_rerenders_no_cookie() -> None:
    srv = _server()
    try:
        body = urlencode({"token": "wrong"})
        st, hdrs, page = _req(srv, "/charon/login", method="POST", body=body, headers={
            "Content-Type": "application/x-www-form-urlencoded",
            "Content-Length": str(len(body)),
        })
        assert st == 200
        assert "set-cookie" not in hdrs
        assert "Invalid token" in page
    finally:
        srv.shutdown()


def test_token_query_upgrades_to_cookie_and_strips_token() -> None:
    srv = _server()
    try:
        st, hdrs, _ = _req(srv, f"/charon?token={TOKEN}")
        assert st == 302
        assert hdrs["location"] == "/charon"  # token stripped from the URL
        assert _verify_session(KEY, _cookie_value(hdrs.get("set-cookie"))) is not None
    finally:
        srv.shutdown()


def test_token_still_admin_fallback_for_gui() -> None:
    srv = _server()
    try:
        # Bearer token authorizes a /charon page directly (headless recovery).
        st, _, body = _req(srv, "/charon",
                           headers={"Authorization": f"Bearer {TOKEN}"})
        assert st == 200 and "Charon Gateway" in body
    finally:
        srv.shutdown()


def test_logout_clears_cookie_and_redirects() -> None:
    srv = _server()
    try:
        st, hdrs, _ = _req(srv, "/charon/logout")
        assert st == 302 and hdrs["location"] == "/charon/login"
        assert "max-age=0" in hdrs["set-cookie"].lower()
    finally:
        srv.shutdown()


def test_sliding_refresh_reissues_cookie() -> None:
    srv = _server()
    srv.setup_handler = lambda action, payload: (200, {"ok": True})
    try:
        old_exp = int(time.time()) + 100
        sess = _sign_session(KEY, old_exp)
        st, hdrs, _ = _req(srv, "/charon/config",
                           headers={"Cookie": f"charon_sess={sess}"})
        assert st == 200
        new_exp = _verify_session(KEY, _cookie_value(hdrs.get("set-cookie")))
        assert new_exp > old_exp  # slid toward a fresh 30-day horizon
    finally:
        srv.shutdown()


def test_tampered_cookie_falls_back_to_login() -> None:
    srv = _server()
    try:
        st, hdrs, _ = _req(srv, "/charon",
                           headers={"Cookie": "charon_sess=forged.deadbeef"})
        assert st == 302 and hdrs["location"] == "/charon/login"
    finally:
        srv.shutdown()


# ---- integration: preserved guards -----------------------------------------

def test_login_post_cross_origin_refused() -> None:
    srv = _server()
    try:
        body = urlencode({"token": TOKEN})
        common = {"Content-Type": "application/x-www-form-urlencoded",
                  "Content-Length": str(len(body))}
        st, _, _ = _req(srv, "/charon/login", method="POST", body=body,
                        headers={**common, "Host": "127.0.0.1:9",
                                 "Origin": "http://evil.example"})
        assert st == 403
        st, _, _ = _req(srv, "/charon/login", method="POST", body=body,
                        headers={**common, "Sec-Fetch-Site": "cross-site"})
        assert st == 403
    finally:
        srv.shutdown()


def test_dns_rebinding_guard_intact() -> None:
    srv = _server()
    try:
        st, _, _ = _req(srv, "/charon/login", headers={"Host": "evil.example"})
        assert st == 403  # loopback bind rejects a non-loopback Host
    finally:
        srv.shutdown()


# ---- CLI -------------------------------------------------------------------

def test_cli_login_prints_click_once_url_that_authenticates(capsys) -> None:
    srv = _server()
    try:
        port = srv.server_address[1]
        from charon.cli import _cmd_login
        args = argparse.Namespace(token=TOKEN, host="127.0.0.1", port=port, open=False)
        assert _cmd_login(args) == 0
        url = capsys.readouterr().out.strip()
        assert url == f"http://127.0.0.1:{port}/charon?token={TOKEN}"
        # the printed URL lands authenticated (302 + a session cookie), token-free
        st, hdrs, _ = _req(srv, urlsplit(url).path + "?" + urlsplit(url).query)
        assert st == 302
        assert _verify_session(KEY, _cookie_value(hdrs.get("set-cookie"))) is not None
    finally:
        srv.shutdown()


def test_cli_logout_all_rotates_key_and_invalidates_old_cookie(
        tmp_path, monkeypatch, capsys) -> None:
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    from charon import secrets
    secrets.set_secret("CHARON_SESSION_KEY", "old" + "0" * 61)
    old_key = secrets.load_secrets()["CHARON_SESSION_KEY"]
    old_cookie = _sign_session(old_key, int(time.time()) + 1000)

    from charon.cli import _cmd_logout
    assert _cmd_logout(argparse.Namespace(all=True)) == 0
    new_key = secrets.load_secrets()["CHARON_SESSION_KEY"]
    assert new_key != old_key
    # an old cookie no longer verifies under the rotated key
    assert _verify_session(new_key, old_cookie) is None


def test_cli_logout_without_all_is_advisory(capsys) -> None:
    from charon.cli import _cmd_logout
    assert _cmd_logout(argparse.Namespace(all=False)) == 0
    assert "charon logout --all" in capsys.readouterr().err
