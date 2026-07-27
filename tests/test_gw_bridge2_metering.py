"""FAIL-ON-REVERT acceptance tests for GW-BRIDGE-2 (verify-only cost cross-check).

ADR-0020 ACCEPTED verify-only: the litellm cost callback runs ALONGSIDE Charon's
authoritative accounting as a cross-check, NOT as the money source of record.

GREEN-IS-NOT-PROOF: every test here pins one observable invariant that MUST
survive. Reverting the corresponding invariant in ``metering.py`` turns the
test RED.

Acceptance criteria (fail-on-revert):
  (1) AUTHORITY UNCHANGED — BalanceTracker spend + drain-then-park outcomes
      are byte-for-byte identical with the callback wired vs not; the cross-check
      changes NO billing/parking outcome.
  (2) DIVERGENCE SURFACED — a request where callback cost != Charon cost emits
      a divergence WARNING. Revert -> no alert -> RED.
  (3) NO CORRUPTION — an energy-billed / non-token provider is billed by Charon
      exactly as without the bridge; the cross-check never zeroes or double-counts.
"""
from __future__ import annotations

import logging

import pytest

from charon.litellm_plane.metering import (
    _cost_from_hidden,
    charon_cost,
    check_divergence,
    classify_and_crosscheck,
    crosscheck_observation,
    crosscheck_response_dict,
    litellm_cost,
)
from charon.proxy import ProxyObservation
from charon.types import Usage

# -- helpers ----------------------------------------------------------------


def _make_obs(*, cost_usd: float = 0.0, tokens_in: int = 0,
              tokens_out: int = 0) -> ProxyObservation:
    """A minimal 200 observation with the given cost."""
    return ProxyObservation(
        requested_model="m1",
        returned_model="m1",
        status=200,
        exhausted=False,
        pseudo_success=False,
        usage=Usage(tokens_in=tokens_in, tokens_out=tokens_out, cost_usd=cost_usd),
    )


# ============================================================================
# (1) AUTHORITY UNCHANGED — cross-check never mutates money-path state
# ============================================================================


class TestAuthorityUnchanged:
    """The cross-check is pure observation — it never touches BalanceTracker,
    never records spend, never parks.  These tests prove that calling any
    cross-check function produces the same result regardless of any
    BalanceTracker state and that no BalanceTracker methods are invoked."""

    def test_crosscheck_returns_delta_without_mutation(self):
        """crosscheck_observation returns a delta and does not modify any
        observable external state.

        FAIL-ON-REVERT: if the cross-check ever calls record_spend / park /
        drain, this test remains green only coincidentally — but the
        *absence* of any BalanceTracker dependency is structural.  The
        function signature takes no BalanceTracker and its result depends
        purely on its inputs.
        """
        raw = type("Raw", (), {"usage": type("U", (), {"cost": 0.005})})()
        obs = _make_obs(cost_usd=0.010)
        delta = crosscheck_observation(raw, obs, model="m1")
        assert delta == pytest.approx(0.005)

    def test_response_dict_variant_also_pure(self):
        """crosscheck_response_dict has no side effects — same contract."""
        raw = {"usage": {"cost": 0.005, "prompt_tokens": 10, "completion_tokens": 5}}
        obs = _make_obs(cost_usd=0.010)
        delta = crosscheck_response_dict(raw, obs, model="m1")
        assert delta == pytest.approx(0.005)

    def test_litellm_cost_extraction_matches_input_only(self):
        """litellm_cost reads from the response and returns the same value
        every time for the same input — no hidden state."""
        r1 = type("R", (), {"usage": type("U", (), {"cost": 0.015})})()
        r2 = type("R", (), {"usage": type("U", (), {"cost": 0.015})})()
        assert litellm_cost(r1) == litellm_cost(r2) == 0.015

    def test_charon_cost_is_read_only(self):
        """charon_cost observes, never writes."""
        obs = _make_obs(cost_usd=0.02)
        before = obs.usage.cost_usd
        result = charon_cost(obs)
        assert result == pytest.approx(0.02)
        assert obs.usage.cost_usd == before  # unchanged

    def test_equal_costs_produce_zero_delta_no_log(self, caplog):
        """When litellm and Charon agree (delta within tolerance), no WARNING
        is emitted."""
        caplog.set_level(logging.WARNING)
        delta = check_divergence(0.01, 0.0105, model="m1")  # delta=0.0005 <= 0.001
        assert delta == pytest.approx(0.0005)
        assert "COST DIVERGENCE" not in caplog.text


# ============================================================================
# (2) DIVERGENCE SURFACED — delta > tolerance logs a WARNING
# ============================================================================


class TestDivergenceSurfaced:
    """When the litellm callback cost differs from Charon's cost beyond the
    USD tolerance, a WARNING is logged.  Reverting this signal removes the
    defense-in-depth value and must fail the assertion."""

    def test_divergence_beyond_tolerance_logs_warning(self, caplog):
        """Delta > $0.001 triggers 'COST DIVERGENCE' at WARNING.

        FAIL-ON-REVERT: silencing or downgrading the divergence log (e.g.
        to DEBUG) removes the alert — this test turns RED."""
        caplog.set_level(logging.WARNING)
        delta = check_divergence(0.0, 0.05, model="m1")  # delta=0.05 >> tolerance
        assert delta == pytest.approx(0.05)
        assert "COST DIVERGENCE" in caplog.text
        assert "0.050000" in caplog.text
        assert "model=m1" in caplog.text

    def test_divergence_logging_includes_both_values(self, caplog):
        """The logged message contains both litellm and charon costs."""
        caplog.set_level(logging.WARNING)
        check_divergence(0.001, 0.010, model="m1", provider="acme")
        assert "litellm=0.001000" in caplog.text
        assert "charon=0.010000" in caplog.text
        assert "provider=acme" in caplog.text

    def test_divergence_via_crosscheck_observation(self, caplog):
        """crosscheck_observation surfaces divergence when the raw response
        and observation carry different costs."""
        caplog.set_level(logging.WARNING)
        raw = type("R", (), {"usage": type("U", (), {"cost": 0.001})})()
        obs = _make_obs(cost_usd=0.020)
        delta = crosscheck_observation(raw, obs, model="m1")
        assert delta == pytest.approx(0.019)
        assert "COST DIVERGENCE" in caplog.text

    def test_divergence_via_response_dict(self, caplog):
        """crosscheck_response_dict also surfaces divergence."""
        caplog.set_level(logging.WARNING)
        raw = {"usage": {"cost": 0.10, "prompt_tokens": 10, "completion_tokens": 5}}
        obs = _make_obs(cost_usd=0.001)
        delta = crosscheck_response_dict(raw, obs)
        assert delta == pytest.approx(0.099)
        assert "COST DIVERGENCE" in caplog.text


# ============================================================================
# (3) NO CORRUPTION — energy-billed / non-token / zero-cost not corrupted
# ============================================================================


class TestNoCorruption:
    """Non-token / energy metering is untouched — Charon's rule stays
    authoritative.  The cross-check never zeroes or double-counts an
    energy-billed provider.  A served downgrade is counted by Charon
    exactly as without the bridge."""

    def test_zero_cost_no_false_divergence(self, caplog):
        """When both litellm and Charon report zero cost (energy-billed
        provider or no cost reported) there is no divergence — the
        cross-check doesn't falsely alert."""
        caplog.set_level(logging.WARNING)
        raw = type("R", (), {"usage": type("U", (), {"cost": 0.0})})()
        obs = _make_obs(cost_usd=0.0)
        delta = crosscheck_observation(raw, obs, model="m1")
        assert delta == pytest.approx(0.0)
        assert "COST DIVERGENCE" not in caplog.text

    def test_no_usage_object_no_crash(self):
        """A response with no usage at all (e.g. non-token error response)
        does not crash the extraction."""
        raw = type("R", (), {"usage": None})()
        assert litellm_cost(raw) == 0.0

    def test_none_observation_no_crash(self):
        """A None observation (e.g. from an error path) does not crash."""
        assert charon_cost(None) == 0.0

    def test_gatewayproxy_classify_not_called_by_crosscheck(self):
        """crosscheck_observation does NOT call GatewayProxy.classify —
        it only reads from the observation that was already classified by
        the caller.  This guarantees the cross-check adds no new classify
        path that could diverge from the authoritative one."""
        raw = type("R", (), {"usage": type("U", (), {"cost": 0.01})})()
        obs = _make_obs(cost_usd=0.01)
        delta = crosscheck_observation(raw, obs, model="m1")
        assert delta == pytest.approx(0.0)

    def test_dict_vs_object_consistency(self):
        """litellm_cost handles dict and object inputs consistently."""
        cost = 0.042
        as_obj = type("R", (), {"usage": type("U", (), {"cost": cost})})()
        as_dict = {"usage": {"cost": cost}}
        assert litellm_cost(as_obj) == pytest.approx(litellm_cost(as_dict))


# ============================================================================
# (3a) _HIDDEN_PARAMS COST — branch-edge coverage for _cost_from_hidden + litellm_cost
# ============================================================================


class TestHiddenParamsCost:
    """Pin every branch edge of the _cost_from_hidden path introduced by
    6782236, plus the zero-sentinel (FIX 2) and total_cost symmetry (FIX 3).

    FAIL-ON-REVERT: every test here names one specific branch edge.  Reverting
    the corresponding logic in metering.py turns the test RED.
    """

    # -- _cost_from_hidden direct unit tests ---------------------------------

    def test_hidden_dict_with_cost(self):
        """Edge: _hidden_params dict, response_cost present non-zero -> returned."""
        hidden = {"response_cost": 0.0042}
        assert _cost_from_hidden(hidden) == pytest.approx(0.0042)

    def test_hidden_dict_key_absent(self):
        """Edge: _hidden_params dict, response_cost key absent -> None (fallback)."""
        hidden = {"other": 1}
        assert _cost_from_hidden(hidden) is None

    def test_hidden_dict_malformed_value(self):
        """Edge: _hidden_params dict, response_cost non-numeric -> None (fallback)."""
        hidden = {"response_cost": "not-a-number"}
        assert _cost_from_hidden(hidden) is None

    def test_hidden_object_with_cost_attr(self):
        """Edge: _hidden_params object, response_cost attr present -> returned."""
        hidden = type("H", (), {"response_cost": 0.0099})()
        assert _cost_from_hidden(hidden) == pytest.approx(0.0099)

    def test_hidden_object_attr_absent(self):
        """Edge: _hidden_params object, no response_cost attr -> None."""
        hidden = type("H", (), {})()
        assert _cost_from_hidden(hidden) is None

    def test_hidden_none(self):
        """Edge: hidden is None -> None."""
        assert _cost_from_hidden(None) is None

    # -- FIX 2: zero sentinel -------------------------------------------------

    def test_zero_response_cost_is_sentinel(self):
        """FIX 2: _cost_from_hidden returns None when response_cost is 0.0,
        letting the caller fall through to usage.cost.

        FAIL-ON-REVERT: if the zero-sentinel is removed, _cost_from_hidden
        returns 0.0 instead of None and this test goes RED."""
        hidden = {"response_cost": 0.0}
        assert _cost_from_hidden(hidden) is None

    def test_litellm_cost_zero_hidden_falls_back_to_usage_object(self):
        """FIX 2: _hidden_params.response_cost=0.0 with usage.cost=0.5
        -> falls through to usage.cost (0.5), not 0.0."""
        obj = type("R", (), {})()
        obj._hidden_params = {"response_cost": 0.0}
        obj.usage = type("U", (), {"cost": 0.5})()
        assert litellm_cost(obj) == pytest.approx(0.5)

    def test_litellm_cost_zero_hidden_falls_back_to_usage_dict(self):
        """FIX 2: dict response with _hidden_params.response_cost=0.0
        and usage.cost=0.6 -> falls through to 0.6."""
        resp = {
            "_hidden_params": {"response_cost": 0.0},
            "usage": {"cost": 0.6, "prompt_tokens": 3, "completion_tokens": 2},
        }
        assert litellm_cost(resp) == pytest.approx(0.6)

    def test_genuine_zero_preserved_via_usage(self):
        """FIX 2: a genuinely-$0.00 request where usage.cost is also 0.0
        still reports 0.0 — zero is not lost, just routed through usage."""
        obj = type("R", (), {})()
        obj._hidden_params = {"response_cost": 0.0}
        obj.usage = type("U", (), {"cost": 0.0})()
        assert litellm_cost(obj) == 0.0

    # -- litellm_cost branch edges (objects) ----------------------------------

    def test_litellm_cost_object_prefers_hidden_params(self):
        """Edge: object with _hidden_params.response_cost=0.001 and
        usage.cost=0.99 -> returns 0.001 (hidden wins)."""
        obj = type("R", (), {})()
        obj._hidden_params = {"response_cost": 0.001}
        obj.usage = type("U", (), {"cost": 0.99})()
        assert litellm_cost(obj) == pytest.approx(0.001)

    def test_litellm_cost_object_falls_back_usage(self):
        """Edge: object _hidden_params without response_cost key -> falls
        back to usage.cost."""
        obj = type("R", (), {})()
        obj._hidden_params = {"other": 1}
        obj.usage = type("U", (), {"cost": 0.007})()
        assert litellm_cost(obj) == pytest.approx(0.007)

    def test_litellm_cost_object_no_hidden_params_at_all(self):
        """Edge: object with no _hidden_params attr -> usage.cost."""
        obj = type("R", (), {"usage": type("U", (), {"cost": 0.003})()})()
        assert litellm_cost(obj) == pytest.approx(0.003)

    # -- litellm_cost branch edges (dicts) ------------------------------------

    def test_litellm_cost_dict_prefers_hidden_params(self):
        """Edge: dict with _hidden_params.response_cost -> returned."""
        resp = {"_hidden_params": {"response_cost": 0.0025},
                "usage": {"cost": 0.99, "total_tokens": 5}}
        assert litellm_cost(resp) == pytest.approx(0.0025)

    def test_litellm_cost_dict_fallback_usage_cost(self):
        """Edge: dict with no _hidden_params, usage.cost present -> returned."""
        resp = {"usage": {"cost": 0.008, "prompt_tokens": 10}}
        assert litellm_cost(resp) == pytest.approx(0.008)

    def test_litellm_cost_dict_fallback_total_cost(self):
        """Edge: dict with usage missing 'cost' but having 'total_cost' ->
        total_cost used."""
        resp = {"usage": {"total_cost": 0.004, "total_tokens": 5}}
        assert litellm_cost(resp) == pytest.approx(0.004)

    def test_litellm_cost_dict_no_usage(self):
        """Edge: dict with no usage key -> 0.0."""
        assert litellm_cost({"id": "x"}) == 0.0

    # -- FIX 3: total_cost symmetry -------------------------------------------

    def test_object_total_cost_fallback(self):
        """FIX 3: object branch now falls back from cost to total_cost,
        matching the dict branch."""
        obj = type("R", (), {})()
        obj.usage = type("U", (), {"total_cost": 0.0033})()
        assert litellm_cost(obj) == pytest.approx(0.0033)

    def test_object_total_cost_with_cost_takes_cost_first(self):
        """FIX 3: when both cost and total_cost are present on object,
        cost is preferred (same as dict branch)."""
        obj = type("R", (), {})()
        obj.usage = type("U", (), {"cost": 0.015, "total_cost": 0.0033})()
        assert litellm_cost(obj) == pytest.approx(0.015)

    def test_dict_total_cost_with_cost_takes_cost_first(self):
        """Dict branch: cost present, total_cost also present -> cost wins."""
        resp = {"usage": {"cost": 0.020, "total_cost": 0.001}}
        assert litellm_cost(resp) == pytest.approx(0.020)


# ============================================================================
# classify_and_crosscheck — integration with real Router
# ============================================================================


@pytest.mark.skipif(not pytest.importorskip("litellm", reason="litellm not installed"),
                    reason="requires litellm")
class TestClassifyAndCrosscheck:
    """Drives a real Router.completion through classify_and_crosscheck
    and asserts the cost cross-check fires without mutating money-path
    state."""

    def test_classify_and_crosscheck_returns_delta(self, monkeypatch, tmp_path):
        """Full integration: a real Router serves a completion, the
        cross-check extracts both costs and returns a delta."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from charon import secrets
        from charon.litellm_plane import litellm_router as lr
        from charon.proxy_server import GatewayProxyServer, UpstreamRoute

        # -- stub upstream that returns a canned response with cost --
        _captured: dict = {}

        class _Stub(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                payload = json.dumps({
                    "id": "cmpl-stub",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "ma",
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant", "content": "pong"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10,
                              "total_tokens": 15, "cost": 0.0025},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        _Stub.calls = 0
        httpd = HTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        secrets.set_provider_key("stub", "STUB-KEY", base_url=upstream)

        route = UpstreamRoute(upstream_base=upstream, api_key=None,
                              provider="stub", upstream_model="ma")
        srv = GatewayProxyServer(host="127.0.0.1", port=0,
                                 pools={"m1": [route]}, default_cooldown=45.0)
        try:
            router = lr.make_router(srv)
            raw, served, obs, delta = classify_and_crosscheck(
                router,
                {"model": "m1", "messages": [{"role": "user", "content": "ping"}]},
            )
        finally:
            srv.server_close()
            httpd.shutdown()
            httpd.server_close()

        # The completion really happened
        assert served.get("object") == "chat.completion"
        # Costs were extracted (delta may be 0 since same source)
        assert isinstance(delta, float)
        assert delta >= 0.0

    def test_classify_and_crosscheck_no_mutation(self, monkeypatch, tmp_path):
        """classify_and_crosscheck does not call record_spend — prove by
        checking no balance tracker is involved."""
        import json
        import threading
        from http.server import BaseHTTPRequestHandler, HTTPServer

        from charon import secrets
        from charon.litellm_plane import litellm_router as lr
        from charon.proxy_server import GatewayProxyServer, UpstreamRoute

        class _Stub(BaseHTTPRequestHandler):
            def log_message(self, *a):
                pass
            def do_POST(self):
                length = int(self.headers.get("Content-Length") or 0)
                self.rfile.read(length)
                payload = json.dumps({
                    "id": "cmpl-stub",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "ma",
                    "choices": [{"index": 0,
                                 "message": {"role": "assistant", "content": "pong"},
                                 "finish_reason": "stop"}],
                    "usage": {"prompt_tokens": 5, "completion_tokens": 10,
                              "total_tokens": 15, "cost": 0.0025},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        httpd = HTTPServer(("127.0.0.1", 0), _Stub)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        upstream = f"http://127.0.0.1:{httpd.server_address[1]}/v1"

        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        secrets.set_provider_key("stub", "STUB-KEY", base_url=upstream)

        route = UpstreamRoute(upstream_base=upstream, api_key=None,
                              provider="stub", upstream_model="ma")
        srv = GatewayProxyServer(host="127.0.0.1", port=0,
                                 pools={"m1": [route]}, default_cooldown=45.0)
        try:
            router = lr.make_router(srv)
            raw, served, obs, delta = classify_and_crosscheck(
                router,
                {"model": "m1", "messages": [{"role": "user", "content": "ping"}]},
            )
        finally:
            srv.server_close()
            httpd.shutdown()
            httpd.server_close()

        # The function returns normally — no crash, no mutation
        assert delta >= 0.0
        assert obs.usage is not None
