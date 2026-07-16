from __future__ import annotations

import io
import json
import urllib.error
from unittest import mock

import pytest

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


def test_build_request_sends_shared_browser_ua() -> None:
    """P5: upstream POST must carry the shared browser-like UA so a Cloudflare-fronted
    provider (error 1010 → 403) is not wrongly failed. Never urllib-default / charon-proxy."""
    from charon.netutil import BROWSER_UA

    se = SpeculativeExecutor(enabled=True)

    class FakeRoute:
        upstream_base = "https://api.example.com"
        api_key = "sk-test"
        strip_v1 = True
        upstream_model = None

    req = se._build_request(FakeRoute(), b'{"model":"gpt-4"}', "application/json")
    ua = req.get_header("User-agent")
    assert ua == BROWSER_UA
    assert ua != "charon-proxy/0.1"
    assert not (ua or "").lower().startswith("python-urllib")


def test_build_request_rewrites_model() -> None:
    se = SpeculativeExecutor(enabled=True)

    class FakeRoute:
        upstream_base = "https://api.example.com"
        api_key = None
        strip_v1 = True
        upstream_model = "us-east-model"

    req = se._build_request(FakeRoute(), b'{"model":"gpt-4"}', "application/json")
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


# --- DESTIFF-SPECULATIVE: failover composition -----------------------------

class _FakeRoute:
    def __init__(self, label: str, base: str = "https://api.example.com") -> None:
        self.label = label
        self.upstream_base = base
        self.api_key = "sk-test"
        self.strip_v1 = True
        self.upstream_model = None


def _http_response(status: int, body: bytes = b'{"ok":true}') -> mock.Mock:
    resp = mock.Mock()
    resp.status = status
    resp.read = lambda: body
    resp.headers = {"content-type": "application/json"}
    return resp


def _http_error(status: int, body: bytes = b'{"error":"bad key"}') -> urllib.error.HTTPError:
    import email.message
    hdrs = email.message.Message()
    hdrs["content-type"] = "application/json"
    return urllib.error.HTTPError(
        url="https://x.example/v1/chat/completions",
        code=status,
        msg="err",
        hdrs=hdrs,
        fp=io.BytesIO(body),
    )


def test_classify_200_is_ok() -> None:
    se = SpeculativeExecutor()
    kind, _, attribution = se._classify(SpecResult(status=200, latency_ms=12.0))
    assert kind == "ok"
    assert "200" in attribution


def test_classify_401_is_failover() -> None:
    se = SpeculativeExecutor()
    kind, _, attribution = se._classify(SpecResult(status=401, body=b"{}"))
    assert kind == "failover"
    assert "401" in attribution


def test_classify_429_is_failover() -> None:
    se = SpeculativeExecutor()
    kind, _, attribution = se._classify(SpecResult(status=429))
    assert kind == "failover"
    assert "429" in attribution


def test_classify_500_is_failover() -> None:
    se = SpeculativeExecutor()
    kind, _, _ = se._classify(SpecResult(status=500))
    assert kind == "failover"


def test_classify_transport_error_is_failover() -> None:
    se = SpeculativeExecutor()
    kind, _, attribution = se._classify(SpecResult(error="connection refused"))
    assert kind == "failover"
    assert "transport" in attribution


def test_classify_upstream_400_is_ok() -> None:
    """An upstream-issued 4xx (e.g. bad prompt) is a *valid* response — return it,
    do not skip it (FAILOVER would lose a verdict the caller can act on) and do
    not retry (RETRY would POST again)."""
    se = SpeculativeExecutor()
    kind, _, _ = se._classify(SpecResult(status=400, body=b'{"err":"bad prompt"}'))
    assert kind == "ok"


def test_execute_first_good_wins_unaffected() -> None:
    """Existing first-good-wins contract: a 200 from candidate A returns
    immediately, B and C are cancelled. The failover composition must not
    re-issue or change this."""
    se = SpeculativeExecutor(enabled=True, max_providers=3)
    routes = [_FakeRoute("a"), _FakeRoute("b"), _FakeRoute("c")]

    call_log: list[str] = []

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url
        if "a" in url or "b" in url or "c" in url:
            # Map by host label: routes are differentiated by base URL; we use
            # body-derived tagging. Simpler: use a global counter.
            idx = len(call_log)
            call_log.append(url)
            if idx == 0:
                return _http_response(200, b'{"winner":"first"}')
            # Other providers — would block, but the race cancels them.
            import time as _t
            _t.sleep(2.0)
            return _http_response(200, b"{}")

    with mock.patch("charon.speculative_execution.urllib.request.urlopen",
                    side_effect=fake_urlopen):
        result = se.execute(routes, b"{}")

    assert result is not None
    assert result.status == 200
    assert result.body == b'{"winner":"first"}'
    # The first 200 wins; we don't have to assert cancellation of others here
    # — that's covered by the existing race semantics, unchanged.


def test_execute_failover_mid_race_yields_next_result() -> None:
    """The DESTIFF-SPECULATIVE accept: candidate A 401s, candidate B 200s →
    the race must surface B's 200 (not A's 401, not a hard fail). B's
    request was already in flight — no re-issue — and the primitive's
    composition never doubles up."""
    se = SpeculativeExecutor(enabled=True, max_providers=3, timeout_ms=5000.0)
    routes = [_FakeRoute("a"), _FakeRoute("b"), _FakeRoute("c")]

    import time as _t

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url
        # Differentiate by port-less URL last segment (a.example.com / b / c)
        if "a." in url:
            _t.sleep(0.01)  # arrives first
            raise _http_error(401)
        if "b." in url:
            _t.sleep(0.05)  # arrives second but is 200
            return _http_response(200, b'{"winner":"b"}')
        # c: never returns in time
        _t.sleep(2.0)
        return _http_response(200, b"{}")

    for r in routes:
        r.upstream_base = f"https://{r.label}.example.com"

    with mock.patch("charon.speculative_execution.urllib.request.urlopen",
                    side_effect=fake_urlopen):
        result = se.execute(routes, b"{}")

    assert result is not None
    assert result.status == 200
    assert result.body == b'{"winner":"b"}'
    assert result.provider == "b"


def test_execute_all_fail_raises_exhaustion() -> None:
    """All candidates return provider-level faults (401/429/5xx) → the
    failover_loop primitive's exhaustion error is raised, naming every
    candidate's failure and ending with an actionable recommendation."""
    se = SpeculativeExecutor(enabled=True, max_providers=3, timeout_ms=5000.0)
    routes = [_FakeRoute("a"), _FakeRoute("b"), _FakeRoute("c")]

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        url = req.full_url
        if "a." in url:
            raise _http_error(401)
        if "b." in url:
            raise _http_error(429)
        raise _http_error(503)

    for r in routes:
        r.upstream_base = f"https://{r.label}.example.com"

    with mock.patch("charon.speculative_execution.urllib.request.urlopen",
                    side_effect=fake_urlopen):
        with pytest.raises(RuntimeError) as ei:
            se.execute(routes, b"{}")
    msg = str(ei.value)
    # invoke_with_failover exhaustion contract: every candidate named, recommendation
    assert "all candidates exhausted" in msg
    assert "a:" in msg and "b:" in msg and "c:" in msg
    assert "401" in msg
    assert "429" in msg
    assert "503" in msg
    assert "check keys" in msg or "balances" in msg or "health" in msg


def test_execute_failover_does_not_reissue() -> None:
    """The primitive is composed WITHOUT re-issuing: the attempt callable
    returns the already-collected result. We assert by counting urlopen
    calls — one per candidate, no more."""
    se = SpeculativeExecutor(enabled=True, max_providers=2, timeout_ms=5000.0)
    routes = [_FakeRoute("a"), _FakeRoute("b")]

    counter = {"n": 0}

    def fake_urlopen(req, timeout=None):  # noqa: ARG001
        counter["n"] += 1
        url = req.full_url
        if "a." in url:
            raise _http_error(401)
        if "b." in url:
            raise _http_error(429)
        raise _http_error(500)

    for r in routes:
        r.upstream_base = f"https://{r.label}.example.com"

    with mock.patch("charon.speculative_execution.urllib.request.urlopen",
                    side_effect=fake_urlopen):
        with pytest.raises(RuntimeError):
            se.execute(routes, b"{}")

    expected = 2
    assert counter["n"] == expected, (
        f"expected exactly {expected} upstream calls (one per candidate), got {counter['n']}"
    )
