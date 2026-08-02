"""Park-and-re-arm contract for a funded provider (PARK-REARM-FUNDED-PROVIDER).

Four DONE-CONTRACT areas, all hermetic (stubbed upstream, no live gateway):

  (a) BLAST RADIUS — a 402 on ONE leg does NOT park sibling legs of the same
      provider. Exhaustion is keyed per ``(requested_model, provider)`` LEG, so
      a single leg's cap stays that leg; sibling legs of the same provider and
      sibling providers serving the same model id remain eligible.
  (b) RE-ARM — a leg that was exhausted and answers 200 again is RE-ADMITTED
      within one observation window (``record()`` drops the leg's exclusion on a
      clean 200). A parked provider re-arms via ``unpark`` and serves again.
  (c) ANTI-OVER-BLOCK — a genuine provider-wide exhaustion (account balance zero
      / all legs 402) DOES still exhaust/park the provider. The fix narrows the
      blast radius; it does not remove the protection.
  (d) CLASSIFICATION — 403 key-limit is classified distinctly from 402 balance-
      exhausted; neither is silently folded into the other, and both are visible
      in the exhaustion ledger (the observation ``note``) with the right label.

FAIL-ON-REVERT notes on each test say exactly which proxy.py change reverting
turns it RED.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon.balance import BalanceTracker
from charon.proxy import GatewayProxy
from charon.proxy_server import GatewayProxyServer, UpstreamRoute

# ---------------------------------------------------------------------------
# Mock upstream — replays a scripted (status, kind) sequence, one per call.
# ---------------------------------------------------------------------------


class _Prog(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a: object) -> None:
        pass

    def do_POST(self) -> None:
        srv = self.server  # type: ignore[attr-defined]
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
            msg_map = {
                "det": "Insufficient USD balance. Available 0.050538 USD, "
                       "required 0.153460 USD.",
                "trans": "Insufficient balance after pending billing reservations.",
                "key_limit": "Key limit exceeded for this API key.",
                "auth": "invalid_api_key",
            }
            payload = json.dumps({"error": {"message": msg_map.get(kind, "error")}}).encode()
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


def _ok_body(model: str) -> dict:
    return {
        "model": model,
        "choices": [{"message": {"content": "ok"}}],
        "usage": {"prompt_tokens": 1, "completion_tokens": 1, "cost": 0.001},
    }


# ---------------------------------------------------------------------------
# (a) BLAST RADIUS: exhaustion is per-(model, provider) LEG, not per-provider.
# ---------------------------------------------------------------------------


def test_one_leg_402_does_not_park_sibling_leg_of_same_provider():
    """A 402 on openrouter's gpt-5.4-mini leg does NOT exhaust openrouter's
    glm-5.2 sibling leg (same provider, different model) — the incident shape.

    FAIL-ON-REVERT: if the exhausted set were keyed per-PROVIDER (or the park
    were model-wide), ``glm-5.2`` would be excluded after gpt-5.4-mini 402s."""
    proxy = GatewayProxy()

    proxy.observe(
        "gpt-5.4-mini", 402, {},
        {"error": {"message": "Insufficient USD balance. Available "
                              "0.050538 USD, required 0.153460 USD."}},
        count_usage=False, provider="openrouter")

    assert proxy.is_exhausted_leg("gpt-5.4-mini", "openrouter")
    assert not proxy.is_exhausted_leg("glm-5.2", "openrouter"), (
        "glm-5.2 (openrouter) is a SIBLING leg of gpt-5.4-mini — a 402 on one "
        "leg must not park it")
    assert not proxy.is_exhausted("glm-5.2")
    assert proxy.exhausted_legs() == {("gpt-5.4-mini", "openrouter")}


def test_one_leg_402_narrows_to_provider_leg_not_shared_model():
    """A 402 on openrouter's leg of a model SHARED by several providers marks
    only openrouter's leg excluded — sibling providers of the same model stay
    eligible.

    FAIL-ON-REVERT: with model-wide keying, the 402 on openrouter would exclude
    every provider's leg of the model (``is_exhausted_leg("gpt-5.4-mini",
    "decart")`` would read the same single entry)."""
    proxy = GatewayProxy()
    proxy.observe("gpt-5.4-mini", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")

    assert proxy.is_exhausted_leg("gpt-5.4-mini", "openrouter")
    assert not proxy.is_exhausted_leg("gpt-5.4-mini", "decart"), (
        "decart's leg of the same model id must NOT be excluded by openrouter's "
        "per-key cap (blast radius)")
    # model-wide view stays backward-compatible for the orchestrator:
    assert proxy.is_exhausted("gpt-5.4-mini")
    assert proxy.exhausted_models() == {"gpt-5.4-mini"}


def test_200_on_one_provider_does_not_rearm_sibling_provider_leg():
    """A clean 200 from decart's leg of a shared model must NOT re-admit
    openrouter's still-failing leg.

    FAIL-ON-REVERT: with model-wide keying, the 200 on ``gpt-5.4-mini`` would
    clear the single exhaustion entry and openrouter's leg would be re-admitted
    even though it never answered."""
    proxy = GatewayProxy()
    proxy.observe("gpt-5.4-mini", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    assert proxy.is_exhausted_leg("gpt-5.4-mini", "openrouter")

    proxy.observe("gpt-5.4-mini", 200, {}, _ok_body("gpt-5.4-mini"),
                  count_usage=True, provider="decart")

    assert proxy.is_exhausted_leg("gpt-5.4-mini", "openrouter"), (
        "decart's 200 must NOT re-admit openrouter's exhausted leg — re-arm is "
        "per-leg")
    assert not proxy.is_exhausted_leg("gpt-5.4-mini", "decart")


def test_single_model_402_is_not_provider_level_exhaustion():
    """One model's deterministic 402 is a per-key cap — NOT provider-level
    account-depletion evidence, so the auto-park gate must NOT park the whole
    provider on it.

    FAIL-ON-REVERT: dropping the per-provider tracking makes
    ``has_multiple_exhausted_models`` indistinguishable from a single 402 (the
    forwarder's park gate would park on one leg's cap)."""
    proxy = GatewayProxy()
    proxy.observe("gpt-5.4-mini", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    assert proxy.is_exhausted_leg("gpt-5.4-mini", "openrouter")
    assert not proxy.has_multiple_exhausted_models("openrouter"), (
        "a single model's 402 must NOT read as provider-level account depletion")


def test_two_models_402_is_provider_level_exhaustion():
    """Two distinct models of the same provider BOTH deterministically 402 →
    provider-level account-depletion signal (the anti-over-block park input)."""
    proxy = GatewayProxy()
    proxy.observe("gpt-5.4-mini", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    proxy.observe("glm-5.2", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    assert proxy.has_multiple_exhausted_models("openrouter"), (
        "two distinct models 402ing is account-level evidence (anti-over-block)")


def test_transient_and_throttle_do_not_count_toward_provider_park():
    """Only DETERMINISTIC balance exhaustion counts as account-depletion
    evidence — a transient 402 (self-healing) or a 429 throttle is per-key /
    per-moment and must NOT push the provider-level park signal."""
    proxy = GatewayProxy()
    proxy.observe(
        "model-a", 402, {},
        {"error": {"message": "Insufficient balance after pending billing "
                              "reservations."}},
        count_usage=False, provider="openrouter")   # transient — self-heals
    proxy.observe("model-b", 429, {}, {"error": {"message": "rate limit"}},
                  count_usage=False, provider="openrouter")   # throttle
    assert not proxy.has_multiple_exhausted_models("openrouter"), (
        "transient 402 + throttle must not read as account depletion")


def test_provider_signal_withdraws_on_rearm():
    """A clean 200 on one model withdraws it from the provider's account-
    depletion evidence — the signal tracks live state, not history."""
    proxy = GatewayProxy()
    proxy.observe("gpt-5.4-mini", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    proxy.observe("glm-5.2", 402, {},
                  {"error": {"message": "Insufficient USD balance."}},
                  count_usage=False, provider="openrouter")
    assert proxy.has_multiple_exhausted_models("openrouter")

    proxy.observe("glm-5.2", 200, {}, _ok_body("glm-5.2"),
                  count_usage=True, provider="openrouter")
    assert not proxy.has_multiple_exhausted_models("openrouter"), (
        "glm-5.2 recovered — only gpt-5.4-mini remains balance-exhausted")


# ---------------------------------------------------------------------------
# (b) RE-ARM: a parked/exhausted leg that answers 200 is re-admitted.
# ---------------------------------------------------------------------------


def test_exhausted_leg_cleared_on_200():
    """A leg recorded as exhausted via observe() is RE-ADMITTED when it
    subsequently answers a clean 200.

    FAIL-ON-REVERT: without the re-arm branch in record(), the 200 leaves the
    exhaustion entry in place and the leg stays parked for the process
    lifetime."""
    proxy = GatewayProxy()

    proxy.observe("model-x", 402, {},
                  {"error": {"message": "balance exhausted"}},
                  count_usage=False, provider="openrouter")
    assert proxy.is_exhausted("model-x")

    proxy.observe("model-x", 200, {}, _ok_body("model-x"),
                  count_usage=True, provider="openrouter")
    assert not proxy.is_exhausted("model-x"), (
        "a clean 200 observation must remove the leg from the exhausted set "
        "(re-arm within one observation window)")


def test_rearm_is_per_leg():
    """A 200 on ONE leg re-admits only that leg; a sibling leg's independent
    exhaustion stays.

    FAIL-ON-REVERT: re-arming by model id alone would clear model-b when
    model-a recovers."""
    proxy = GatewayProxy()
    proxy.observe("model-a", 402, {}, {"error": {"message": "balance"}},
                  count_usage=False, provider="openrouter")
    proxy.observe("model-b", 402, {}, {"error": {"message": "balance"}},
                  count_usage=False, provider="openrouter")
    assert proxy.exhausted_legs() == {
        ("model-a", "openrouter"), ("model-b", "openrouter")}

    proxy.observe("model-a", 200, {}, _ok_body("model-a"),
                  count_usage=True, provider="openrouter")

    assert not proxy.is_exhausted_leg("model-a", "openrouter")
    assert proxy.is_exhausted_leg("model-b", "openrouter"), (
        "model-b's independent exhaustion must survive model-a's recovery")


def test_pseudo_success_200_does_not_rearm():
    """A silent-downgrade 200 is a FAILOVER observation (it served a different
    model) — it must NOT re-admit the leg.

    FAIL-ON-REVERT: re-arming on any 200 would clear an exhaustion entry the
    very downgrade that caused it, un-parking a habitual downgrader."""
    proxy = GatewayProxy()
    proxy.observe("asked-model", 402, {}, {"error": {"message": "balance"}},
                  count_usage=False, provider="openrouter")
    assert proxy.is_exhausted("asked-model")

    obs = proxy.classify("asked-model", 200,
                         body={"model": "free-model",
                               "choices": [{"message": {"content": "x"}}]},
                         expected_model="asked-model")
    assert obs.pseudo_success and obs.failover
    proxy.record(obs, count_usage=False, provider="openrouter")

    assert proxy.is_exhausted("asked-model"), (
        "a downgrade is not a clean recovery — the leg stays parked")


def test_reexhausted_after_rearm_cycle_is_bounded():
    """Re-arm then a fresh 402 re-parks — the park/re-arm cycle repeats, and
    each re-arm is bounded by the next clean 200."""
    proxy = GatewayProxy()
    for _ in range(3):
        proxy.observe("model-x", 402, {}, {"error": {"message": "balance"}},
                      count_usage=False, provider="openrouter")
        assert proxy.is_exhausted("model-x")
        proxy.observe("model-x", 200, {}, _ok_body("model-x"),
                      count_usage=True, provider="openrouter")
        assert not proxy.is_exhausted("model-x")


# ---------------------------------------------------------------------------
# (c) ANTI-OVER-BLOCK: all legs 402 still exhausts every leg of the provider.
# ---------------------------------------------------------------------------


def test_both_legs_exhausted_when_all_402():
    """When every leg of a provider returns 402, EVERY leg is excluded — the
    narrow view still blocks the provider completely.

    FAIL-ON-REVERT: if the blast-radius narrowing removed the per-leg exclusion
    for the ALL-402 case, a genuinely drained provider would keep its legs
    eligible and burn failover slots forever."""
    proxy = GatewayProxy()
    proxy.observe("model-a", 402, {}, {"error": {"message": "balance"}},
                  count_usage=False, provider="openrouter")
    proxy.observe("model-b", 402, {}, {"error": {"message": "balance"}},
                  count_usage=False, provider="openrouter")

    exhausted = proxy.exhausted_legs()
    assert ("model-a", "openrouter") in exhausted
    assert ("model-b", "openrouter") in exhausted
    assert proxy.is_exhausted("model-a") and proxy.is_exhausted("model-b")


# ---------------------------------------------------------------------------
# (d) CLASSIFICATION: 403 key-limit vs 402 balance — distinct labels, both in
#     the exhaustion ledger.
# ---------------------------------------------------------------------------


def test_403_key_limit_distinct_from_402_balance():
    """402 → exhaustion_type "balance"; 403 → "key_limit"; 429 → "throttle";
    503 → "unavailable". Neither 402 nor 403 is folded into the other.

    FAIL-ON-REVERT: reverting the 403 classifier makes ``obs_403.exhausted``
    False (403 was previously not an exhaustion at all); reverting the
    ``_exhaustion_type`` ordering mislabels 503 as "throttle"."""
    proxy = GatewayProxy()

    obs_402 = proxy.classify(
        "m", 402, {},
        {"error": {"message": "Insufficient USD balance. Available 0.050538 USD."}})
    assert obs_402.exhausted and obs_402.failover
    assert obs_402.exhaustion_type == "balance"

    obs_transient = proxy.classify(
        "m", 402, {},
        {"error": {"message": "Insufficient balance after pending billing reservations."}})
    assert obs_transient.exhausted
    assert obs_transient.transient
    assert obs_transient.exhaustion_type == "balance", (
        "a transient 402 is still a balance issue — never labelled 'throttle'")

    obs_403 = proxy.classify(
        "m", 403, {},
        {"error": {"message": "Key limit exceeded for this API key."}})
    assert obs_403.exhausted
    assert obs_403.exhaustion_type == "key_limit", (
        f"403 key-limit should be exhaustion_type='key_limit', "
        f"got {obs_403.exhaustion_type!r}")

    obs_403_bare = proxy.classify("m", 403, {}, {})
    assert obs_403_bare.exhausted
    assert obs_403_bare.exhaustion_type == "key_limit"

    obs_429 = proxy.classify("m", 429, {}, {"error": {"message": "rate limit"}})
    assert obs_429.exhausted
    assert obs_429.exhaustion_type == "throttle"

    obs_503 = proxy.classify("m", 503, {}, {"error": {"message": "overloaded"}})
    assert obs_503.exhausted
    assert obs_503.exhaustion_type == "unavailable", (
        f"503 should be 'unavailable', got {obs_503.exhaustion_type!r}")


def test_403_billing_body_is_balance():
    """A 403 whose body says balance is a billing exhaustion (labelled
    "balance"), NOT folded into the key_limit label.

    FAIL-ON-REVERT: an unconditional ``403 → key_limit`` would mislabel a
    billing 403."""
    proxy = GatewayProxy()
    obs = proxy.classify("m", 403, {},
                         {"error": {"message": "Insufficient balance"}})
    assert obs.exhausted
    assert obs.exhaustion_type == "balance"


def test_exhaustion_type_visible_in_ledger_note():
    """The exhaustion label appears in the observation note — the field the
    failover ledger/failover-reasons surface to operators — so 403 key-limit and
    402 balance are OBSERVABLY distinct, not silently folded."""
    proxy = GatewayProxy()

    obs_402 = proxy.classify("m", 402, {}, {"error": {"message": "balance"}})
    assert "exhausted" in obs_402.note and "balance" in obs_402.note

    obs_403 = proxy.classify("m", 403, {},
                             {"error": {"message": "Key limit exceeded."}})
    assert "key_limit" in obs_403.note, f"403 note must carry 'key_limit': {obs_403.note!r}"

    obs_429 = proxy.classify("m", 429, {}, {"error": {"message": "rate limit"}})
    assert "throttle" in obs_429.note

    obs_503 = proxy.classify("m", 503, {}, {"error": {"message": "overloaded"}})
    assert "unavailable" in obs_503.note


# ---------------------------------------------------------------------------
# Integration (full gateway stack, stubbed upstream): the DONE-CONTRACT shapes
# through forwarder + BalanceTracker + proxy.
# ---------------------------------------------------------------------------


def test_sibling_leg_still_served_when_other_leg_exhausted():
    """The live-defect shape end-to-end: gpt-5.4-mini (openrouter) 402s; its
    sibling leg glm-5.2 (openrouter) must STILL serve, and the whole provider
    must NOT be parked by one leg's cap."""
    a, base_a = _up([(402, "det")])
    b, base_b = _up([(200, None)], return_model="glm-5.2")
    bt = BalanceTracker()
    pools = {
        "pool-v": [
            UpstreamRoute(base_a, "ka", provider="openrouter",
                          upstream_model="gpt-5.4-mini"),
            UpstreamRoute(base_b, "kb", provider="openrouter",
                          upstream_model="glm-5.2"),
        ],
    }
    gw = GatewayProxyServer(pools=pools, balance_tracker=bt)
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "pool-v"})
        assert status == 200, f"expected 200, got {status}"
        assert body["model"] == "glm-5.2", (
            f"model-b should serve while model-a is exhausted, got {body.get('model')!r}")
        assert not bt.is_parked("openrouter"), (
            "a single leg's deterministic 402 must NOT park the whole provider "
            "(blast radius) — glm-5.2 (openrouter) still serves")

        status2, body2, hdrs2 = _req(gw.url + "/v1/chat/completions", {"model": "pool-v"})
        assert status2 == 200 and body2["model"] == "glm-5.2"
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_all_legs_deterministic_402_parks_provider():
    """ANTI-OVER-BLOCK: when every leg of a provider returns deterministic 402,
    the provider IS parked (drops out of rotation) — the fix narrows the blast
    radius, it does not remove the protection."""
    a, base_a = _up([(402, "det")])
    b, base_b = _up([(200, None)], return_model="b-model")
    bt = BalanceTracker()
    pools = {
        "pool-v": [
            UpstreamRoute(base_a, "ka", provider="prov-drained",
                          upstream_model="model-a"),
            UpstreamRoute(base_b, "kb", provider="prov-healthy",
                          upstream_model="b-model"),
        ],
    }
    gw = GatewayProxyServer(pools=pools, balance_tracker=bt)
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "pool-v"})
        assert status == 200, f"expected 200 from healthy sibling, got {status}"
        assert body["model"] == "b-model"
        assert bt.is_parked("prov-drained"), (
            "deterministic 402 on one leg must park that provider "
            "(anti-over-block: the fix narrows the blast radius, not the "
            "protection)")
        status2, body2, hdrs2 = _req(gw.url + "/v1/chat/completions", {"model": "pool-v"})
        assert status2 == 200
        assert a.calls == 1, "parked provider was still dispatched on request 2"
    finally:
        gw.shutdown()
        a.shutdown()
        b.shutdown()


def test_leg_recovered_unparked_provider_serves_traffic():
    """RE-ARM end-to-end: a parked provider re-arms via ``bt.unpark`` (the
    funding-class re-arm table) and its legs serve traffic again."""
    leg_a, base_a = _up([(200, None)], return_model="leg-a-model")
    leg_b, base_b = _up([(200, None)], return_model="leg-b-model")
    bt = BalanceTracker()
    pools = {
        "pool-multi": [
            UpstreamRoute(base_a, "ka", provider="prov-x",
                          upstream_model="leg-a-model"),
            UpstreamRoute(base_b, "kb", provider="prov-x",
                          upstream_model="leg-b-model"),
        ],
    }
    gw = GatewayProxyServer(pools=pools, balance_tracker=bt)
    gw.serve_in_thread()
    try:
        status, body, hdrs = _req(gw.url + "/v1/chat/completions", {"model": "pool-multi"})
        assert status == 200, f"first request should succeed, got {status}"

        bt.park("prov-x")
        assert bt.is_parked("prov-x")

        status2, body2, hdrs2 = _req(gw.url + "/v1/chat/completions", {"model": "pool-multi"})
        assert status2 == 200, (
            f"parked provider with live legs should still answer via the "
            f"never-strand fallback, got {status2}")

        bt.unpark("prov-x")
        assert not bt.is_parked("prov-x")

        status3, body3, hdrs3 = _req(gw.url + "/v1/chat/completions", {"model": "pool-multi"})
        assert status3 == 200, f"re-armed provider should serve, got {status3}"
        assert leg_a.calls + leg_b.calls >= 2, (
            "re-armed provider should have served at least 2 requests total")
    finally:
        gw.shutdown()
        leg_a.shutdown()
        leg_b.shutdown()
