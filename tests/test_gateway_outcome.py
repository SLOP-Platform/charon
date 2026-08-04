"""OUTCOME test for the gateway money path — asserts WHAT the client observed.

Implements §3 of ``OUTCOME-TEST-BLUEPRINT.md`` (§1 is a fake test: it injects no
fault, so it is green on a gateway with no failover at all). Three of §3's
mechanisms were rejected as unimplementable-against-reality and replaced with the
real observable surfaces (see REJECTED, below).

Every assertion here is on something a CLIENT can see:
  * the real HTTP status code the gateway returned,
  * the real response envelope it wrote,
  * the real ``X-Charon-*`` visibility headers,
  * whether a real HTTP request actually arrived at a mock upstream's socket.

Nothing here asserts that a function was called, and nothing consults a
"healthy"/"ok" signal. Hermetic: the only upstreams are loopback mocks booted by
this file, so the money path is never really spent.

DOCTRINE — "could not check" is never "passed":
  * no ``skip``/``xfail``/``importorskip`` anywhere in this file — a missing
    prerequisite must be RED, not green-with-a-skip;
  * ``_post`` converts "no HTTP response" and "no response within the deadline"
    into distinct, loud AssertionErrors, so a stranded or hung request can never
    be silently read as a pass;
  * INFRA faults (harness/mock/gateway did not come up) carry an ``INFRA:``
    message and their own test, so they can never be reported as a failover
    BEHAVIOUR failure (blueprint §2.2).

REJECTED from §3, because the thing it names does not exist in this repo
(verified 2026-08-03 on feat/outcome-test-owed):
  * ``run_gateway_pipeline.py`` — no such file on any branch. §3 keeps §1's D2
    defect here: with the runner absent, ``test_runner_exists`` and the
    ``rc != 127`` guard produce a RED that says nothing about failover.
  * ``CHARON_FAULT_INJECT`` / ``CHARON_UPSTREAM_MODE`` / ``CHARON_LEDGER_PATH`` —
    no such hooks exist (zero hits in src/ or tools/). ``monkeypatch.setenv`` on
    a name nothing reads injects NO fault, which resurrects §1's fatal defect
    inside §3. The fault is therefore injected where the gateway genuinely sees
    one: at the upstream (a real 429/402 response, or a parked provider).
  * the per-attempt "ledger with attempts" — ``src/charon/ledger.py`` is the WORK
    ledger (orchestration tasks) and is not wired into ``forwarder.py`` or
    ``proxy_server.py`` at all. The gateway's real per-attempt record is the
    ``providers_tried`` envelope + ``X-Charon-Failover*`` headers, asserted below.
  * ``status in (200, "EXHAUSTED")`` as one assertion — too weak to fail: with a
    healthy leg present, exhaustion is a BUG, and that disjunction passes it.
    Each scenario below pins ONE required terminal state.

AGENT HANDOVER MANIFEST
  GOAL: with the first leg forced to fail (or every leg parked), the gateway must
        reach a well-formed terminal state and name the legs it tried.
  NOT ENFORCED MECHANICALLY: the file-hash integrity gate that §3 claims
        guards this file DOES NOT EXIST. This paragraph is prose, and prose does
        not gate (blueprint §2.5) — do not read it as protection.
  NEXT AGENT: if this file goes red, fix the ROUTING CODE. Weakening an assertion
        here re-opens forwarder.py's never-strand / park-exclusion blind spots.
"""
from __future__ import annotations

import http.client
import json
import threading
import urllib.error
import urllib.request
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

import pytest

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute

# Bound on every request: a hang is a failure class here, not a stall to wait out.
_DEADLINE_S = 10


class _MockUpstream(ThreadingHTTPServer):
    """Loopback upstream with DECLARED, typed state.

    The programmable response and the record of what really arrived live on this
    subclass with real annotations — not as attributes bolted onto a stock
    ``HTTPServer`` instance, which is untypeable and hides typos until runtime.
    """

    daemon_threads = True
    allow_reuse_address = True

    def __init__(self, handler: type[BaseHTTPRequestHandler], *, status: int,
                 return_model: str, cost: float) -> None:
        super().__init__(("127.0.0.1", 0), handler)
        self.status: int = status              # status this upstream answers with
        self.return_model: str = return_model  # `model` echoed in a 200 body
        self.cost: float = cost                # usage.cost reported on a 200
        self.received: list[str | None] = []   # models really POSTed to this socket

    @property
    def base_url(self) -> str:
        """``http://host:port`` for this bound socket (host decoded, never ``b'..'``)."""
        host, port = self.server_address[0], self.server_address[1]
        if isinstance(host, bytes):
            host = host.decode()
        return f"http://{host}:{port}"


class _UpstreamHandler(BaseHTTPRequestHandler):
    """Programmable loopback upstream that records the requests it really got."""

    def log_message(self, *a: object) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server
        # Real runtime check (not a typing escape hatch): this handler is only
        # valid on the typed server above, and mypy narrows off the same fact.
        assert isinstance(srv, _MockUpstream), (
            f"INFRA: handler bound to {type(srv).__name__}, not _MockUpstream")
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        srv.received.append(body.get("model"))
        if srv.status == 200:
            payload = json.dumps({
                "model": srv.return_model,
                "choices": [{"message": {"role": "assistant", "content": "served"}}],
                "usage": {"prompt_tokens": 2, "completion_tokens": 3, "cost": srv.cost},
            }).encode()
        else:
            payload = json.dumps({"error": {
                "message": "quota exhausted",
                "metadata": {"error_type": "rate_limit_exceeded"}}}).encode()
        self.send_response(srv.status)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _boot(status: int = 200, return_model: str = "m",
          cost: float = 0.0) -> tuple[_MockUpstream, str]:
    """Boot one loopback upstream; return (server, base_url)."""
    srv = _MockUpstream(_UpstreamHandler, status=status,
                        return_model=return_model, cost=cost)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, srv.base_url


def _post(url: str, payload: dict) -> tuple[int, dict, dict]:
    """POST and return (status, body, headers).

    A gateway that answers with NO HTTP response (stranded request: the forwarder
    fell off the end of its route loop without writing anything) or that does not
    answer inside the deadline (hang) raises a loud, specifically-worded
    AssertionError — neither is ever allowed to read as a pass.
    """
    req = urllib.request.Request(
        url, data=json.dumps(payload).encode(),
        headers={"Content-Type": "application/json"}, method="POST")
    try:
        resp = urllib.request.urlopen(req, timeout=_DEADLINE_S)
        return resp.status, json.loads(resp.read() or b"{}"), dict(resp.headers)
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read() or b"{}"), dict(exc.headers)
    except TimeoutError as exc:
        raise AssertionError(
            f"BEHAVIOUR (hang): no response from {url} within {_DEADLINE_S}s "
            f"({exc!r}). A request that never terminates is a failure, not a wait."
        ) from exc
    except (http.client.RemoteDisconnected, urllib.error.URLError) as exc:
        raise AssertionError(
            f"BEHAVIOUR (stranded): the gateway closed the connection without "
            f"writing any HTTP response ({exc!r}). The request reached no "
            f"provider and produced no terminal state."
        ) from exc


def _get_json_or_infra_fail(url: str) -> dict:
    """GET and parse JSON; any transport/HTTP fault becomes an INFRA-worded
    AssertionError so a harness/route fault is never mistaken for a behaviour
    failure (and is never swallowed as "could not check")."""
    try:
        with urllib.request.urlopen(url, timeout=_DEADLINE_S) as resp:
            assert resp.status == 200, f"INFRA: {url} answered {resp.status}"
            return json.loads(resp.read() or b"{}")
    except (urllib.error.URLError, http.client.HTTPException, TimeoutError,
            json.JSONDecodeError) as exc:
        raise AssertionError(f"INFRA: {url} is not usable ({exc!r})") from exc


def _gateway(pools: dict, balance_tracker=None) -> GatewayProxyServer:
    gw = GatewayProxyServer(pools=pools, balance_tracker=balance_tracker)
    gw.serve_in_thread()
    assert gw.url.startswith("http://"), f"INFRA: gateway did not bind ({gw.url!r})"
    return gw


def _assert_real_completion(body: dict, hdrs: dict, *, served_by: str) -> None:
    """A 200 must carry a real payload — a success with no content is the worst
    outcome (blueprint §2.3). Asserts the TOP-LEVEL envelope contract too, so a
    foreign envelope cannot pass by having the right insides."""
    assert "choices" in body, f"BEHAVIOUR: 200 without a `choices` envelope: {body!r}"
    assert body.get("usage"), f"BEHAVIOUR: 200 without a `usage` block: {body!r}"
    content = body["choices"][0]["message"]["content"]
    assert content, "BEHAVIOUR: 200 with an empty completion — silent success"
    assert hdrs.get("X-Charon-Provider") == served_by, (
        f"BEHAVIOUR: served by {hdrs.get('X-Charon-Provider')!r}, "
        f"expected {served_by!r}")


def test_infra_harness_and_gateway_come_up() -> None:
    """INFRA gate: the mock upstream and the gateway are really live.

    Kept separate and INFRA-worded so a broken harness can never be reported as
    a failover behaviour failure (blueprint §2.2 — "could not run" and "ran and
    got the wrong answer" must never share a message).
    """
    up, base = _boot(status=200, return_model="m")
    try:
        status, body, _ = _post(base, {"model": "m"})
        assert status == 200, f"INFRA: mock upstream answered {status}, not 200"
        assert "choices" in body, f"INFRA: mock upstream envelope is wrong: {body!r}"
        # model_ids → gateway mode; /charon/status is served only in that mode.
        gw = GatewayProxyServer(pools={"v": [UpstreamRoute(base, "k", provider="pa")]},
                                model_ids=["v"])
        gw.serve_in_thread()
        try:
            snap = _get_json_or_infra_fail(gw.url + "/charon/status")
            assert "v" in snap.get("pools", {}), f"INFRA: pool not registered: {snap!r}"
        finally:
            gw.shutdown()
    finally:
        up.shutdown()


def test_all_legs_parked_still_serves_a_real_200_and_never_strands() -> None:
    """Every leg of the pool parked → the client still gets a REAL 200.

    Covers the never-strand fallback at forwarder.py:481-487, which today has no
    client-observable coverage anywhere in tests/ (the drain/park suites assert
    ``bt.is_parked`` internal state, not what the caller received). This is the
    live-relevant case: 7 providers are parked on the running gateway, so a pool
    whose every leg is parked is reachable in production.
    """
    up_a, base_a = _boot(status=200, return_model="ma", cost=0.01)
    up_b, base_b = _boot(status=200, return_model="mb", cost=0.02)
    bt = BalanceTracker()
    bt.park("pa")
    bt.park("pb")
    gw = _gateway({"v": [UpstreamRoute(base_a, "ka", provider="pa", upstream_model="ma"),
                         UpstreamRoute(base_b, "kb", provider="pb", upstream_model="mb")]},
                  balance_tracker=bt)
    try:
        status, body, hdrs = _post(gw.url + "/v1/chat/completions",
                                   {"model": "v", "messages": []})
        assert status == 200, (
            f"BEHAVIOUR: every leg parked → the request was stranded with "
            f"{status}, instead of falling back to the full chain: {body!r}")
        _assert_real_completion(body, hdrs, served_by="pa")
        assert up_a.received == ["ma"], (
            "BEHAVIOUR: no HTTP request reached the first leg — the fallback did "
            f"not restore the chain (upstream saw {up_a.received!r})")
        assert hdrs.get("X-Charon-Failovers") == "0", (
            "BEHAVIOUR: the restored chain should serve on its first leg; "
            f"headers report {hdrs.get('X-Charon-Failovers')!r} failovers")
        assert bt.is_parked("pa") and bt.is_parked("pb"), (
            "BEHAVIOUR: the never-strand fallback silently UN-PARKED providers; "
            "it must bypass the park exclusion for this request only")
    finally:
        gw.shutdown()
        up_a.shutdown()
        up_b.shutdown()


def test_parked_leg_is_never_dispatched_while_a_live_leg_exists() -> None:
    """A parked leg receives NO HTTP request when a live sibling exists.

    The observable effect is on the upstream's own socket: a parked provider that
    is still dispatched would appear in ``up_parked.received``. Pre-flight
    exclusion is also not a failover, so the visibility header must say 0.
    """
    up_parked, base_parked = _boot(status=429)
    up_live, base_live = _boot(status=200, return_model="mb", cost=0.02)
    bt = BalanceTracker()
    bt.park("parked-leg")
    gw = _gateway({"v": [UpstreamRoute(base_parked, "ka", provider="parked-leg"),
                         UpstreamRoute(base_live, "kb", provider="live-leg",
                                       upstream_model="mb")]},
                  balance_tracker=bt)
    try:
        status, body, hdrs = _post(gw.url + "/v1/chat/completions",
                                   {"model": "v", "messages": []})
        assert status == 200, f"BEHAVIOUR: live leg did not serve ({status}): {body!r}"
        _assert_real_completion(body, hdrs, served_by="live-leg")
        assert up_parked.received == [], (
            "BEHAVIOUR: a PARKED provider was really dispatched — its upstream "
            f"received {up_parked.received!r}. Parked traffic costs money and "
            "burns a dead key.")
        assert hdrs.get("X-Charon-Failovers") == "0", (
            "BEHAVIOUR: excluding a parked leg pre-flight is not a failover; "
            f"header reports {hdrs.get('X-Charon-Failovers')!r}")
    finally:
        gw.shutdown()
        up_parked.shutdown()
        up_live.shutdown()


@pytest.mark.parametrize("leg_status", [429, 402])
def test_total_exhaustion_is_an_honest_503_naming_every_leg(leg_status: int) -> None:
    """Every leg exhausted → a REAL 503 that names each leg tried, never a 200.

    Chain exhaustion is a correct terminal state (blueprint §2.3), but it must be
    reported honestly: the caller must be able to see WHICH providers were tried
    and WHY each failed, from the response alone, and must never receive a
    success-shaped body.
    """
    up_a, base_a = _boot(status=leg_status)
    up_b, base_b = _boot(status=leg_status)
    gw = _gateway({"v": [UpstreamRoute(base_a, "ka", provider="leg-a"),
                         UpstreamRoute(base_b, "kb", provider="leg-b")]})
    try:
        status, body, hdrs = _post(gw.url + "/v1/chat/completions",
                                   {"model": "v", "messages": []})
        assert status == 503, (
            f"BEHAVIOUR: whole-pool exhaustion returned {status}, not a "
            f"synthesized 503 terminal: {body!r}")
        assert "choices" not in body, (
            f"BEHAVIOUR: exhaustion answered with a success-shaped body: {body!r}")
        err = body.get("error", {})
        assert err.get("type") == "all_providers_exhausted", (
            f"BEHAVIOUR: exhaustion is not self-describing: {body!r}")
        assert err.get("requested_model") == "v", f"BEHAVIOUR: model not echoed: {body!r}"
        tried = err.get("providers_tried") or []
        assert [t.get("provider") for t in tried] == ["leg-a", "leg-b"], (
            "BEHAVIOUR: the terminal envelope does not name every leg tried "
            f"(got {tried!r}) — indistinguishable from a crash")
        assert all(t.get("reason") for t in tried), (
            f"BEHAVIOUR: a leg was named with no reason: {tried!r}")
        assert [t.get("status") for t in tried] == [leg_status, leg_status], (
            f"BEHAVIOUR: per-leg status not recorded truthfully: {tried!r}")
        assert hdrs.get("X-Charon-Failovers") == "2", (
            f"BEHAVIOUR: header hides attempts: {hdrs.get('X-Charon-Failovers')!r}")
        assert up_a.received and up_b.received, (
            "BEHAVIOUR: a leg was reported as tried but its upstream received "
            f"nothing (a={up_a.received!r} b={up_b.received!r})")
    finally:
        gw.shutdown()
        up_a.shutdown()
        up_b.shutdown()
