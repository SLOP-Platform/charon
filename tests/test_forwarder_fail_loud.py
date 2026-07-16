"""FAIL-LOUD-CONTRACT (ADR-0016 step #5) — terminal-error legibility.

The terminal ``all_providers_exhausted`` synthesis is a money-path surface:
when every capable provider in the chain is out, the client sees a structured
envelope listing WHICH providers were tried, WHY each failed, WHEN it
re-arms, and WHEN the soonest member recovers (``Retry-After``) — so an
operator does not have to read logs to learn why spend stalled.

The companion invariant: a genuine client-error (401-bad-key / 400) on a
single-upstream gateway is RELAYED transparently (NOT wrapped in the
synthesized envelope, NO synthesized ``Retry-After``). The 4xx-relay vs
exhaustion-synth distinction is preserved — a misleading terminal error
hides why spend stalled (charon-silent-downgrade-leak).

Each test is FAIL-ON-REVERT:

* Reverting ``providers_tried`` → structured envelope test RED.
* Reverting the bounded ``Retry-After`` → bounded-retry test RED.
* Reverting the 4xx-relay distinction → auth-relay test RED.
* Hand-fabricated placeholder class/rearm strings → balance-tracker
  sourcing test RED.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute

_DETERMINISTIC_MSG = (
    "This request requires more credits, or fewer max_tokens. You requested "
    "up to 65536 tokens, but can only afford 345 tokens."
)
_TRANSIENT_MSG = "Insufficient balance after pending billing reservations."
_BAD_KEY_MSG = "Invalid API key. Check your key and try again."


# ---------------------------------------------------------------------------
# Mock upstream — replays a scripted (status, kind) sequence, one per call.
# ---------------------------------------------------------------------------


class _Prog(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
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
        else:
            msg = {"transient": _TRANSIENT_MSG,
                   "deterministic": _DETERMINISTIC_MSG,
                   "bad_key": _BAD_KEY_MSG}.get(kind, "error")
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


def _gw(pools, *, balance_cfg: dict | None = None):
    bt = BalanceTracker(config=balance_cfg) if balance_cfg else None
    gw = GatewayProxyServer(pools=pools, balance_tracker=bt)
    gw.serve_in_thread()
    return gw, bt


# ---------------------------------------------------------------------------
# 1. Structured envelope — providers_tried carries per-attempt breakdown.
# ---------------------------------------------------------------------------


def test_all_providers_exhausted_carries_structured_per_provider_breakdown():
    """Every capable provider in the chain returns an exhaustion signal →
    client sees a 503 with type=='all_providers_exhausted' AND a
    ``providers_tried`` array of one entry per attempted provider, each
    carrying provider+status+reason+class+rearm. The operator can read why
    each failed without consulting logs.

    FAIL-ON-REVERT: reverting the ``providers_tried`` synthesis leaves the
    body without that field → ``KeyError`` on lookup → RED.
    """
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(402, "deterministic")])
    # Real per-provider funding-class config so the class/rearm fields are
    # sourced from balance_tracker (not a hand-fabricated placeholder).
    balance_cfg = {
        "drained-a": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 3},
        "drained-b": {"mode": "fixed", "starting_balance": 1.0, "funding_class": 1},
    }
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="drained-a"),
                   UpstreamRoute(base_b, "kb", provider="drained-b")]}
    gw, bt = _gw(pools, balance_cfg=balance_cfg)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        # Structured envelope per ADR-0016 step #5 body schema.
        assert body["error"]["requested_model"] == "v"
        assert body["error"]["no_provider_reason"] is None
        # One entry per attempted provider — the two pool members, in
        # failover order.
        tried = body["error"]["providers_tried"]
        assert isinstance(tried, list)
        assert len(tried) == 2
        providers = [t["provider"] for t in tried]
        assert providers == ["drained-a", "drained-b"] or providers == ["drained-b", "drained-a"]
        # Every entry carries ALL five required fields — provider, status,
        # reason, class, rearm. None of them is None (the field is always
        # populated, even if class is "unknown" when no funding_class
        # config is supplied).
        for entry in tried:
            for key in ("provider", "status", "reason", "class", "rearm"):
                assert key in entry, f"missing {key!r} in {entry!r}"
                assert entry[key] is not None, f"null {key!r} in {entry!r}"
        # Class is sourced from funding_class: a=3 (drain-then-park), b=1
        # (free-recurring). The class strings must match the canonical
        # taxonomy — not invented placeholders.
        by_prov = {e["provider"]: e for e in tried}
        assert by_prov["drained-a"]["class"] == "drain-then-park"
        assert by_prov["drained-a"]["rearm"] == "operator top-up"
        assert by_prov["drained-b"]["class"] == "free-recurring"
        assert by_prov["drained-b"]["rearm"].startswith("auto reset")
        # The plain text reason string from the proxy's classify() taxonomy
        # is preserved (not replaced by the structured class/rearm).
        assert "exhausted" in by_prov["drained-a"]["reason"].lower()
        # Legacy failover_reasons kept for back-compat with the existing
        # X-Charon-Failover-Reasons header consumer.
        assert "drained-a=402" in body["error"]["failover_reasons"][0] or \
               body["error"]["failover_reasons"][0].startswith("drained-b=402")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


# ---------------------------------------------------------------------------
# 2. Bounded Retry-After — uses the soonest chain member recovery, not unbounded.
# ---------------------------------------------------------------------------


def test_retry_after_within_max_cooldown():
    """The terminal 503 carries a ``Retry-After`` header (and matching
    ``retry_after_s`` envelope field) bounded to ``[1, max_cooldown_s]`` —
    the gateway owns retry cadence (P1), the client never sees an
    unbounded or 0 backoff that would mask a transient chain recovery.

    FAIL-ON-REVERT: dropping the bounded retry-after synthesis → header is
    either missing or zero → RED.
    """
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(429, None)])
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="prov-a"),
                   UpstreamRoute(base_b, "kb", provider="prov-b")]}
    gw, _bt = _gw(pools)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        # Body field mirrors the header (the operator's structured view of
        # the same value).
        ra = body["error"]["retry_after_s"]
        assert isinstance(ra, int) and ra >= 1
        assert ra <= gw.max_cooldown_s, (
            f"retry_after_s={ra} exceeds max_cooldown_s={gw.max_cooldown_s}")
        # Header must be present and within the same bound.
        hdr_ra = int(hdrs["Retry-After"])
        assert 1 <= hdr_ra <= gw.max_cooldown_s
        assert hdr_ra == ra  # header and body field are the same value
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


# ---------------------------------------------------------------------------
# 3. 4xx-relay distinction — bad key is RELAYED, never wrapped in synth.
# ---------------------------------------------------------------------------


def test_auth_error_is_relayed_transparently_no_synthesized_envelope():
    """A 401-bad-key on a single-upstream gateway is RELAYED transparently
    to the client — NOT wrapped in the synthesized exhaustion envelope, NO
    synthesized ``Retry-After``. Relaying a real auth failure is the
    correct behavior (every other provider would reject the same bad key;
    failing over is pointless). Wrapping it would be the
    silent-downgrade-leak the ADR-0016 step #5 money-path hardens against.

    FAIL-ON-REVERT: collapsing the 4xx-relay and exhaustion-synth branches
    (e.g. by removing the ``if obs.failover`` guard) wraps the real auth
    error in ``type: all_providers_exhausted`` and synthesizes a
    ``Retry-After`` → both assertions fail → RED.
    """
    a, base_a = _up([(401, "bad_key")])
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="solo-prov")]}
    gw, _bt = _gw(pools)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        # Real upstream status (401), NOT the synthesized 503.
        assert status == 401
        # The body is the upstream error envelope — NOT the synthesized
        # ``all_providers_exhausted`` shape.
        assert "type" not in body.get("error", {}) or \
               body["error"].get("type") != "all_providers_exhausted"
        assert "providers_tried" not in body.get("error", {})
        # The real upstream message is preserved verbatim.
        assert "Invalid API key" in body["error"]["message"]
        # No synthesized Retry-After on a non-retry-worthy 4xx.
        assert "Retry-After" not in hdrs
        # The X-Charon-Failover-Reasons header records the path: zero
        # failovers (we relayed, not failed over).
        assert hdrs.get("X-Charon-Failovers") == "0"
    finally:
        gw.shutdown()
        a.shutdown()


def test_400_bad_request_is_relayed_transparently():
    """A 400 (bad request body) is also RELAYED — same 4xx-relay invariant.
    Different status, same logic: a client-side error is not a chain
    exhaustion, and relaying the real upstream error is the only honest
    response (otherwise the client can never learn that their payload is
    wrong)."""
    a, base_a = _up([(400, None)])
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="solo-prov")]}
    gw, _bt = _gw(pools)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 400
        assert "providers_tried" not in body.get("error", {})
        assert "Retry-After" not in hdrs
    finally:
        gw.shutdown()
        a.shutdown()


def test_auth_error_on_multi_provider_pool_is_relayed_not_synthesized():
    """A genuine 401-bad-key on a MULTI-provider pool is RELAYED from the
    FIRST provider (HTTP 401) — NOT failed over across the pool and NOT
    wrapped in the synthesized ``all_providers_exhausted`` 503 envelope.

    This is the actual money-path distinction ADR-0016 step #5 hardens:
    every provider rejects the same bad key, so failing over is pointless
    churn that masks the real cause (a dead key). The solo-upstream relay
    test above can't lock this — on a single route ``more`` is always
    False, so the synth branch (gated on a non-empty ``failovers`` list) is
    unreachable regardless of how the 401 is classified. A multi-provider
    pool makes the synth path reachable, so a 401 misclassified as
    exhaustion would leak into the synthesized envelope here.

    FAIL-ON-REVERT: collapsing the 4xx-relay distinction (e.g. classifying a
    genuine 401-bad-key as ``exhausted`` in ``proxy._is_billing_error``,
    or forcing ``obs.failover`` True) routes the 401 into the failover
    loop → both providers 401 → the synth 503 envelope fires with
    ``type: all_providers_exhausted`` and a synthesized ``Retry-After``
    → every assertion below RED.
    """
    a, base_a = _up([(401, "bad_key")])
    b, base_b = _up([(401, "bad_key")])
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="prov-a"),
                   UpstreamRoute(base_b, "kb", provider="prov-b")]}
    gw, _bt = _gw(pools)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        # Real upstream 401, NOT the synthesized 503.
        assert status == 401, (
            f"expected relayed 401, got synth {status}: {body!r}")
        # The body is the upstream error envelope — NOT the synthesized
        # ``all_providers_exhausted`` shape.
        assert body["error"].get("type") != "all_providers_exhausted", (
            f"4xx-relay leak: 401-bad-key was wrapped in synth envelope: {body!r}")
        assert "providers_tried" not in body.get("error", {})
        # The real upstream message is preserved verbatim.
        assert "Invalid API key" in body["error"]["message"]
        # No synthesized Retry-After on a non-retry-worthy 4xx.
        assert "Retry-After" not in hdrs
        # No failover happened — the 401 was relayed on the first provider.
        assert hdrs.get("X-Charon-Failovers") == "0"
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


# ---------------------------------------------------------------------------
# 4. Unknown funding class → ("unknown", "unknown"), never KeyError.
# ---------------------------------------------------------------------------


def test_class_and_rearm_default_to_unknown_when_balance_tracker_unconfigured():
    """When no balance_tracker / funding_class is configured (plain API-key
    providers — the default for most installs), the class/rearm fields
    must STILL be present (the field is required for legibility) and
    degrade gracefully to ``"unknown"``. Never a KeyError, never missing
    keys — that would crash the response build path and turn a money-path
    503 into a 500.

    FAIL-ON-REVERT: making the field lookup require a non-None
    balance_tracker → KeyError or AttributeError on a default-config
    install → RED.
    """
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(402, "deterministic")])
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="plain-a"),
                   UpstreamRoute(base_b, "kb", provider="plain-b")]}
    # No balance_cfg → no balance_tracker → unknown class/rearm.
    gw, _bt = _gw(pools)
    try:
        status, body, _hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        tried = body["error"]["providers_tried"]
        assert len(tried) == 2
        for entry in tried:
            assert entry["class"] == "unknown"
            assert entry["rearm"] == "unknown"
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()
