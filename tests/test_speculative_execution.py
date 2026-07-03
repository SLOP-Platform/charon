from __future__ import annotations

from charon.speculative_execution import SpecResult, SpeculativeExecutor


def test_init_disabled_by_default() -> None:
    se = SpeculativeExecutor()
    assert se.enabled is False
    assert se.max_providers == 3


def test_execute_returns_none_when_disabled() -> None:
    se = SpeculativeExecutor(enabled=False)
    assert se.execute([], b"{}") is None


def test_execute_returns_none_for_empty_routes() -> None:
    se = SpeculativeExecutor(enabled=True)
    assert se.execute([], b"{}") is None


def test_build_request_adds_auth_header() -> None:
    se = SpeculativeExecutor(enabled=True)

    class FakeRoute:
        upstream_base = "https://api.example.com"
        api_key = "sk-test"
        strip_v1 = True
        upstream_model = None

    req = se._build_request(FakeRoute(), b'{"model":"gpt-4"}', "application/json")
    assert req.get_header("Authorization") == "Bearer sk-test"


def test_build_request_rewrites_model() -> None:
    se = SpeculativeExecutor(enabled=True)

    class FakeRoute:
        upstream_base = "https://api.example.com"
        api_key = None
        strip_v1 = True
        upstream_model = "us-east-model"

    req = se._build_request(FakeRoute(), b'{"model":"gpt-4"}', "application/json")
    import json
    body = json.loads(req.data)
    assert body["model"] == "us-east-model"


def test_build_request_strip_v1_false_url() -> None:
    se = SpeculativeExecutor(enabled=True)

    class FakeRoute:
        upstream_base = "https://api.example.com"
        api_key = None
        strip_v1 = False
        upstream_model = None

    req = se._build_request(FakeRoute(), b"{}", "application/json")
    assert "/v1/chat/completions" in req.full_url


def test_spec_result_defaults() -> None:
    sr = SpecResult()
    assert sr.provider == ""
    assert sr.status == 0
    assert sr.body == b""
