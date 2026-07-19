# check-test-patterns: allow-self-mirroring-mock
"""TOOLCALL-ROOTCAUSE retry-once fix — money-path failover classification.

Root cause (internal tool-call root-cause analysis, 2026-07-13): the "all providers
exhausted" symptom traced to raw curls was NOT a tool-call/schema bug — it was
provider funds exhaustion, but the gateway treated every 402/503 identically:

  * openrouter's 402 ("You requested up to 65536 tokens, but can only afford
    345") is a DETERMINISTIC drained key — retrying it is pointless.
  * nanogpt's 402 ("Insufficient balance after pending billing reservations")
    and its 503 are a MOMENTARY billing-reservation race that self-heals within
    milliseconds — a single same-provider retry recovers it.

Before this fix, ``forward_with_failover`` (src/charon/forwarder.py) burned a
failover slot on BOTH cases identically and could report "all providers
exhausted" even when a transient provider would have served the very next
millisecond. This module drives the real forwarder end-to-end against local
mock upstreams (loopback HTTP, no live network) and asserts the fixed
behavior: retry-once-same-provider on a transient 402/503, immediate failover
(no wasted retry) on a deterministic 402, and a genuine terminal exhaustion
only when every provider in the pool is out.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon.proxy_server import GatewayProxyServer, UpstreamRoute

_TRANSIENT_MSG = "Insufficient balance after pending billing reservations."
_DETERMINISTIC_MSG = (
    "This request requires more credits, or fewer max_tokens. You requested "
    "up to 65536 tokens, but can only afford 345 tokens."
)


class _Prog(http.server.BaseHTTPRequestHandler):
    """Mock upstream that replays a scripted sequence of responses, one per
    call (holding the last entry once the script is exhausted)."""

    def log_message(self, *a) -> None:  # silence test noise
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[assignment]
        length = int(self.headers.get("Content-Length") or 0)
        self.rfile.read(length)
        srv.calls += 1  # type: ignore[attr-defined]
        idx = min(srv.calls - 1, len(srv.responses) - 1)  # type: ignore[attr-defined]
        status, kind = srv.responses[idx]  # type: ignore[attr-defined]
        if status == 200:
            payload = json.dumps({
                "model": srv.return_model,  # type: ignore[attr-defined]
                "choices": [{"message": {"content": "ok"}}],
                "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.01},
            }).encode()
            self.send_response(200)
        else:
            msg = {"transient": _TRANSIENT_MSG,
                   "deterministic": _DETERMINISTIC_MSG}.get(kind, "error")
            payload = json.dumps({"error": {"message": msg}}).encode()
            self.send_response(status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _up(responses, return_model="m"):
    """Start a mock upstream that replays *responses* — a list of
    ``(status, kind)`` where ``kind`` is ``"transient"``/``"deterministic"``/
    ``None`` (only meaningful for non-200 statuses)."""
    srv = _Threaded(("127.0.0.1", 0), _Prog)
    srv.responses = responses  # type: ignore[attr-defined]
    srv.return_model = return_model  # type: ignore[attr-defined]
    srv.calls = 0  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url, payload):
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read()), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read()), dict(exc.headers)


def _gw(pools):
    gw = GatewayProxyServer(pools=pools)
    gw.serve_in_thread()
    return gw


def test_transient_402_recovers_on_same_provider_retry():
    """nanogpt-style transient 402 then success — served from the SAME
    provider on retry, no failover needed at all."""
    up, base = _up([(402, "transient"), (200, None)])
    gw = _gw({"v": [UpstreamRoute(base, "k")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["choices"][0]["message"]["content"] == "ok"
        assert hdrs["X-Charon-Failovers"] == "0"  # no OTHER provider was used
        assert up.calls == 2  # exactly one same-provider retry
    finally:
        gw.shutdown()
        up.shutdown()


def test_transient_503_recovers_on_same_provider_retry():
    """A bare 503 (no billing body at all) is transient by status alone."""
    up, base = _up([(503, None), (200, None)])
    gw = _gw({"v": [UpstreamRoute(base, "k")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "0"
        assert up.calls == 2
    finally:
        gw.shutdown()
        up.shutdown()


def test_deterministic_402_fails_over_without_wasting_a_retry():
    """openrouter-style deterministic 402 (drained key) → immediate failover to
    the next provider, and the drained provider is called EXACTLY ONCE (the
    retry-once path must not fire for a non-transient exhaustion)."""
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(200, None)], return_model="mb")
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["model"] == "mb"
        assert hdrs["X-Charon-Failovers"] == "1"
        assert a.calls == 1  # NOT retried — deterministic drained key
        assert b.calls == 1
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_transient_retry_still_fails_then_fails_over_to_next_provider():
    """Transient 402 retried once, still failing (the race didn't clear in
    time) → falls through to the next provider in the pool exactly as a
    deterministic exhaustion would, having spent one (and only one) retry."""
    a, base_a = _up([(402, "transient"), (402, "transient")])
    b, base_b = _up([(200, None)], return_model="mb")
    gw = _gw({"v": [UpstreamRoute(base_a, "ka", upstream_model="ma"),
                    UpstreamRoute(base_b, "kb", upstream_model="mb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["model"] == "mb"
        assert hdrs["X-Charon-Failovers"] == "1"
        assert a.calls == 2  # exactly one retry, then moved on
        assert b.calls == 1
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_providers_exhausted_still_surfaces_when_pool_genuinely_drained():
    """Both providers deterministically drained → the client sees the
    synthesized terminal exhaustion, not a false success. Neither provider is
    retried (both deterministic)."""
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(402, "deterministic")])
    gw = _gw({"v": [UpstreamRoute(base_a, "ka"), UpstreamRoute(base_b, "kb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        assert hdrs["X-Charon-Failovers"] == "2"
        assert a.calls == 1 and b.calls == 1
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_providers_exhausted_after_transient_retries_both_exhaust():
    """Both providers are transient-flavored but NEITHER recovers even after
    its one retry → still a genuine terminal exhaustion (retry-once must not
    mask a pool that is truly, if momentarily, all down), and each was
    retried exactly once (2 calls each), not looped indefinitely."""
    a, base_a = _up([(402, "transient"), (402, "transient")])
    b, base_b = _up([(503, None), (503, None)])
    gw = _gw({"v": [UpstreamRoute(base_a, "ka"), UpstreamRoute(base_b, "kb")]})
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        assert a.calls == 2 and b.calls == 2
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
