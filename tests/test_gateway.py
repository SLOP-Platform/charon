"""P1 — standalone ``charon gateway``: config loading, /v1/models, token gate,
loopback guard, and an end-to-end forward through a mock upstream.
"""
from __future__ import annotations

import ast
import http.server
import json
import pathlib
import socketserver
import threading
import urllib.error
import urllib.request

import pytest

import charon
from charon import gateway
from charon.gateway import GatewayConfig
from charon.proxy import GatewayProxy
from charon.proxy_server import GatewayProxyServer, UpstreamRoute


def test_gateway_shares_core_and_excludes_privileged_loop():
    """P6/ADR-0005 R3: the gateway and the orchestrator share ONE provider/failover
    core (the `GatewayProxy` observer), and the gateway request path must NEVER
    import the privileged coordinator loop."""
    src_dir = pathlib.Path(charon.__file__).parent
    for mod in ("gateway.py", "proxy_server.py"):
        tree = ast.parse((src_dir / mod).read_text())
        imported: set[str] = set()
        for n in ast.walk(tree):
            if isinstance(n, ast.ImportFrom) and n.module:
                imported.add(n.module)
            elif isinstance(n, ast.Import):
                imported.update(a.name for a in n.names)
        assert not any("coordinator" in m for m in imported), f"{mod} imports the loop"
    # shared core: the gateway observes via the same classifier the orchestrator uses
    srv = GatewayProxyServer()
    try:
        assert isinstance(srv.observer, GatewayProxy)
    finally:
        srv.server_close()


class _MockUpstream(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a) -> None:
        pass

    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = json.dumps({
            "model": body.get("model"),
            "choices": [{"message": {"content": "ok"}}],
            "usage": {"prompt_tokens": 3, "completion_tokens": 2, "cost": 0.01},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _mk_upstream():
    srv = _Threaded(("127.0.0.1", 0), _MockUpstream)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    return srv, f"http://{srv.server_address[0]}:{srv.server_address[1]}"


def _req(url: str, *, method="GET", token=None, header=True, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token and header:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


# ---- config loading -------------------------------------------------------

def test_load_config_from_toml_resolves_keys_and_overrides(monkeypatch, tmp_path):
    monkeypatch.setenv("OR_KEY", "sekret")
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[gateway]\nhost = "127.0.0.1"\nport = 9999\ntoken = "t0"\n\n'
        '[models."openrouter/qwen:free"]\n'
        'upstream_base = "https://openrouter.ai/api/v1"\n'
        'key_env = "OR_KEY"\nupstream_model = "qwen/real:free"\n\n'
        '[models."local-only-acp"]\n'  # no upstream_base → skipped
        'cost_rank = 5\n'
    )
    cfg = gateway.load_config(toml_path=toml)
    assert cfg.port == 9999 and cfg.token == "t0"
    assert cfg.model_ids == ["openrouter/qwen:free"]  # acp-only entry skipped
    route = cfg.routes["openrouter/qwen:free"]
    assert route.api_key == "sekret" and route.upstream_model == "qwen/real:free"
    # explicit args win over file
    cfg2 = gateway.load_config(toml_path=toml, port=1234, token="cli")
    assert cfg2.port == 1234 and cfg2.token == "cli"


def test_load_config_from_models_json(monkeypatch, tmp_path):
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    (tmp_path / "models.json").write_text(json.dumps({
        "kimi": {"agent": "opencode", "upstream_base": "http://x/v1", "free": True},
    }))
    cfg = gateway.load_config(state_dir=tmp_path)
    assert cfg.model_ids == ["kimi"] and cfg.token is None
    assert cfg.routes["kimi"].upstream_base == "http://x/v1"


def test_token_falls_back_to_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_GATEWAY_TOKEN", "envtok")
    cfg = gateway.load_config(state_dir=tmp_path)  # empty dir → no models
    assert cfg.token == "envtok"


def test_load_config_builds_cost_ranked_pool(tmp_path):
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[models."paid"]\nupstream_base = "http://paid/v1"\ncost_rank = 10\n\n'
        '[models."free1"]\nupstream_base = "http://free/v1"\nfree = true\ncost_rank = 0\n\n'
        '[pools]\nauto = ["paid", "free1"]\n'  # listed paid-first; free must sort first
    )
    cfg = gateway.load_config(toml_path=toml)
    assert "auto" in cfg.pools and "auto" in cfg.model_ids and "paid" in cfg.model_ids
    # the failover chain is ordered free-first / cheapest-first regardless of listing
    assert [r.upstream_base for r in cfg.pools["auto"]] == ["http://free/v1", "http://paid/v1"]


# ---- /v1/models + token gate ---------------------------------------------

def test_models_endpoint_and_token_gate():
    cfg = GatewayConfig(
        port=0,
        token="s3cret",
        routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
        model_ids=["m1"],
    )
    server = gateway.build_server(cfg)
    server.serve_in_thread()
    try:
        # no token → 401
        status, _ = _req(server.url + "/v1/models")
        assert status == 401
        # bearer header → 200 + only ids exposed (no key_env/upstream_base leak)
        status, body = _req(server.url + "/v1/models", token="s3cret")
        assert status == 200
        assert [m["id"] for m in body["data"]] == ["m1"]
        # ?token= query also works (browser URL)
        status, _ = _req(server.url + "/v1/models?token=s3cret", token=None)
        assert status == 200
        # wrong token → 401
        status, _ = _req(server.url + "/v1/models", token="nope")
        assert status == 401
    finally:
        server.shutdown()


def test_gateway_forwards_chat_completions_end_to_end():
    up, base = _mk_upstream()
    cfg = GatewayConfig(
        port=0,
        routes={"kimi": UpstreamRoute(base, api_key="k", upstream_model="kimi-real")},
        model_ids=["kimi"],
    )
    server = gateway.build_server(cfg)
    server.serve_in_thread()
    try:
        status, body = _req(server.url + "/v1/chat/completions",
                            method="POST", payload={"model": "kimi"})
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "ok"
        assert server.observer.cumulative_usage().cost_usd == 0.01
    finally:
        server.shutdown()
        up.shutdown()


# ---- /v1/models metadata + pool filtering ---------------------------------

def test_models_endpoint_surfaces_metadata():
    cfg = GatewayConfig(
        port=0,
        token="t",
        routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
        model_ids=["m1"],
        model_meta={"m1": {"context_window": 200000, "max_tokens": 32768,
                            "reasoning": True, "vision": False}},
    )
    srv = gateway.build_server(cfg)
    srv.serve_in_thread()
    try:
        _, body = _req(srv.url + "/v1/models", token="t")
        assert body["data"][0]["id"] == "m1"
        assert body["data"][0]["context_window"] == 200000
        assert body["data"][0]["max_tokens"] == 32768
        assert body["data"][0]["reasoning"] is True
        assert body["data"][0]["vision"] is False
        assert "audio" not in body["data"][0]    # not present → not emitted
    finally:
        srv.shutdown()


def test_models_endpoint_excludes_pool_ids():
    cfg = GatewayConfig(
        port=0,
        token="t",
        routes={
            "m1": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k"),
            "m2": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k"),
        },
        pools={"auto": [
            UpstreamRoute("http://127.0.0.1:1/v1", api_key="k"),
        ]},
        model_ids=["auto", "m1", "m2"],  # pool id IS in the internal list
    )
    srv = gateway.build_server(cfg)
    srv.serve_in_thread()
    try:
        _, body = _req(srv.url + "/v1/models", token="t")
        ids = [m["id"] for m in body["data"]]
        assert ids == ["m1", "m2"]       # "auto" excluded
        assert "auto" not in ids
    finally:
        srv.shutdown()


def test_models_endpoint_does_not_exclude_model_in_both_routes_and_pools():
    """A concrete model whose id happens to match a pool name is still a real model."""
    cfg = GatewayConfig(
        port=0,
        token="t",
        routes={"low": UpstreamRoute("http://127.0.0.1:1/v1", api_key="k")},
        pools={"low": [
            UpstreamRoute("http://127.0.0.1:1/v1", api_key="k"),
            UpstreamRoute("http://127.0.0.1:1/v1", api_key="k2"),
        ]},
        model_ids=["low"],
    )
    srv = gateway.build_server(cfg)
    srv.serve_in_thread()
    try:
        _, body = _req(srv.url + "/v1/models", token="t")
        ids = [m["id"] for m in body["data"]]
        assert ids == ["low"]   # not excluded — it IS a concrete model
    finally:
        srv.shutdown()


# ---- loopback guard -------------------------------------------------------

def test_run_refuses_nonloopback_without_token(capsys):
    cfg = GatewayConfig(host="0.0.0.0", token=None)
    assert gateway.run(cfg) == 2  # refused before binding
    assert "non-loopback" in capsys.readouterr().err


def test_failover_chain_check_warns_when_no_pools_or_fallback(capsys, monkeypatch) -> None:
    """When no pools and no fallback are configured, the gateway must print a
    strong warning so operators know their setup is fragile."""
    # Hermetic: _check_failover_safety also reads on-disk pools/fallback config, so a
    # host that HAS those files (e.g. a live gateway box) would suppress the warning
    # and fail this test spuriously. Force the "nothing configured" state.
    monkeypatch.setattr("charon.config.load_fallback_providers", lambda: {})
    monkeypatch.setattr("charon.config.load_pools", lambda: {})
    cfg = GatewayConfig(routes={}, pools={}, token="t",
                        host="127.0.0.1", port=0)
    try:
        srv = gateway.build_server(cfg)
    except Exception:  # pragma: no cover
        pytest.fail("build_server should not raise for loopback+token")

    # Simulate the startup warning path (run() calls _check_failover_safety)
    gateway._check_failover_safety(cfg)
    captured = capsys.readouterr()
    assert "NO FAILOVER CHAIN" in captured.err
    srv.server_close()


# ---- SR-6: auto-derive cost_rank + cost_class ------------------------------
# The failover chain is now CHEAP-FIRST automatically: cost_rank is DERIVED from
# per-token pricing (3:1 in:out blend) when no explicit override is set, free
# models still sort first, and `cost_class: "premium"` is gated out of
# default-primary pools (usable only when explicitly requested or in a premium
# role). See `gateway._build_routes_and_pools` (SR-6).

def test_sr6_derived_rank_orders_by_blended_cost(tmp_path):
    """cost_rank is DERIVED from cost_input/cost_output (3:1 blend) when no
    explicit override is set; cheaper-input models sort first within the paid
    bucket (free models still sort absolutely first).

    Pricing convention is per-token USD (``0.0000025`` == $2.50/1M tokens, see
    ``providers._extract_pricing``). The derived-rank scale maps ~$1/1M tokens
    to rank ~100, composing with the historical hand-set range (0-9999)."""
    toml = tmp_path / "charon.toml"
    toml.write_text(
        # cheap-paid: $0.50/1M in, $1.50/1M out → blended ~$0.75/1M → rank ~75
        '[models."cheap-paid"]\nupstream_base = "http://cheap/v1"\n'
        'cost_input = 0.0000005\ncost_output = 0.0000015\n\n'
        # dear-paid: $5/1M in, $15/1M out → blended ~$7.50/1M → rank ~750
        '[models."dear-paid"]\nupstream_base = "http://dear/v1"\n'
        'cost_input = 0.000005\ncost_output = 0.000015\n\n'
        # free still sorts first despite having "expensive-looking" pricing metadata
        '[models."free-one"]\nupstream_base = "http://free/v1"\nfree = true\n'
        'cost_input = 0.1\ncost_output = 0.1\n\n'
        '[pools]\nauto = ["dear-paid", "cheap-paid", "free-one"]\n'  # listed dear-first
    )
    cfg = gateway.load_config(toml_path=toml)
    chain = cfg.pools["auto"]
    assert [r.upstream_base for r in chain] == [
        "http://free/v1",      # free-first (always)
        "http://cheap/v1",     # then cheapest blended
        "http://dear/v1",      # then dearer
    ]


def test_sr6_explicit_cost_rank_override_ignored(tmp_path):
    """DELETE-STATIC-RANK (ADR-0016 step #6): a hand-typed ``cost_rank`` is no
    longer an operator escape hatch — it is IGNORED.  force-dear is naturally
    cheaper ($0.10/1M) than natural ($2/1M); the operator's hand-typed
    ``cost_rank = 9999`` is ignored, and force-dear sorts FIRST.

    This test is the FAIL-ON-REVERT companion to the old
    ``test_sr6_explicit_cost_rank_override_wins``: revert the deletion (re-honor
    explicit cost_rank) and this assertion goes RED."""
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[models."force-dear"]\nupstream_base = "http://a/v1"\n'
        'cost_input = 0.0000001\ncost_output = 0.0000001\ncost_rank = 9999\n\n'
        '[models."natural"]\nupstream_base = "http://b/v1"\n'
        'cost_input = 0.000002\ncost_output = 0.000002\n\n'
        '[pools]\nauto = ["force-dear", "natural"]\n'
    )
    import warnings as _w
    with _w.catch_warnings():
        _w.simplefilter("ignore", DeprecationWarning)
        cfg = gateway.load_config(toml_path=toml)
    chain = cfg.pools["auto"]
    # DELETE-STATIC-RANK: cost_rank=9999 is IGNORED, so the cheaper-by-price
    # model sorts first.
    assert [r.upstream_base for r in chain] == ["http://a/v1", "http://b/v1"], (
        "hand-typed cost_rank=9999 leaked into the sort — DELETE-STATIC-RANK is "
        "reverted; ADR-0016 step #6 contract broken"
    )


def test_sr6_missing_pricing_falls_back_to_default_rank(tmp_path):
    """A model with neither cost_input/cost_output NOR an explicit cost_rank gets
    the neutral default (1000) — it sorts after cheap models, before dear ones."""
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[models."priced"]\nupstream_base = "http://a/v1"\n'
        'cost_input = 0.0000001\ncost_output = 0.0000001\n\n'  # → rank ~10
        '[models."unpriced"]\nupstream_base = "http://b/v1"\n'   # → default 1000
        '[pools]\nauto = ["unpriced", "priced"]\n'
    )
    cfg = gateway.load_config(toml_path=toml)
    chain = cfg.pools["auto"]
    assert [r.upstream_base for r in chain] == ["http://a/v1", "http://b/v1"]


def test_sr6_premium_class_gated_out_of_default_pool(tmp_path):
    """A `cost_class: "premium"` model is EXCLUDED from a default-primary pool
    chain (it's still routable directly via `routes`, just not the cheap-first
    default). This prevents a GPT-5.5/Opus-class model from ever being the
    silent default-primary."""
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[models."cheap"]\nupstream_base = "http://cheap/v1"\n'
        'cost_input = 0.0000005\ncost_output = 0.0000015\n\n'
        '[models."premium-opus"]\nupstream_base = "http://opus/v1"\n'
        'cost_input = 0.00005\ncost_output = 0.00015\ncost_class = "premium"\n\n'
        '[pools]\nauto = ["premium-opus", "cheap"]\n'
    )
    cfg = gateway.load_config(toml_path=toml)
    # premium gated out of the default chain
    chain = cfg.pools["auto"]
    assert [r.upstream_base for r in chain] == ["http://cheap/v1"]
    # but it remains explicitly routable (not removed from routes)
    assert "premium-opus" in cfg.routes
    assert cfg.routes["premium-opus"].upstream_base == "http://opus/v1"


def test_sr6_premium_only_pool_is_operators_opt_in(tmp_path):
    """If EVERY member of a pool is premium, the pool is kept as-is (an explicit
    premium-only role is the operator's opt-in — we don't silently empty it)."""
    toml = tmp_path / "charon.toml"
    toml.write_text(
        '[models."opus-a"]\nupstream_base = "http://a/v1"\ncost_class = "premium"\n\n'
        '[models."opus-b"]\nupstream_base = "http://b/v1"\ncost_class = "premium"\n\n'
        '[pools]\nprem = ["opus-a", "opus-b"]\n'
    )
    cfg = gateway.load_config(toml_path=toml)
    chain = cfg.pools["prem"]
    assert {r.upstream_base for r in chain} == {"http://a/v1", "http://b/v1"}


def test_sr6_cost_class_normalized_on_add_model(tmp_path, monkeypatch):
    """`config.add_model` normalizes cost_class to the canonical lowercase
    vocabulary and silently drops unknown values (no crash, just not persisted)."""
    from charon import config as _config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _config.add_model("m1", upstream_base="http://x/v1", cost_class="PREMIUM")
    _config.add_model("m2", upstream_base="http://x/v1", cost_class="bogus")
    models = _config.load_models()
    assert models["m1"].get("cost_class") == "premium"  # normalized
    assert "cost_class" not in models["m2"]              # bogus dropped


def test_sr6_cost_carried_through_bulk_import(tmp_path, monkeypatch):
    """`add_models_bulk` carries `cost_class` through the import path (same as
    cost_input/cost_output/context_window)."""
    from charon import config as _config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    _config.add_models_bulk([
        {"id": "m1", "free": False, "cost_class": "premium"},
        {"id": "m2", "free": True, "cost_class": "free-daily"},
        {"id": "m3", "free": False, "cost_class": "garbage"},  # dropped
    ], provider="openrouter")
    models = _config.load_models()
    assert models["m1"]["cost_class"] == "premium"
    assert models["m2"]["cost_class"] == "free-daily"
    assert "cost_class" not in models["m3"]


# ---- SR-6: production path tests (models.json / add_model / add_models_bulk) ----

def test_sr6_derived_rank_from_add_model_production_path(tmp_path, monkeypatch):
    """cost_rank is DERIVED from pricing when models are added through add_model
    (the models.json production path) WITHOUT an explicit cost_rank — the dear-first
    pool listing MUST be reordered cheap-first. This is the test whose absence masked
    the blocker defect."""
    from charon import config as _config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # dear-paid: $5/1M in, $15/1M out → blended ~$7.50/1M → rank ~750
    _config.add_model("dear", upstream_base="http://dear/v1",
                      cost_input=0.000005, cost_output=0.000015)
    # cheap-paid: $0.50/1M in, $1.50/1M out → blended ~$0.75/1M → rank ~75
    _config.add_model("cheap", upstream_base="http://cheap/v1",
                      cost_input=0.0000005, cost_output=0.0000015)
    # free with "expensive" pricing still sorts first
    _config.add_model("freebie", upstream_base="http://free/v1", free=True,
                      cost_input=0.1, cost_output=0.1)

    _config.set_pool("auto", ["dear", "cheap", "freebie"])  # listed dear-first
    cfg = gateway.load_config(state_dir=tmp_path)
    chain = cfg.pools["auto"]
    assert [r.upstream_base for r in chain] == [
        "http://free/v1",      # free-first
        "http://cheap/v1",     # then cheapest (rank ~75)
        "http://dear/v1",      # then dear (rank ~750)
    ]


def test_sr6_derived_rank_from_add_models_bulk_production_path(tmp_path, monkeypatch):
    """cost_rank is DERIVED when models are added through add_models_bulk (the
    models-import production path) with pricing but no explicit cost_rank."""
    from charon import config as _config
    from charon.pools import derived_cost_rank
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    _config.add_models_bulk([
        {"id": "dear",  "free": False, "cost_input": 0.000005,  "cost_output": 0.000015},
        {"id": "cheap", "free": False, "cost_input": 0.0000005, "cost_output": 0.0000015},
        {"id": "freebie", "free": True, "cost_input": 0.1, "cost_output": 0.1},
    ], provider="test")

    models = _config.load_models()
    # No cost_rank was stamped on any model
    for mid in ("dear", "cheap", "freebie"):
        assert "cost_rank" not in models[mid], f"{mid} must not have stamped cost_rank"
    # Derived ranks compute correctly from pricing
    assert derived_cost_rank(models["cheap"]) < derived_cost_rank(models["dear"])


def test_sr6_explicit_cost_rank_via_add_model_ignored(tmp_path, monkeypatch):
    """DELETE-STATIC-RANK (ADR-0016 step #6): a hand-typed ``cost_rank`` via
    ``add_model`` is IGNORED — the derivation wins.  The field is also no
    longer PERSISTED to ``models.json`` (see
    ``tests/test_delete_static_rank.py`` for the persistence assertion).

    Previously this test asserted the SR-5b escape-hatch behavior; the deletion
    contract flips that — revert the deletion and this test goes RED."""
    from charon import config as _config
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    # force-dear is naturally cheap; operator's hand-typed 9999 is ignored
    with pytest.warns(DeprecationWarning, match=r"cost_rank=9999"):
        _config.add_model("force-dear", upstream_base="http://a/v1",
                          cost_input=0.0000001, cost_output=0.0000001, cost_rank=9999)
    _config.add_model("natural", upstream_base="http://b/v1",
                      cost_input=0.000002, cost_output=0.000002)

    _config.set_pool("auto", ["force-dear", "natural"])
    cfg = gateway.load_config(state_dir=tmp_path)
    chain = cfg.pools["auto"]
    # DELETE-STATIC-RANK: hand-typed 9999 is ignored; cheaper-by-price wins.
    assert [r.upstream_base for r in chain] == ["http://a/v1", "http://b/v1"], (
        "hand-typed cost_rank via add_model leaked into the sort — "
        "DELETE-STATIC-RANK is reverted; ADR-0016 step #6 contract broken"
    )
    # And the field is NOT persisted.
    persisted = _config.load_models()
    assert "cost_rank" not in persisted["force-dear"], (
        f"cost_rank leaked into models.json: {persisted['force-dear']!r}"
    )


# ---- DRAIN-AND-PARK: balance tracker construction ---------------------------

def test_load_config_builds_balance_tracker_from_provider_config(monkeypatch, tmp_path):
    """When a provider has balance fields (funding_class, mode, starting_balance),
    load_config constructs a non-None GatewayConfig.balance_tracker.

    FAIL-ON-REVERT: reverting the balance-tracker construction must fail the
    cfg.balance_tracker is not None assertion."""
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    (tmp_path / "models.json").write_text(json.dumps({
        "test-model": {
            "provider": "test-provider",
            "upstream_base": "http://x/v1",
        },
    }))
    (tmp_path / "providers.json").write_text(json.dumps({
        "test-provider": {
            "base_url": "http://x/v1",
            "funding_class": 3,
            "mode": "fixed",
            "starting_balance": 50.0,
        },
    }))
    cfg = gateway.load_config(state_dir=tmp_path)
    assert cfg.balance_tracker is not None, (
        "FAIL-ON-REVERT: balance_tracker must be constructed from provider config")
    # The tracker should know about this provider
    fc = cfg.balance_tracker.funding_class("test-provider")
    assert fc == 3


def test_load_config_no_balance_when_no_provider_balance_fields(monkeypatch, tmp_path):
    """Without any balance fields in providers.json, balance_tracker stays None
    (backward-compatible — current behavior)."""
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    (tmp_path / "models.json").write_text(json.dumps({
        "m": {"upstream_base": "http://x/v1"},
    }))
    (tmp_path / "providers.json").write_text(json.dumps({
        "plain-provider": {"base_url": "http://x/v1"},
    }))
    cfg = gateway.load_config(state_dir=tmp_path)
    assert cfg.balance_tracker is None
