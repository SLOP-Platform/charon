"""Redirect refusal: the sinks two reviewers missed, plus failover + logging.

Two independent adversarial reviews of round 4 BOTH missed four key-bearing send
sites — ``routing_proxy``, ``speculative_execution``, ``adapters/review`` and
``observability``. Round 5 routed them through the choke point but added no
redirect coverage for any of them, so their safety rested entirely on a gate that
a reviewer then defeated. This file gives each surviving site a LIVE 302 test
with a real attacker socket.

Correction (INERT-INSTANCE-DETECT, 2026-07-24): only two of those four were ever
live egress paths — ``routing_proxy`` and ``adapters/review``.
``speculative_execution`` and ``observability`` were instance-inert (constructed
by the gateway, never invoked) and have been RETIRED, so their 302 tests are gone
with them: they proved a property of code that never ran.

What survives them is the choke point itself, and it is still fully proven here.
``observability`` was the tree's only caller of ``netutil.keyed_request``'s
non-Bearer ``auth_scheme``, so that arm is now covered directly against
``netutil`` (``test_basic_auth_scheme_does_not_follow_redirect``) rather than
through a module — a stronger test, since it no longer depends on any one caller
existing.

Every test here carries a POSITIVE CONTROL asserting the credential was actually
in flight. Without it, "the attacker saw no Authorization header" passes just as
happily when the request was never made at all — which is exactly how the round-5
balance-poll test passed while sitting behind ``except Exception: return None``.
"""
from __future__ import annotations

import http.server
import json
import logging
import threading
import urllib.error

import pytest

from charon import netutil, proxy, routing_proxy

REAL_KEY = "sk-REAL-provider-secret"


class _Attacker(http.server.BaseHTTPRequestHandler):
    """The redirect target. Records anything it is handed."""

    def do_GET(self) -> None:  # noqa: N802
        self._record()

    def do_POST(self) -> None:  # noqa: N802
        self._record()

    def _record(self) -> None:
        self.server.seen_auths.append(self.headers.get("Authorization"))  # type: ignore[attr-defined]
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.end_headers()
        self.wfile.write(b'{"ok": true}')

    def log_message(self, *a: object) -> None:
        pass


def _make_redirector(attacker_url: str):
    """A provider that 302s to *attacker_url*, recording what it was sent first."""

    class _Redirector(http.server.BaseHTTPRequestHandler):
        def do_GET(self) -> None:  # noqa: N802
            self._redirect()

        def do_POST(self) -> None:  # noqa: N802
            self._redirect()

        def _redirect(self) -> None:
            self.server.seen_auths.append(self.headers.get("Authorization"))  # type: ignore[attr-defined]
            self.send_response(302)
            self.send_header("Location", attacker_url)
            self.end_headers()

        def log_message(self, *a: object) -> None:
            pass

    return _Redirector


class _Server:
    """A threaded HTTP server that records Authorization headers."""

    def __init__(self, handler) -> None:
        self.httpd = http.server.HTTPServer(("127.0.0.1", 0), handler)
        self.httpd.seen_auths = []  # type: ignore[attr-defined]
        self.thread = threading.Thread(target=self.httpd.serve_forever, daemon=True)
        self.thread.start()

    @property
    def url(self) -> str:
        return f"http://127.0.0.1:{self.httpd.server_address[1]}"

    @property
    def seen_auths(self) -> list:
        return self.httpd.seen_auths  # type: ignore[attr-defined]

    def close(self) -> None:
        self.httpd.shutdown()
        self.httpd.server_close()
        self.thread.join(timeout=5)


@pytest.fixture
def redirect_pair():
    """(provider-that-redirects, attacker-it-redirects-to)."""
    attacker = _Server(_Attacker)
    provider = _Server(_make_redirector(attacker.url + "/v1/chat/completions"))
    try:
        yield provider, attacker
    finally:
        provider.close()
        attacker.close()


def _assert_key_was_in_flight_but_not_leaked(provider: _Server, attacker: _Server) -> None:
    assert any(a and REAL_KEY in a for a in provider.seen_auths), (
        "the sink never sent the credential to the provider at all, so the "
        "no-leak assertion below would pass vacuously")
    assert not any(a and REAL_KEY in a for a in attacker.seen_auths), (
        f"THE PROVIDER KEY REACHED THE REDIRECT TARGET: {attacker.seen_auths}")


# ── the live sinks two reviewers missed ─────────────────────────────────────

def test_routing_proxy_does_not_follow_redirect(redirect_pair) -> None:
    provider, attacker = redirect_pair
    srv = routing_proxy.RoutingProxyServer(
        "127.0.0.1", 0, "test-model", provider.url + "/v1", api_key=REAL_KEY)
    thread = threading.Thread(target=srv.serve_forever, daemon=True)
    thread.start()
    try:
        req = netutil.keyed_request(
            srv.url + "/v1/chat/completions",
            data=json.dumps({"model": "test-model", "messages": []}).encode(),
            method="POST", headers={"Content-Type": "application/json"})
        try:
            netutil.open_keyed(req, timeout=10)
        except urllib.error.HTTPError:
            pass  # the proxy relays the upstream's refused 302 — that is the point
    finally:
        srv.shutdown()
        srv.server_close()
        thread.join(timeout=5)
    _assert_key_was_in_flight_but_not_leaked(provider, attacker)


def test_gateway_reviewer_does_not_follow_redirect(redirect_pair) -> None:
    from charon.adapters.review import GatewayReviewer
    from charon.types import Outcome, OutcomeStatus, WorkUnit

    provider, attacker = redirect_pair
    reviewer = GatewayReviewer(base_url=provider.url + "/v1", model="m",
                               token=REAL_KEY, timeout_s=10)
    unit = WorkUnit(task_id="u1", goal="g")
    outcome = Outcome(status=OutcomeStatus.PROGRESSED, provider="p")
    with pytest.raises(Exception):  # noqa: B017 — any failure is fine; the leak is the assertion
        reviewer.review(unit, outcome)
    _assert_key_was_in_flight_but_not_leaked(provider, attacker)


# ── P1: a refused redirect must fail over AND be diagnosable ─────────────────

@pytest.mark.parametrize("status", [301, 302, 303, 307, 308])
def test_refused_redirect_triggers_failover(status: int) -> None:
    """Round 5 left 3xx at failover=False.

    A provider doing trailing-slash canonicalisation or a regional move would
    therefore relay a bare, empty 30x straight to the agent, with no failover to
    a healthy sibling and nothing in the log.
    """
    observer = proxy.GatewayProxy()
    obs = observer.classify("some-model", status, {}, {})
    assert obs.refused_redirect is True
    assert obs.failover is True, (
        f"HTTP {status} did not trigger failover — the client gets a bare {status} "
        f"with an empty body and the gateway never tries a working sibling")
    assert "refused redirect" in obs.note


@pytest.mark.parametrize("status", [200, 400, 404, 429, 500])
def test_non_redirect_statuses_are_not_marked_refused_redirect(status: int) -> None:
    """Positive control: the 3xx arm must not swallow the existing classifications."""
    obs = proxy.GatewayProxy().classify("some-model", status, {}, {})
    assert obs.refused_redirect is False


def test_refused_redirect_is_logged_with_the_target_host(redirect_pair, caplog) -> None:
    """The operator must be able to SEE why their provider stopped working."""
    provider, attacker = redirect_pair
    req = netutil.keyed_request(provider.url + "/v1/models", api_key=REAL_KEY)
    with caplog.at_level(logging.WARNING):
        with pytest.raises(urllib.error.HTTPError):
            netutil.open_keyed(req, timeout=10)
    assert "refused redirect" in caplog.text
    assert "127.0.0.1" in caplog.text, f"the refused Location host is not named: {caplog.text}"


# ── the non-Bearer auth arm, re-homed off the retired `observability` module ──

def test_basic_auth_scheme_does_not_follow_redirect(redirect_pair) -> None:
    """`netutil.keyed_request(auth_scheme=...)` must refuse redirects for EVERY
    scheme, not just Bearer.

    This arm used to be proven through `observability`'s Langfuse export, which
    was the tree's only non-Bearer caller. That module is retired, so the
    property is asserted straight against the choke point — where it actually
    lives. Without this, `auth_scheme` would have zero coverage and a future
    Basic-auth caller would inherit an unproven path.
    """
    provider, attacker = redirect_pair
    req = netutil.keyed_request(
        provider.url + "/api/public/ingestion",
        api_key="cHVibGljOnNlY3JldA==",
        auth_scheme="Basic",
        data=b"{}", method="POST",
        headers={"Content-Type": "application/json"})
    try:
        netutil.open_keyed(req, timeout=10)
    except urllib.error.HTTPError:
        pass  # the refused 302 surfaces as an error — that is the point

    assert provider.seen_auths and any(
        a and a.startswith("Basic ") for a in provider.seen_auths), (
        "no Basic credential was ever in flight — the leak assertion below "
        "would pass vacuously")
    assert not any(
        a and a.startswith("Basic ") for a in attacker.seen_auths), (
        f"BASIC CREDENTIALS REACHED THE REDIRECT TARGET: {attacker.seen_auths}")
