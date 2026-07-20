"""Redirect refusal: the four sinks two reviewers missed, plus failover + logging.

Two independent adversarial reviews of round 4 BOTH missed four key-bearing send
sites — ``routing_proxy``, ``speculative_execution``, ``adapters/review`` and
``observability``. Round 5 routed them through the choke point but added no
redirect coverage for any of them, so their safety rested entirely on a gate that
a reviewer then defeated. This file gives each of the four a LIVE 302 test with a
real attacker socket.

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

from charon import netutil, observability, proxy, routing_proxy, speculative_execution

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


# ── the four sinks two reviewers missed ──────────────────────────────────────

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


def test_speculative_execution_does_not_follow_redirect(redirect_pair) -> None:
    provider, attacker = redirect_pair

    class _Route:
        upstream_base = provider.url + "/v1"
        upstream_model = "test-model"
        api_key = REAL_KEY
        label = "spec-provider"
        strip_v1 = False

    ex = speculative_execution.SpeculativeExecutor(enabled=True, timeout_ms=10000)
    ex.execute([_Route()], json.dumps({"model": "m", "messages": []}).encode())
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


def test_observability_langfuse_does_not_follow_redirect(redirect_pair) -> None:
    """Langfuse creds ride as BASIC, not Bearer — a different auth_scheme through
    the same choke point, so it needs its own proof."""
    provider, attacker = redirect_pair
    obs = observability.Observability({
        "langfuse_url": provider.url + "/api/public/ingestion",
        "langfuse_public_key": REAL_KEY,
        "langfuse_secret_key": "secret",
    })
    obs.export(observability.ObsEvent(event_type="t", provider="p", model="m"),
               targets=[observability.ObsTarget.LANGFUSE])
    # Basic auth base64-encodes the credential, so the raw key is not a substring.
    assert provider.seen_auths and any(
        a and a.startswith("Basic ") for a in provider.seen_auths), (
        "langfuse export never sent credentials — the leak assertion would be vacuous")
    assert not attacker.seen_auths or not any(
        a and a.startswith("Basic ") for a in attacker.seen_auths), (
        f"LANGFUSE CREDENTIALS REACHED THE REDIRECT TARGET: {attacker.seen_auths}")


def test_observability_webhook_does_not_follow_redirect(redirect_pair) -> None:
    provider, attacker = redirect_pair
    obs = observability.Observability({
        "webhook_url": provider.url + "/hook", "webhook_secret": "s"})
    obs.export(observability.ObsEvent(event_type="t", provider="p", model="m"),
               targets=[observability.ObsTarget.WEBHOOK])
    assert provider.seen_auths, "webhook never fired — nothing was proven"
    assert not attacker.seen_auths, (
        f"the webhook followed a redirect to the attacker: {attacker.seen_auths}")


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


# ── P2: one bad base must not abort the whole speculative race ───────────────

def test_bad_base_does_not_abort_the_speculative_race() -> None:
    """`_build_request` SSRF-validates and raises ValueError on a link-local base.

    Called outside any try (round 5), ONE typo'd upstream_base aborted `execute()`
    entirely and discarded every healthy route's in-flight result.
    """
    healthy = _Server(_Attacker)

    class _Bad:
        upstream_base = "http://169.254.169.254/v1"  # cloud metadata — refused
        upstream_model = "m"
        api_key = REAL_KEY
        label = "bad-route"
        strip_v1 = False

    class _Good:
        upstream_base = healthy.url + "/v1"
        upstream_model = "m"
        api_key = REAL_KEY
        label = "good-route"
        strip_v1 = False

    try:
        ex = speculative_execution.SpeculativeExecutor(enabled=True, timeout_ms=10000)
        result = ex.execute([_Bad(), _Good()],
                            json.dumps({"model": "m", "messages": []}).encode())
        assert result is not None, (
            "the malformed route took down the whole race — the healthy route's "
            "result was discarded")
        assert result.provider == "good-route"
    finally:
        healthy.close()


def test_all_bad_bases_returns_none_rather_than_raising() -> None:
    """Degenerate case: every route unbuildable must not escape as a ValueError."""

    class _Bad:
        upstream_base = "http://169.254.169.254/v1"
        upstream_model = "m"
        api_key = REAL_KEY
        label = "bad"
        strip_v1 = False

    ex = speculative_execution.SpeculativeExecutor(enabled=True, timeout_ms=5000)
    assert ex.execute([_Bad()], b'{"model":"m","messages":[]}') is None
