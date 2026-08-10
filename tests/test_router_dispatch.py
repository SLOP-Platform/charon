"""Integration tests for the litellm Router dispatch path (PR #266 cutover).

These tests exercise the live Router money-path — ``forward_via_router`` and its
sub-components — against a mock provider. Every covered line here is a line the
diff-coverage gate would otherwise flag as unreachable.

Tests are parametrised on ``use_litellm_router``: True exercises the Router path;
False keeps the hand-rolled path as a control to prove the mock works regardless.
"""
from __future__ import annotations

import http.server
import json
import threading

import pytest

from charon import gateway
from charon.gateway import GatewayConfig

# ── mock provider: serves /models and /chat/completions ───────────────────


class _MockProvider(http.server.BaseHTTPRequestHandler):
    """A stand-in provider that serves valid chat completions."""

    def log_message(self, *a):
        pass

    def do_GET(self):
        body = json.dumps({"data": [{"id": "good-model"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_POST(self):
        self.server.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
        self.server.seen_auths.append(self.server.seen_auth)  # type: ignore[attr-defined]
        body = json.dumps({
            "id": "chatcmpl-mock",
            "object": "chat.completion",
            "created": 1,
            "model": "good-model",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "hello from mock"},
                "finish_reason": "stop",
            }],
            "usage": {
                "prompt_tokens": 5,
                "completion_tokens": 5,
                "total_tokens": 10,
            },
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


# ── helpers ───────────────────────────────────────────────────────────────


def _start():
    import socketserver

    srv = socketserver.ThreadingTCPServer(("127.0.0.1", 0), _MockProvider)
    srv.seen_auth = None  # type: ignore[attr-defined]
    srv.seen_auths = []  # type: ignore[attr-defined]
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv


def _base(srv) -> str:
    return f"http://127.0.0.1:{srv.server_address[1]}/v1"


def _req(url, method="GET", token=None, body=None):
    import urllib.error
    import urllib.request

    data = json.dumps(body).encode() if body else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)  # nosec B310 — test-only mock URL open
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def _serve(tmp_path, *, use_litellm_router: bool = True):
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[],
                      use_litellm_router=use_litellm_router),
        setup_dir=tmp_path)
    server.serve_in_thread()
    return server


# ── the happy-path integration test ───────────────────────────────────────


@pytest.mark.parametrize("use_litellm_router", [False, True])
def test_router_happy_path_successful_completion(
        monkeypatch, tmp_path, use_litellm_router):
    """A legit provider registered with a key, a model added, and a completion
    proxied through the gateway — asserts the provider received the key, the
    response is a 200, and the model matches.

    When ``use_litellm_router=True``, this exercises the full Router dispatch
    path: ``forward_via_router`` → ``complete_via_router_tracked`` →
    ``make_router`` / ``_install_no_redirect_patch`` → 200 post-serve hooks.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    server = _serve(tmp_path, use_litellm_router=use_litellm_router)
    try:
        # Register provider
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "good", "base_url": _base(legit), "key": "sk-good"})
        assert st == 200, f"provider registration failed: {body}"

        # Register model
        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "my-model", "provider": "good", "upstream_model": "good-model"})
        assert st == 200, f"model registration failed: {body}"

        # Send completion
        st, body_str = _req(server.url + "/v1/chat/completions", "POST", token="t",
                            body={"model": "my-model",
                                  "messages": [{"role": "user", "content": "hi"}]})
        assert st == 200, f"completion failed (status {st}): {body_str[:500]}"
        body = json.loads(body_str)
        assert body.get("model") == "good-model", (
            f"expected model 'good-model', got {body.get('model')!r}")
        assert legit.seen_auth == "Bearer sk-good", (
            f"provider did not receive the key: {legit.seen_auth!r}")
        assert len(legit.seen_auths) >= 1, "provider received no requests"
    finally:
        server.shutdown()
        legit.shutdown()


def test_router_build_router_handles_exception(monkeypatch, tmp_path):
    """``_build_router`` exception handler (proxy_server.py:653-654) logs a
    warning when ``make_router`` raises — covered by monkeypatching
    ``litellm.Router`` to raise on construction.

    The monkeypatch is installed BEFORE ``build_server`` so the Router is
    never successfully constructed; the server starts cleanly with the
    hand-rolled fallback."""
    pytest.importorskip("litellm")
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    import litellm
    _orig_router = litellm.Router

    def _bad_router(*args, **kwargs):
        raise RuntimeError("simulated Router construction failure")
    litellm.Router = _bad_router  # type: ignore[assignment,misc]

    try:
        server = gateway.build_server(
            GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[],
                          use_litellm_router=True),
            setup_dir=tmp_path)
        # Router construction failed → router is None (hand-rolled fallback)
        assert server.router is None, (
            f"router should be None when Router construction fails, got {server.router!r}")
    finally:
        litellm.Router = _orig_router  # type: ignore[assignment,misc]


def test_enrich_registry_called_in_load_config(monkeypatch, tmp_path):
    """``gateway.py:209`` — ``enrich_registry`` is called during ``load_config``
    when loading from a models.json file. After enrichment, the model is still
    present in the routes table."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # Write a minimal models.json with a known model
    import os
    os.makedirs(tmp_path, exist_ok=True)
    models = {"gpt-4o": {"provider": "openai"}}
    with open(tmp_path / "models.json", "w") as f:
        json.dump(models, f)

    cfg = gateway.load_config(state_dir=str(tmp_path))
    # The enriched registry should still contain the model (enrich_registry is
    # additive — it never removes entries, only adds cost_input/cost_output).
    assert "gpt-4o" in cfg.routes, (
        f"model should be in routes after enrichment, got {list(cfg.routes)}")


# ── pure-function unit tests ──────────────────────────────────────────────


def test_spend_to_record_from_branches():
    """Cover all four branches of ``_spend_to_record_from``."""
    from charon.forwarder import _spend_to_record_from
    est = 0.005

    # Branch 1: usage not a dict → est_cost
    assert _spend_to_record_from({}, est) == est
    assert _spend_to_record_from({"usage": "bad"}, est) == est

    # Branch 2: cost > 0 → cost
    assert _spend_to_record_from({"usage": {"cost": 0.01}}, est) == 0.01
    assert _spend_to_record_from({"usage": {"total_cost": 0.02}}, est) == 0.02

    # Branch 3: usage has tokens but cost ≤ 0 → 0.0
    assert _spend_to_record_from(
        {"usage": {"prompt_tokens": 10, "completion_tokens": 5}}, est) == 0.0
    assert _spend_to_record_from({"usage": {"total_tokens": 15}}, est) == 0.0

    # Branch 4: usage is a dict with no tokens → est_cost
    assert _spend_to_record_from({"usage": {}}, est) == est
    assert _spend_to_record_from({"usage": {"cost": 0.0, "total_cost": 0.0}}, est) == est


def test_has_assistant_turn():
    """Cover all branches of ``_has_assistant_turn``."""
    from charon.forwarder import _has_assistant_turn

    assert _has_assistant_turn(None) is False
    assert _has_assistant_turn([]) is False
    assert _has_assistant_turn([{"role": "user", "content": "hi"}]) is False
    assert _has_assistant_turn([{"role": "assistant", "content": "hello"}]) is True
    assert _has_assistant_turn([
        {"role": "user", "content": "hi"},
        {"role": "assistant", "content": "hello"},
    ]) is True


def test_gateway_json_use_litellm_router(monkeypatch, tmp_path):
    """Cover loading ``use_litellm_router`` from gateway.json (gateway.py:209)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # Write models.json so the state_dir branch loads
    (tmp_path / "models.json").write_text(json.dumps({"gpt-4o": {"provider": "openai"}}))
    # Write gateway.json with use_litellm_router: false
    (tmp_path / "gateway.json").write_text(json.dumps({"use_litellm_router": False}))

    cfg = gateway.load_config(state_dir=str(tmp_path))
    assert cfg.use_litellm_router is False, "gateway.json use_litellm_router should be read"

    # Verify the hand-rolled path: server built without Router
    server = gateway.build_server(cfg)
    assert server.router is None, "Router should be None when use_litellm_router=False"


# ── litellm_router pure-function unit tests ────────────────────────────────


def test_deployment_with_max_context():
    """Cover ``_deployment`` max_context injection (litellm_router.py:151)."""
    from charon.litellm_plane.litellm_router import _deployment
    from charon.proxy_server import UpstreamRoute

    route = UpstreamRoute(
        upstream_base="http://x/v1", api_key="k", provider="p", max_context=8192)
    dep = _deployment(route, "m1", "http://x/v1", "k")
    assert dep["model_info"]["max_input_tokens"] == 8192


def test_preorder_chain_drained_provider():
    """Cover ``_preorder_chain`` drained-provider exclusion (litellm_router.py:253)."""
    from unittest.mock import MagicMock

    from charon.litellm_plane.litellm_router import _preorder_chain
    from charon.proxy_server import UpstreamRoute

    bt = MagicMock()
    bt.funding_class.return_value = 4
    bt.remaining.return_value = 0.0
    bt.is_parked.return_value = False
    bt.is_drained.return_value = True
    bt.parked_provider_ids.return_value = frozenset()
    bt.cooldown_provider_ids.return_value = frozenset()

    route = UpstreamRoute(upstream_base="http://d/v1", provider="drained")
    result = _preorder_chain([route], bt)
    assert len(result) == 0, "drained provider must be excluded"


def test_primary_leg_no_chain():
    """Cover ``_primary_leg`` returning None when no chain (litellm_router.py:505)."""
    from charon.litellm_plane.litellm_router import _primary_leg
    assert _primary_leg("absent", {}) is None


def test_provider_from_deployment_edge_cases():
    """Cover ``_provider_from_deployment`` falsy model_id + no-match (512,517)."""
    from charon.litellm_plane.litellm_router import _provider_from_deployment

    assert _provider_from_deployment(None, "") == ""
    assert _provider_from_deployment(None, None) == ""


def test_classify_for_envelope_no_bt():
    """Cover ``_classify_for_envelope`` with no balance tracker (523-530)."""
    from charon.litellm_plane.litellm_router import _classify_for_envelope

    cls_, arm = _classify_for_envelope("p", None)
    assert cls_ == "unknown"
    assert arm == "unknown"


def test_synth_exhaustion_envelope_all_parked():
    """Cover ``_synth_exhaustion_envelope`` all_parked=True (538-544)."""
    from charon.litellm_plane.litellm_router import AttemptRecord, _synth_exhaustion_envelope

    rec = AttemptRecord(provider="p1", status=0, ok=False, reason="parked")
    status, env = _synth_exhaustion_envelope(
        "m", [rec], all_parked=True, bt=None)
    assert status == 503
    assert env["error"]["type"] == "all_providers_exhausted"
    assert env["error"]["no_provider_reason"] == "all_legs_parked"
    assert len(env["error"]["providers_tried"]) == 1
    assert env["error"]["providers_tried"][0]["status"] == "parked"


def test_complete_via_router_no_route():
    """Cover ``complete_via_router_tracked`` primary-is-None no-route (574-592)."""
    from charon.litellm_plane.litellm_router import complete_via_router_tracked

    status, env, headers = complete_via_router_tracked(
        None, {"model": "absent", "messages": [{"role": "user", "content": "x"}]},
        chains={}, bt=None, orig_pools=None, orig_routes=None, timeout=10)
    assert status == 502
    assert "no_route_configured" == env["error"]["type"]


# ── litellm_pricing pure-function unit tests ───────────────────────────────


def test_strip_provider_suffix_matching():
    """Cover ``_strip_provider_suffix`` matching suffix (116-118)."""
    from charon.routing_policy.litellm_pricing import _strip_provider_suffix

    assert _strip_provider_suffix("gpt-5.4-mini-ng") == "gpt-5.4-mini"
    assert _strip_provider_suffix("deepseek-v4-flash") == "deepseek-v4-flash"


def test_litellm_candidates_empty_base():
    """Cover ``_litellm_candidates`` empty-base early return (138).
    Patches _strip_free_suffix to return '' so `not base` triggers."""
    from unittest.mock import patch

    from charon.routing_policy.litellm_pricing import _litellm_candidates

    with patch("charon.routing_policy.litellm_pricing._strip_free_suffix",
               return_value=""):
        assert _litellm_candidates("x", {"provider": "deepseek",
                                         "upstream_model": "free-"}) == []


def test_price_for_image_only_entry():
    """Cover ``price_for`` ci_f/co_f both-None branch (litellm_pricing.py:203)."""
    from charon.routing_policy.litellm_pricing import price_for
    # DALL-E is an image-only model in litellm with no token pricing
    dall_e = price_for("dall-e-3", {"provider": "openai"})
    # Must return None — entry exists but carries no token price
    assert dall_e is None


def test_enrich_registry_non_dict_passthrough():
    """Cover ``enrich_registry`` non-dict passthrough (228-229)."""
    from charon.routing_policy.litellm_pricing import enrich_registry

    reg = {"key": "not-a-dict"}
    out = enrich_registry(dict(reg))
    assert out["key"] == "not-a-dict"


def test_coverage_report_all_branches():
    """Cover all branches of ``coverage_report`` (269-296)."""
    from charon.routing_policy.litellm_pricing import coverage_report

    reg = {
        "priced-by-op": {"provider": "a", "cost_input": 1e-6},
        "unmapped": {"provider": "nanogpt", "upstream_model": "nanogpt-id"},
        "skip-non-dict": "not-a-dict",
    }
    report = coverage_report(reg)
    assert report["total"] == 3
    assert report["priced"] >= 1  # priced-by-op is priced
    assert report["unmapped_count"] >= 1  # nanogpt is unmapped
    assert "a" in report["per_provider"]
    assert report["per_provider"]["a"] == [1, 1]  # 1 priced, 1 total
    unmapped_ids = [u["id"] for u in report["unmapped"]]
    assert "unmapped" in unmapped_ids


def test_provider_from_deployment_no_match():
    """Cover _provider_from_deployment return '' when no match (litellm_router.py:517)."""
    from charon.litellm_plane.litellm_router import _provider_from_deployment

    class FakeRouter:
        model_list = [{"model_info": {"id": "other", "provider": "x"}}]

    result = _provider_from_deployment(FakeRouter(), "not-found")
    assert result == ""


def test_classify_for_envelope_fc_returned():
    """Cover _classify_for_envelope with bt returning a funding_class (523-530)."""
    from unittest.mock import MagicMock

    from charon.litellm_plane.litellm_router import _classify_for_envelope

    bt = MagicMock()
    bt.funding_class.return_value = 4
    cls_, arm = _classify_for_envelope("p", bt)
    assert cls_ == "PAYG"
    assert arm == "top-up or rate-limit cooldown"


def test_classify_for_envelope_fc_none():
    """Cover _classify_for_envelope when fc returns None (524-525)."""
    from unittest.mock import MagicMock

    from charon.litellm_plane.litellm_router import _classify_for_envelope

    bt = MagicMock()
    bt.funding_class.return_value = None
    cls_, arm = _classify_for_envelope("p", bt)
    assert cls_ == "unknown"


def test_complete_via_router_all_parked():
    """Cover complete_via_router_tracked all-parked branch (579-591)."""
    from charon.litellm_plane.litellm_router import complete_via_router_tracked
    from charon.proxy_server import UpstreamRoute

    route = UpstreamRoute(upstream_base="http://x/v1", provider="parked")
    status, env, _ = complete_via_router_tracked(
        None, {"model": "m", "messages": [{"role": "user", "content": "x"}]},
        chains={}, bt=None, orig_pools={"m": [route]}, orig_routes=None, timeout=10)
    assert status == 503
    assert env["error"]["type"] == "all_providers_exhausted"
    assert env["error"]["no_provider_reason"] == "all_legs_parked"


def test_coverage_report_litellm_priced():
    """Cover litellm-priced branch of coverage_report (287-289).
    Uses deepseek provider which IS in _PROVIDER_TO_LITELLM."""
    from charon.routing_policy.litellm_pricing import coverage_report

    reg = {"deepseek-chat": {"provider": "deepseek", "upstream_model": "deepseek-chat"}}
    report = coverage_report(reg)
    # deepseek-chat is known to litellm → priced by litellm
    assert report["priced"] >= 1
    assert report["per_provider"]["deepseek"][0] >= 1


# ── module-wired Router path integration test ──────────────────────────────


def test_router_path_with_wired_modules(monkeypatch, tmp_path):
    """Exercise ``forward_via_router`` with spend_limiter, guardrails,
    response_normalizer, semantic_cache, and balance_tracker wired —
    covering the module-guard branches (ADOPT-MAP KEEP-list: spend
    limiter, caching, response normalizer, balance tracking)."""
    pytest.importorskip("litellm")
    from charon.balance import BalanceTracker
    from charon.cache import SemanticCache
    from charon.response_normalizer import ResponseNormalizer
    from charon.spend_limits import SpendDecision, SpendLimiter

    class _RecLimiter(SpendLimiter):
        def __init__(self, d):
            super().__init__(monthly_limit_usd=0.0, state_dir=d)
            self.recorded: list[float] = []

        def check(self, e):
            return SpendDecision(allowed=True, remaining=float("inf"), reason="")

        def record(self, c):
            self.recorded.append(c)

    class _RecNormalizer(ResponseNormalizer):
        def __init__(self):
            self.seen: list[str] = []

        def normalize(self, content, mode):
            self.seen.append(str(content))
            return ResponseNormalizer.normalize(content, mode)

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    legit = _start()
    from charon.guardrails import Guardrails
    limiter = _RecLimiter(tmp_path)
    norm = _RecNormalizer()
    cache = SemanticCache()
    bt = BalanceTracker()
    gr = Guardrails(config={"disable_pii": True})
    # Wrap record_spend to capture the spend args flowing through R1's cost binding
    _bt_spend_args: list[tuple] = []
    _bt_orig_record = bt.record_spend

    def _bt_record_spend(provider, usd, model=None):
        _bt_spend_args.append((provider, usd, model))
        _bt_orig_record(provider, usd, model=model)
    bt.record_spend = _bt_record_spend

    server = _serve(tmp_path, use_litellm_router=True)
    server.spend_limiter = limiter
    server.response_normalizer = norm
    server.semantic_cache = cache
    server.balance_tracker = bt
    server.guardrails = gr

    try:
        # Register provider then model — these may rebuild the observer,
        # so wire pricing AFTER registration
        st, body = _req(server.url + "/charon/providers", "POST", token="t", body={
            "name": "good", "base_url": _base(legit), "key": "sk-good"})
        assert st == 200, f"provider registration failed: {body}"

        st, body = _req(server.url + "/charon/models", "POST", token="t", body={
            "id": "my-model", "provider": "good", "upstream_model": "good-model"})
        assert st == 200, f"model registration failed: {body}"

        # Wire pricing so the observer can compute non-zero cost from tokens
        server.model_pricing = {"good-model": {"cost_input": 1e-6, "cost_output": 2e-6}}
        server.observer.set_pricing(server.model_pricing)

        # Send completion
        st, body_str = _req(server.url + "/v1/chat/completions", "POST", token="t",
                            body={"model": "my-model",
                                  "messages": [{"role": "user", "content": "hi"}]})
        assert st == 200, f"completion failed (status {st}): {body_str[:500]}"
        body = json.loads(body_str)
        assert body.get("model") == "good-model"

        # spend_limiter: exercised (the guard branch is covered)
        assert limiter.recorded, "spend_limiter.record was never called"

        # response_normalizer: exercised
        assert norm.seen, "response_normalizer was never called"

        # balance_tracker: record_spend was called through the R1 cost binding
        assert _bt_spend_args, (
            "balance_tracker.record_spend was never called — "
            "the guard branch at :500 was NOT exercised")
        prov, cost_val, model = _bt_spend_args[0]
        assert cost_val > 0.0, (
            f"balance_tracker.record_spend got cost={cost_val!r} — "
            "R1 cost binding is still producing $0.00. "
            f"Provider={prov!r}, model={model!r}")
    finally:
        server.shutdown()
        legit.shutdown()
