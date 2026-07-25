"""End-to-end: a real request served THROUGH the adopted litellm.Router path.

Unlike ``test_litellm_router_adopt.py`` (unit-level control checks), this drives the FULL
path a live request takes — a real ``GatewayProxyServer`` config → :func:`make_router`
→ ``Router.completion`` → an httpx send to a real (stub) upstream → a served response — and
asserts the money-path security controls actually FIRE on that path:

  * #181 base-bound key READ        — the stub upstream receives exactly the key that was
                                      stored BOUND to its base
  * SSRF refusal                    — a metadata base is refused before the Router builds
  * preset egress allowlist         — an off-preset (attacker) base is refused (egress.py
                                      reconciliation: litellm_plane enforces the SAME allowlist
                                      the live route_from_spec path enforces)
  * SG-never-Anthropic              — an Anthropic-only model has no deployment to serve
  * chain order is BINDING          — ``litellm_params['order']``: the funding-class /
                                      drain-then-park chain Charon computes is the chain litellm
                                      actually dials, measured as a WIRE distribution over many
                                      real requests (not an assertion about router internals)
  * context-window pre-call check   — ``enable_pre_call_checks``: a leg whose ``max_context``
                                      cannot hold the prompt is never dialed

litellm is required for this module (it makes the real call); skipped when absent.
"""
from __future__ import annotations

import json
import threading
from collections import Counter
from http.server import BaseHTTPRequestHandler, HTTPServer

import pytest

pytest.importorskip("litellm")

import litellm  # noqa: E402
from litellm.exceptions import BadRequestError  # noqa: E402

from charon import egress, secrets  # noqa: E402
from charon.litellm_plane import litellm_router as lr  # noqa: E402
from charon.proxy_server import GatewayProxyServer, UpstreamRoute  # noqa: E402

# Enough real requests that a uniform shuffle over a 3-leg chain could not plausibly land on
# one leg by luck: p = 3 * (1/3)**300. The MEASURED pre-fix distribution over exactly this
# fixture was 97/95/108 (litellm's default `simple-shuffle`); the fix makes it 300/0/0.
FIRST_LEG_TRIALS = 300


class _StubUpstream(BaseHTTPRequestHandler):
    """A minimal OpenAI-compatible upstream. Captures the Authorization header of the last
    request (so the test can prove the base-bound key was delivered) and returns a canned
    chat completion. Bound to loopback, which egress._is_local_host permits."""

    captured_auth: str | None = None
    captured_path: str | None = None

    def log_message(self, *a):  # keep test output clean
        pass

    def do_POST(self):
        length = int(self.headers.get("Content-Length") or 0)
        _ = self.rfile.read(length)
        type(self).captured_auth = self.headers.get("Authorization")
        type(self).captured_path = self.path
        payload = json.dumps({
            "id": "chatcmpl-stub",
            "object": "chat.completion",
            "created": 0,
            "model": "ma",
            "choices": [{
                "index": 0,
                "message": {"role": "assistant", "content": "pong"},
                "finish_reason": "stop",
            }],
            "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


@pytest.fixture()
def stub_upstream():
    _StubUpstream.captured_auth = None
    _StubUpstream.captured_path = None
    httpd = HTTPServer(("127.0.0.1", 0), _StubUpstream)
    t = threading.Thread(target=httpd.serve_forever, daemon=True)
    t.start()
    port = httpd.server_address[1]
    try:
        yield f"http://127.0.0.1:{port}/v1"
    finally:
        httpd.shutdown()
        httpd.server_close()


def _make_gateway(pools, **kw):
    """A real GatewayProxyServer (loopback, ephemeral port), used purely as the config
    source make_router reads — never serve_forever'd here."""
    return GatewayProxyServer(host="127.0.0.1", port=0, pools=pools, default_cooldown=45.0, **kw)


@pytest.fixture()
def stub_fleet():
    """Spawn LABELLED loopback upstreams and count which one each request actually reached.

    Yields ``(spawn, hits)``: ``spawn("leg1")`` returns that leg's base URL, and ``hits["leg1"]``
    is how many completions that leg really SERVED. Selection is therefore measured on the wire
    — the leg had to be dialed for its counter to move — rather than by reading back the
    router's own bookkeeping, which is what makes the ordering assertions non-vacuous.
    """
    hits: Counter = Counter()
    servers: list[HTTPServer] = []

    def spawn(label: str) -> str:
        class _Handler(BaseHTTPRequestHandler):
            def log_message(self, *a):  # keep test output clean
                pass

            def do_POST(self):
                self.rfile.read(int(self.headers.get("Content-Length") or 0))
                hits[label] += 1
                payload = json.dumps({
                    "id": f"chatcmpl-{label}",
                    "object": "chat.completion",
                    "created": 0,
                    "model": "ma",
                    "choices": [{
                        "index": 0,
                        "message": {"role": "assistant", "content": label},
                        "finish_reason": "stop",
                    }],
                    "usage": {"prompt_tokens": 1, "completion_tokens": 1, "total_tokens": 2},
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(payload)))
                self.end_headers()
                self.wfile.write(payload)

        httpd = HTTPServer(("127.0.0.1", 0), _Handler)
        threading.Thread(target=httpd.serve_forever, daemon=True).start()
        servers.append(httpd)
        return f"http://127.0.0.1:{httpd.server_address[1]}/v1"

    try:
        yield spawn, hits
    finally:
        for httpd in servers:
            httpd.shutdown()
            httpd.server_close()


def _leg(label: str, base: str, **kw) -> UpstreamRoute:
    """A chain leg pointing at one spawned stub, with its key stored BOUND to that base
    (so the #181 control resolves a real key and the leg is genuinely dialable)."""
    secrets.set_provider_key(label, f"KEY-{label}", base_url=base)
    return UpstreamRoute(upstream_base=base, api_key=None, provider=label,
                         upstream_model="ma", **kw)


def _drive(router, n: int, *, content: str = "ping") -> None:
    """Issue *n* real completions through the adopted Router serve path."""
    for _ in range(n):
        lr.complete_via_router(
            router, {"model": "m1", "messages": [{"role": "user", "content": content}]})


def test_e2e_served_response_and_base_bound_key(stub_upstream, monkeypatch, tmp_path):
    """A full request is served through the adopted Router, and the stub upstream receives
    exactly the key stored BOUND to its base (the #181 read firing on the live path)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_provider_key("stub", "STUB-KEY-BOUND", base_url=stub_upstream)

    route = UpstreamRoute(upstream_base=stub_upstream, api_key=None, provider="stub",
                          upstream_model="ma")
    srv = _make_gateway({"m1": [route]})
    try:
        router = lr.make_router(srv)
        resp = lr.complete_via_router(router, {
            "model": "m1",
            "messages": [{"role": "user", "content": "ping"}],
        })
    finally:
        srv.server_close()

    # served response really came back through the router — assert the top-level
    # OpenAI envelope contract, not just content nested inside choices.
    assert resp.get("object") == "chat.completion"
    assert "choices" in resp and resp.get("usage")
    assert resp["choices"][0]["message"]["content"] == "pong"
    # #181: the base-bound key was read and delivered to its own base — nothing else
    assert _StubUpstream.captured_auth == "Bearer STUB-KEY-BOUND"
    assert _StubUpstream.captured_path.endswith("/chat/completions")


def test_e2e_ssrf_metadata_base_refused(monkeypatch, tmp_path):
    """A cloud-metadata base is refused BEFORE the Router is built — it never reaches litellm."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    bad = UpstreamRoute(upstream_base="http://169.254.169.254/v1", provider="evil")
    srv = _make_gateway({"m1": [bad]})
    try:
        with pytest.raises(lr.AdoptError):
            lr.make_router(srv)
    finally:
        srv.server_close()


def test_e2e_off_preset_base_refused_by_egress(monkeypatch, tmp_path):
    """egress.py reconciliation on the live path: a public, SSRF-clean base whose host is NOT
    a git-tracked preset is refused by the fail-closed egress allowlist before the Router
    builds — so litellm_plane cannot reach an arbitrary host the live path would reject."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    off = UpstreamRoute(upstream_base="https://attacker.example/v1", provider="x")
    srv = _make_gateway({"m1": [off]})
    try:
        with pytest.raises(egress.EgressPolicyError):
            lr.make_router(srv)
    finally:
        srv.server_close()


def test_e2e_anthropic_model_has_no_deployment(monkeypatch, tmp_path):
    """SG-never-Anthropic on the live path: an Anthropic-only model's legs are all dropped
    (the base host is preset-allowlisted, so egress passes — the SG guard is what drops it),
    so the Router has no deployment and the request cannot be served through Anthropic."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    claude = UpstreamRoute(upstream_base="https://api.anthropic.com/v1", provider="anthropic",
                           upstream_model="claude-3-opus")
    srv = _make_gateway({"claude-3-opus": [claude]})
    try:
        router = lr.make_router(srv)
        assert router.model_list == []
        # litellm raises BadRequestError ("No deployments available") when no leg survives.
        with pytest.raises(BadRequestError):
            lr.complete_via_router(router, {
                "model": "claude-3-opus",
                "messages": [{"role": "user", "content": "hi"}],
            })
    finally:
        srv.server_close()


# --------------------------------------------------------------------------------------
# Chain order is BINDING on litellm (litellm_params['order'])
# --------------------------------------------------------------------------------------

def test_e2e_first_leg_is_deterministic_not_shuffled(stub_fleet, monkeypatch, tmp_path):
    """The head of the chain serves EVERY request — measured on the wire over 300 real
    completions against three healthy, equally-dialable loopback legs.

    This is the regression that matters: with no ``order``, litellm falls back to
    ``simple-shuffle`` and spreads traffic uniformly across the model group (this exact fixture
    measured 97/95/108), which silently discards the funding-class chain Charon computed. The
    assertion is exact — 300/0/0 — because "mostly leg1" is the same bug with a smaller sample.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    chain = [_leg(lbl, spawn(lbl)) for lbl in ("leg1", "leg2", "leg3")]

    srv = _make_gateway({"m1": chain})
    try:
        router = lr.make_router(srv)
        # Non-vacuity: all three legs really are in the group and eligible — the other two are
        # not absent, cooled, or keyless; they are simply out-ranked.
        assert len(router.model_list) == 3
        assert [d["litellm_params"]["order"] for d in router.model_list] == [1, 2, 3]
        assert len({d["litellm_params"]["api_base"] for d in router.model_list}) == 3
        _drive(router, FIRST_LEG_TRIALS)
    finally:
        srv.server_close()

    assert dict(hits) == {"leg1": FIRST_LEG_TRIALS}


def test_e2e_selection_follows_charon_chain_order_not_insertion_luck(
        stub_fleet, monkeypatch, tmp_path):
    """Reordering the CHAIN reorders the wire traffic — the same three legs, declared
    head-last, now send every request to what is now the head.

    Paired with the test above this rules out the vacuous explanations (a fixed leg is
    special, only one leg is reachable, litellm happens to prefer the first-registered
    deployment): the only thing that changed is Charon's chain order, and the wire followed it.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    legs = {lbl: _leg(lbl, spawn(lbl)) for lbl in ("leg1", "leg2", "leg3")}
    reversed_chain = [legs["leg3"], legs["leg2"], legs["leg1"]]

    srv = _make_gateway({"m1": reversed_chain})
    try:
        router = lr.make_router(srv)
        _drive(router, FIRST_LEG_TRIALS)
    finally:
        srv.server_close()

    assert dict(hits) == {"leg3": FIRST_LEG_TRIALS}


def test_e2e_funding_class_preorder_binds_free_leg_first(stub_fleet, monkeypatch, tmp_path):
    """The money-path point: a chain declared PAYG-first is pre-ordered free-first by
    :func:`_preorder_chain`, and that pre-order now actually reaches the wire.

    Before ``order``, this computation happened and was then thrown away — a shuffle would put
    roughly a third of paid traffic on the PAYG leg while a free-recurring leg sat idle. Here
    the free leg takes 300/300 and the PAYG leg is never billed once.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    payg = _leg("payg", spawn("payg"))
    free = _leg("free", spawn("free"))

    class _BT:
        """Minimal BalanceTracker duck-type: funding class 4 = PAYG, 1 = free-recurring."""

        def funding_class(self, provider):
            return {"free": 1, "payg": 4}.get(provider)

        def remaining(self, provider):
            return None

        def is_parked(self, provider):
            return False

    # Declared PAYG-first on purpose: only the funding-class pre-order can flip it.
    srv = _make_gateway({"m1": [payg, free]}, balance_tracker=_BT())
    try:
        router = lr.make_router(srv)
        by_order = {d["litellm_params"]["order"]: d["litellm_params"]["api_base"]
                    for d in router.model_list}
        assert by_order[1] == free.upstream_base and by_order[2] == payg.upstream_base
        _drive(router, FIRST_LEG_TRIALS)
    finally:
        srv.server_close()

    assert dict(hits) == {"free": FIRST_LEG_TRIALS}


def test_e2e_order_stays_contiguous_when_a_control_drops_a_leg(
        stub_fleet, monkeypatch, tmp_path):
    """SG-never-Anthropic drops the declared head, and the SURVIVING head becomes order=1.

    Ranks must count admitted legs, not raw chain positions — a hole at order=1 would still
    route correctly today (litellm takes the min) but makes the rank stop meaning "position in
    the chain litellm will walk", and the order-based fallback sequence is built from these
    values.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    claude = UpstreamRoute(upstream_base="https://api.anthropic.com/v1", provider="anthropic",
                           upstream_model="claude-3-opus")
    survivors = [_leg(lbl, spawn(lbl)) for lbl in ("leg1", "leg2")]

    srv = _make_gateway({"m1": [claude, *survivors]})
    try:
        router = lr.make_router(srv)
        assert [d["litellm_params"]["order"] for d in router.model_list] == [1, 2]
        _drive(router, 20)
    finally:
        srv.server_close()

    assert dict(hits) == {"leg1": 20}


# --------------------------------------------------------------------------------------
# Context-window pre-call check (enable_pre_call_checks) — max_context is LIVE config
# --------------------------------------------------------------------------------------

def _oversized_prompt(limit: int) -> str:
    """A prompt litellm's own token counter agrees is larger than *limit* tokens."""
    content = "token " * (limit * 4)
    counted = litellm.token_counter(messages=[{"role": "user", "content": content}])
    assert counted > limit, f"prompt is {counted} tokens, not > {limit}"
    return content


def test_e2e_leg_too_small_for_prompt_is_skipped_for_the_next_one(
        stub_fleet, monkeypatch, tmp_path):
    """A prompt larger than the head leg's ``max_context`` is served by the next leg that can
    hold it — and the head is never dialed.

    This is what ``enable_pre_call_checks`` buys. With it off (litellm's default), the
    ``max_input_tokens`` written from ``route.max_context`` is dead config: ``order`` pins the
    request to the 50-token head, which burns a request to earn an upstream rejection. The same
    router serves a SHORT prompt from the head, so the small leg is demonstrably healthy and
    reachable — it is skipped for this prompt only, not broken.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    small = _leg("small", spawn("small"), max_context=50)
    big = _leg("big", spawn("big"), max_context=100_000)

    srv = _make_gateway({"m1": [small, big]})
    try:
        router = lr.make_router(srv)
        assert router.enable_pre_call_checks is True
        # Control: a short prompt fits the head, so the head serves it.
        _drive(router, 5, content="ping")
        assert dict(hits) == {"small": 5}
        # The oversized prompt must skip the head entirely.
        _drive(router, 5, content=_oversized_prompt(50))
    finally:
        srv.server_close()

    assert dict(hits) == {"small": 5, "big": 5}


def test_e2e_prompt_over_every_leg_fails_loud_without_dialing_anything(
        stub_fleet, monkeypatch, tmp_path):
    """When NO leg's context can hold the prompt, the request fails loud before any upstream is
    dialed — litellm raises ``ContextWindowExceededError`` and both stubs stay at zero.

    Fail-loud, not fail-quiet: the alternative (checks off) is to spend a real request against
    a leg that cannot possibly serve it and surface the upstream's error instead.
    """
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    spawn, hits = stub_fleet
    chain = [_leg(lbl, spawn(lbl), max_context=50) for lbl in ("leg1", "leg2")]

    srv = _make_gateway({"m1": chain})
    try:
        router = lr.make_router(srv)
        with pytest.raises(litellm.ContextWindowExceededError):
            _drive(router, 1, content=_oversized_prompt(50))
    finally:
        srv.server_close()

    assert dict(hits) == {}, "no upstream may be dialed when no leg can hold the prompt"
