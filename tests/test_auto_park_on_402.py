"""AUTO-PARK-ON-402 — closes the gap PR #121 left open (fleet ticket: a live
402 never fed BalanceTracker, so a purely-402ing provider never tripped
``is_drained``/``park`` and kept getting retried forever).

Three pieces, each FAIL-ON-REVERT:

1. A DETERMINISTIC drained-key 402 (status==402, ``obs.transient`` False — the
   openrouter "can only afford ... tokens" class) auto-parks the provider via
   ``forwarder.py``'s non-200 branch, dropping it from the pre-flight cheapest-
   first rotation on the NEXT request — no operator action.
2. A TRANSIENT 402/503 (PR #121's retry-once class) and a 429 throttle must
   NEVER be parked — both self-heal with time/retry, and a 429 in particular
   also sets ``obs.exhausted`` True with ``obs.transient`` False (same as a
   deterministic 402), so the park condition is deliberately scoped to
   ``status == 402`` on top of ``not obs.transient`` — this is the subtlety
   that makes ``obs.exhausted and not obs.transient`` alone WRONG (it would
   also catch a 429).
3. Park state persists to disk (survives a simulated restart) and a
   poll-mode provider (openrouter/nanogpt/deepseek) auto-re-arms the moment
   its balance poll recovers — no operator action either way.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request
from pathlib import Path
from unittest.mock import MagicMock, patch

from charon.balance import BalanceTracker
from charon.proxy_server import GatewayProxyServer, UpstreamRoute

_DETERMINISTIC_MSG = (
    "This request requires more credits, or fewer max_tokens. You requested "
    "up to 65536 tokens, but can only afford 345 tokens."
)
_TRANSIENT_MSG = "Insufficient balance after pending billing reservations."


# ---------------------------------------------------------------------------
# Mock upstream — replays a scripted (status, kind) sequence, one per call.
# ---------------------------------------------------------------------------


class _Prog(http.server.BaseHTTPRequestHandler):
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


def _gw_with_balance(pools, bt):
    gw = GatewayProxyServer(pools=pools, balance_tracker=bt)
    gw.serve_in_thread()
    return gw


# ---------------------------------------------------------------------------
# 1. Deterministic 402 auto-parks and drops out of rotation.
# ---------------------------------------------------------------------------


def test_deterministic_402_auto_parks_and_rolls_to_next_provider():
    """A deterministic drained-key 402 fails over to the next provider AND
    parks the drained one — the NEXT request skips it entirely (dropped from
    rotation), not just cooled down for a fixed window.

    FAIL-ON-REVERT: without the ``bt.record_exhaustion`` call at forwarder.py's
    non-200 branch, ``bt.is_parked("drained")`` stays False and provider `a`
    would be re-tried by the pre-flight loop on request 2."""
    a, base_a = _up([(402, "deterministic"), (200, None)])  # 2nd entry unused if parked
    b, base_b = _up([(200, None)], return_model="mb")
    bt = BalanceTracker()  # no funding_class config — plain API-key providers
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="drained", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="healthy", upstream_model="mb")]}
    gw = _gw_with_balance(pools, bt)
    try:
        assert not bt.is_parked("drained")
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["model"] == "mb"
        assert hdrs["X-Charon-Failovers"] == "1"
        assert a.calls == 1  # not retried — deterministic
        assert bt.is_parked("drained"), (
            "deterministic 402 must auto-park the provider (record_exhaustion "
            "call missing or reverted)")

        # Request 2: the pre-flight exclusion loop must skip the parked
        # provider entirely — `a` is never called again.
        status2, body2, hdrs2 = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status2 == 200 and body2["model"] == "mb"
        assert a.calls == 1, (
            "parked provider was still dispatched — pre-flight exclusion did "
            "not honor is_parked() for a non-funding_class provider")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_deterministically_exhausted_providers_surface_loud_terminal_503():
    """Invariant #4: when EVERY provider in a pool deterministically 402s in
    the SAME request, the client still sees the loud synthesized "all
    providers exhausted" 503 — never a silent hang/500.

    The FIRST provider tried (prov-a) has a live sibling (prov-b, not yet
    failed) at the moment it is evaluated, so it IS auto-parked. The LAST
    provider (prov-b) is evaluated only after prov-a is already parked, so
    the sole-leg guard (``_has_live_sibling``) correctly refuses to park it
    too — parking the last live leg would strand the pool with zero routes
    for the NEXT request. Either way this request's client-visible outcome is
    unaffected: both attempts fail NOW, so the terminal 503 fires regardless
    of the parked bookkeeping."""
    a, base_a = _up([(402, "deterministic")])
    b, base_b = _up([(402, "deterministic")])
    bt = BalanceTracker()
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="prov-a"),
                   UpstreamRoute(base_b, "kb", provider="prov-b")]}
    gw = _gw_with_balance(pools, bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 503
        assert body["error"]["type"] == "all_providers_exhausted"
        assert hdrs["X-Charon-Failovers"] == "2"
        assert bt.is_parked("prov-a")
        assert not bt.is_parked("prov-b"), (
            "SOLE-LEG GUARD FAILED: the last live leg of the pool was parked, "
            "which would strand ALL traffic for this model on the next "
            "request with no fallback")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


# ---------------------------------------------------------------------------
# 2. Transient 402/503 and 429 throttle must NOT be parked.
# ---------------------------------------------------------------------------


def test_transient_402_recovers_and_is_not_parked():
    """nanogpt-style transient 402, recovers on same-provider retry (PR #121)
    — never parked."""
    up, base = _up([(402, "transient"), (200, None)])
    bt = BalanceTracker()
    pools = {"v": [UpstreamRoute(base, "k", provider="flaky")]}
    gw = _gw_with_balance(pools, bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and hdrs["X-Charon-Failovers"] == "0"
        assert not bt.is_parked("flaky")
    finally:
        gw.shutdown()
        up.shutdown()


def test_transient_402_that_never_recovers_still_not_parked():
    """Transient 402 retried once, still fails, falls over to the next
    provider — the transient one is STILL not parked (it self-heals with
    time; a momentary race is not a drained key)."""
    a, base_a = _up([(402, "transient"), (402, "transient")])
    b, base_b = _up([(200, None)], return_model="mb")
    bt = BalanceTracker()
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="flaky", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="healthy", upstream_model="mb")]}
    gw = _gw_with_balance(pools, bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["model"] == "mb"
        assert a.calls == 2  # exactly one retry
        assert not bt.is_parked("flaky")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_transient_503_not_parked():
    up, base = _up([(503, None), (200, None)])
    bt = BalanceTracker()
    pools = {"v": [UpstreamRoute(base, "k", provider="flaky")]}
    gw = _gw_with_balance(pools, bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200
        assert not bt.is_parked("flaky")
    finally:
        gw.shutdown()
        up.shutdown()


def test_429_throttle_not_parked():
    """A 429 sets ``obs.exhausted`` True and ``obs.transient`` False — the SAME
    ``transient`` shape as a deterministic 402 — so the park condition must
    check ``status == 402`` explicitly, not just ``exhausted and not
    transient``, or this throttle would get wrongly parked.

    FAIL-ON-REVERT: a park condition of ``obs.exhausted and not obs.transient``
    (dropping the ``status == 402`` check) makes this RED."""
    a, base_a = _up([(429, None)])
    b, base_b = _up([(200, None)], return_model="mb")
    bt = BalanceTracker()
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="throttled", upstream_model="ma"),
                   UpstreamRoute(base_b, "kb", provider="healthy", upstream_model="mb")]}
    gw = _gw_with_balance(pools, bt)
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status == 200 and body["model"] == "mb"
        assert not bt.is_parked("throttled"), (
            "a 429 throttle must NEVER be auto-parked (only a deterministic "
            "402 drained-key does) — status==402 guard missing or reverted")
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_sole_leg_guard_prevents_parking_last_live_provider():
    """A deterministic 402 on a provider whose only pool-sibling is ALREADY
    parked must NOT be auto-parked — parking it would orphan the pool with
    zero live legs, violating the never-strand invariant."""
    a, base_a = _up([(402, "deterministic")])
    bt = BalanceTracker()
    bt.park("sibling")  # pre-parked (e.g. balance-drained, or a prior 402)
    pools = {"v": [UpstreamRoute(base_a, "ka", provider="last-one"),
                   UpstreamRoute("http://127.0.0.1:1", "kb", provider="sibling")]}
    gw = _gw_with_balance(pools, bt)
    try:
        # Pre-flight excludes "sibling" (parked) → only "last-one" is dispatched.
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "v"})
        assert status in (402, 503)  # relayed/terminal — no live alternative
        assert not bt.is_parked("last-one"), (
            "SOLE-LEG GUARD FAILED: the only live provider in the pool was "
            "auto-parked, orphaning it with zero live legs")
    finally:
        gw.shutdown()
        a.shutdown()


# ---------------------------------------------------------------------------
# 3. Persistence across a simulated restart + poll-mode auto-re-arm.
# ---------------------------------------------------------------------------


def test_parked_state_persists_across_simulated_restart(tmp_path: Path) -> None:
    """Parking writes to disk; a FRESH BalanceTracker instance pointed at the
    same state_dir (simulating a gateway container restart) reloads the
    parked set — the fact that a key was drained is never lost.

    FAIL-ON-REVERT: an in-memory-only ``_parked`` set (no ``_save_parked``/
    ``_load_parked``) makes the second tracker's ``is_parked`` False."""
    cfg = {"drained-key": {"mode": "fixed", "starting_usd": 10.0}}
    bt1 = BalanceTracker(config=cfg, state_dir=tmp_path)
    bt1.record_exhaustion("drained-key")
    assert bt1.is_parked("drained-key")
    assert (tmp_path / "balance_park.json").exists()

    # Simulate a restart: brand-new process, brand-new tracker, same state_dir.
    bt2 = BalanceTracker(config=cfg, state_dir=tmp_path)
    assert bt2.is_parked("drained-key"), (
        "parked state did not survive a simulated restart — not persisted to "
        "disk, or not reloaded on construction")


def test_no_state_dir_stays_in_memory_only(tmp_path: Path) -> None:
    """Backward-compat: a BalanceTracker constructed WITHOUT state_dir (the
    existing unit-test / direct-construction pattern) never touches disk."""
    bt = BalanceTracker(config={"p": {"mode": "fixed", "starting_usd": 1.0}})
    bt.park("p")
    assert bt.is_parked("p")
    assert not (tmp_path / "balance_park.json").exists()


def test_auto_unpark_on_poll_recovery():
    """A parked poll-mode provider (openrouter) whose balance poll shows
    recovered funds re-arms itself — no operator action.

    FAIL-ON-REVERT: without the auto-unpark hook in ``remaining()``'s poll
    branch, ``is_parked`` stays True after a fresh poll reports a positive
    balance."""
    bt = BalanceTracker(config={
        "openrouter": {"mode": "poll", "base_url": "https://openrouter.ai/api/v1",
                       "api_key": "sk-test"},
    })
    bt.park("openrouter")
    assert bt.is_parked("openrouter")

    body = json.dumps({"data": {"credits": 12.34}}).encode()
    mock = MagicMock()
    mock.read.return_value = body
    with patch("urllib.request.build_opener") as bo:
        bo.return_value.open.return_value = mock
        remaining = bt.remaining("openrouter")

    assert remaining == 12.34
    assert not bt.is_parked("openrouter"), (
        "poll-mode provider with a recovered positive balance must auto-"
        "re-arm (unpark) with zero operator action")
    assert bt.counters().get("auto_unpark", 0) == 1


def test_poll_provider_stays_parked_when_balance_still_zero():
    """A parked poll-mode provider whose poll STILL reports ~0 stays parked —
    auto-unpark only fires on an actually-recovered balance."""
    bt = BalanceTracker(config={
        "openrouter": {"mode": "poll", "base_url": "https://openrouter.ai/api/v1",
                       "api_key": "sk-test"},
    })
    bt.park("openrouter")

    body = json.dumps({"data": {"credits": 0.0}}).encode()
    mock = MagicMock()
    mock.read.return_value = body
    with patch("urllib.request.build_opener") as bo:
        bo.return_value.open.return_value = mock
        remaining = bt.remaining("openrouter")

    assert remaining == 0.0
    assert bt.is_parked("openrouter")


def test_record_exhaustion_counter_distinguishes_auto_from_manual_park():
    """``record_exhaustion`` (request-path auto-park) bumps a distinct
    ``auto_park`` counter from a plain operator ``park()`` call, so an
    operator can tell a self-park apart from a manual one."""
    bt = BalanceTracker()
    bt.park("manual")
    assert bt.counters().get("auto_park", 0) == 0
    bt.record_exhaustion("auto")
    assert bt.counters().get("auto_park", 0) == 1
    assert bt.is_parked("auto")
