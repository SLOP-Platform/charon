"""Tiers web-UI surface (DTC HARD REQ #3, TIER-4): the setup page's Tiers fieldset,
the ``/charon/tiers`` POST allowlist entry, and the console's read-only tier tag column.

The backend persist/reload (``config.set_tiers`` + the gateway ``"tiers"`` handler branch)
belongs to TIER-1/TIER-2; this surface only renders the fieldset and POSTs to it.
"""
from __future__ import annotations

import json
import os
import urllib.error
import urllib.request

from charon import config, gateway
from charon.gateway import GatewayConfig
from charon.proxy_server import _CONSOLE_HTML, _SETUP_HTML


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


def test_setup_page_renders_tiers_fieldset_with_member_inputs():
    """The Tiers fieldset offers a member-id input per canonical tier from ``order``."""
    assert "Tiers" in _SETUP_HTML
    for tier in config.CANONICAL_TIERS:  # low / med / high — the canonical order
        assert f"id=t{tier}" in _SETUP_HTML
    assert "setTiers()" in _SETUP_HTML
    assert "/charon/tiers" in _SETUP_HTML  # the fieldset POSTs to the TIER-2 backend


def test_console_renders_tier_tag_column():
    """The read-only console gains a tier tag column so tier vids are distinct."""
    assert "<th>tier" in _CONSOLE_HTML
    assert "class=tier" in _CONSOLE_HTML


def test_tiers_in_post_allowlist_does_not_fall_through(monkeypatch, tmp_path):
    """``/charon/tiers`` is in the hardcoded POST allowlist: the write reaches the
    setup handler (200) instead of falling through to chat-completions (→ 502)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]), setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        st, _, _ = _req(server.url + "/charon/tiers", "POST", token="t",
                        body={"order": ["low", "med", "high"],
                              "members": {"low": [], "med": [], "high": []},
                              "aliases": {"opus": "high"}})
        assert st == 200  # handled, not a 502 fall-through to the forward path
        # the POST actually persisted via the TIER-2 backend branch
        assert config.load_tiers()["aliases"]["opus"] == "high"
    finally:
        server.shutdown()


def test_tiers_post_keeps_csrf_origin_guard(monkeypatch, tmp_path):
    """Being on the allowlist, the CSRF/Origin guard covers the tiers write for free."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]), setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        st, _, _ = _req(server.url + "/charon/tiers", "POST", token="t",
                        body={"order": ["low", "med", "high"],
                              "members": {"low": [], "med": [], "high": []}, "aliases": {}},
                        origin="http://evil.example")
        assert st == 403  # cross-origin write refused even with a leaked token
    finally:
        server.shutdown()
        os.environ.pop("CHARON_HOME", None)
