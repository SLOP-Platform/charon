# check-test-patterns: allow-self-mirroring-mock
"""FALLBACK-PROVIDER — global fallback provider chain: config persist/load,
gateway chain compilation, web setup POST, and end-to-end failover.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon import config, gateway, secrets
from charon.gateway import GatewayConfig
from charon.proxy_server import UpstreamRoute

# ---- config persist / load -----------------------------------------------

def test_fallback_config_persist_and_load(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert config.load_fallback_providers() == []
    p = config.set_fallback_providers(["opencode-zen", "  opencode-go  "])
    assert p == tmp_path / "fallback.json"
    assert config.load_fallback_providers() == ["opencode-zen", "opencode-go"]


def test_fallback_load_absent_or_malformed(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert config.load_fallback_providers() == []
    (tmp_path / "fallback.json").write_text("not json")
    assert config.load_fallback_providers() == []
    (tmp_path / "fallback.json").write_text(json.dumps({"wrong": "key"}))
    assert config.load_fallback_providers() == []


def test_fallback_set_persists_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_fallback_providers(["opencode-zen"])
    assert config.load_fallback_providers() == ["opencode-zen"]
    config.set_fallback_providers([])
    assert config.load_fallback_providers() == []


# ---- gateway chain compilation -------------------------------------------

def _provider_entry(name: str, base: str, key_env: str | None = None) -> dict:
    e: dict = {"base_url": base}
    if key_env:
        e["key_env"] = key_env
    return e


def test_fallback_chain_appended_to_pools(monkeypatch, tmp_path):
    """When fallback providers are configured, they are appended to every pool chain."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK1", "key-a")
    monkeypatch.setenv("DK2", "key-b")
    monkeypatch.setenv("DK3", "key-c")

    # Providers — p3 is the fallback, distinct from p1 and p2 in the pool
    provs = {
        "p1": {"base_url": "http://p1.example/v1", "key_env": "DK1"},
        "p2": {"base_url": "http://p2.example/v1", "key_env": "DK2"},
        "p3": {"base_url": "http://p3.example/v1", "key_env": "DK3"},
    }
    (tmp_path / "providers.json").write_text(json.dumps(provs))

    # Models
    (tmp_path / "models.json").write_text(json.dumps({
        "m1": {"provider": "p1", "cost_rank": 10},
        "m2": {"provider": "p2", "free": True, "cost_rank": 0},
    }))

    # Pool
    (tmp_path / "pools.json").write_text(json.dumps({"auto": ["m1", "m2"]}))

    # Fallback — p3 is NOT in the pool chain, so it gets appended
    config.set_fallback_providers(["p3"])

    cfg = gateway.load_config(state_dir=tmp_path)
    assert "auto" in cfg.pools
    chain = cfg.pools["auto"]
    # m2 (free) → m1 (paid) → p3 (fallback)
    assert len(chain) == 3
    assert chain[0].upstream_base == "http://p2.example/v1"  # free first
    assert chain[1].upstream_base == "http://p1.example/v1"   # cost_rank 10
    assert chain[2].upstream_base == "http://p3.example/v1"   # fallback (p3)


def test_fallback_chain_appended_to_single_routes(monkeypatch, tmp_path):
    """Single-route models (not in any pool) also get fallback appended."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK1", "key-a")
    monkeypatch.setenv("DK2", "key-b")

    (tmp_path / "providers.json").write_text(json.dumps({
        "p1": {"base_url": "http://p1.example/v1", "key_env": "DK1"},
        "p2": {"base_url": "http://p2.example/v1", "key_env": "DK2"},
    }))
    (tmp_path / "models.json").write_text(json.dumps({
        "m1": {"provider": "p1", "cost_rank": 10},
    }))
    config.set_fallback_providers(["p2"])

    cfg = gateway.load_config(state_dir=tmp_path)
    # m1 is in routes but also now in pools (with fallback)
    assert "m1" in cfg.routes
    assert "m1" in cfg.pools
    chain = cfg.pools["m1"]
    assert len(chain) == 2
    assert chain[0].upstream_base == "http://p1.example/v1"  # primary
    assert chain[1].upstream_base == "http://p2.example/v1"  # fallback


def test_fallback_skips_unknown_providers(monkeypatch, tmp_path):
    """Unknown fallback provider names are silently skipped."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK1", "key-a")

    (tmp_path / "providers.json").write_text(json.dumps({
        "p1": {"base_url": "http://p1.example/v1", "key_env": "DK1"},
    }))
    (tmp_path / "models.json").write_text(json.dumps({
        "m1": {"provider": "p1", "cost_rank": 10},
    }))
    config.set_fallback_providers(["p1", "no-such-provider"])

    cfg = gateway.load_config(state_dir=tmp_path)
    chain = cfg.pools["m1"]
    assert len(chain) == 2  # p1 (primary) + p1 (fallback) — no-such-provider skipped
    assert all(r.upstream_base == "http://p1.example/v1" for r in chain)


def test_empty_fallback_keeps_chains_unchanged(monkeypatch, tmp_path):
    """When no fallback is configured, single-route models stay out of pools."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK1", "key-a")

    (tmp_path / "providers.json").write_text(json.dumps({
        "p1": {"base_url": "http://p1.example/v1", "key_env": "DK1"},
    }))
    (tmp_path / "models.json").write_text(json.dumps({
        "m1": {"provider": "p1"},
    }))

    cfg = gateway.load_config(state_dir=tmp_path)
    assert "m1" in cfg.routes
    assert "m1" not in cfg.pools  # no fallback → stays as single route only


def test_fallback_does_not_add_duplicates(monkeypatch, tmp_path):
    """If a fallback provider is already in the chain, it's not duplicated."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK1", "key-a")

    (tmp_path / "providers.json").write_text(json.dumps({
        "p1": {"base_url": "http://p1.example/v1", "key_env": "DK1"},
    }))
    (tmp_path / "models.json").write_text(json.dumps({
        "m1": {"provider": "p1", "cost_rank": 10},
    }))
    (tmp_path / "pools.json").write_text(json.dumps({"auto": ["m1"]}))
    config.set_fallback_providers(["p1"])  # same as primary

    cfg = gateway.load_config(state_dir=tmp_path)
    chain = cfg.pools["auto"]
    assert len(chain) == 1  # not duplicated


# ---- web setup POST writes fallback config --------------------------------

class _Threaded(socketserver.ThreadingMixIn, http.server.HTTPServer):
    daemon_threads = True
    allow_reuse_address = True


def _req(url: str, *, method="GET", token=None, payload=None):
    data = json.dumps(payload).encode() if payload is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        resp = urllib.request.urlopen(req, timeout=10)
        return resp.status, json.loads(resp.read())
    except urllib.error.HTTPError as exc:
        return exc.code, json.loads(exc.read())


def test_fallback_setup_handler_writes_config(monkeypatch, tmp_path):
    """POST /charon/fallback persists the fallback provider list and reloads."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)

    cfg = GatewayConfig(
        port=0, token="t",
        routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1")},
        model_ids=["m1"],
    )
    server = gateway.build_server(cfg, setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        # Write fallback config
        status, body = _req(server.url + "/charon/fallback",
                            method="POST", token="t",
                            payload={"providers": ["opencode-zen", "openrouter"]})
        assert status == 200
        assert body["ok"] is True

        # Verify it was persisted
        assert config.load_fallback_providers() == ["opencode-zen", "openrouter"]
    finally:
        server.shutdown()


def test_fallback_surfaces_in_summary(monkeypatch, tmp_path):
    """The summary endpoint includes the current fallback list."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    config.set_fallback_providers(["opencode-zen"])

    cfg = GatewayConfig(
        port=0, token="t",
        routes={"m1": UpstreamRoute("http://127.0.0.1:1/v1")},
        model_ids=["m1"],
    )
    server = gateway.build_server(cfg, setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        _, body = _req(server.url + "/charon/config", token="t")
        assert body.get("fallback") == ["opencode-zen"]
    finally:
        server.shutdown()


# ---- end-to-end failover via global fallback ------------------------------

class _FailPrimary(http.server.BaseHTTPRequestHandler):
    """Always returns 429 — exhausted primary provider."""
    def log_message(self, *a) -> None:
        pass
    def do_POST(self) -> None:
        self.send_response(429)
        self.send_header("Content-Type", "application/json")
        self.send_header("Retry-After", "30")
        self.end_headers()
        self.wfile.write(json.dumps({"error": "quota exceeded"}).encode())


class _HealthyFallback(http.server.BaseHTTPRequestHandler):
    """Returns a normal 200 chat completion."""
    def log_message(self, *a) -> None:
        pass
    def do_POST(self) -> None:
        length = int(self.headers.get("Content-Length") or 0)
        body = json.loads(self.rfile.read(length) or b"{}")
        payload = json.dumps({
            "model": body.get("model"),
            "choices": [{"message": {"content": "fallback-ok"}}],
            "usage": {"prompt_tokens": 2, "completion_tokens": 1, "cost": 0.0},
        }).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)


def _start_mock(handler_class) -> tuple[socketserver.BaseServer, str]:
    srv = _Threaded(("127.0.0.1", 0), handler_class)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address[0], srv.server_address[1]
    if isinstance(host, bytes):
        host = host.decode()
    return srv, f"http://{host}:{port}"


def test_fallback_end_to_end_failover(monkeypatch, tmp_path):
    """A model whose primary returns 429 falls back to the global fallback."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    primary_srv, primary_base = _start_mock(_FailPrimary)
    fallback_srv, fallback_base = _start_mock(_HealthyFallback)

    # Configure providers + model + fallback via the config dir
    monkeypatch.setenv("PRIMARY_KEY", "key-p")
    monkeypatch.setenv("FALLBACK_KEY", "key-f")
    config.add_provider("primary-p", base_url=primary_base, key_env="PRIMARY_KEY")
    config.add_provider("fallback-p", base_url=fallback_base, key_env="FALLBACK_KEY")
    config.add_model("test-model", provider="primary-p")

    # Fallback set to the healthy provider
    config.set_fallback_providers(["fallback-p"])

    cfg = gateway.load_config(state_dir=secrets.config_dir(), port=0)
    assert "test-model" in cfg.pools
    chain = cfg.pools["test-model"]
    assert len(chain) == 2
    assert chain[1].upstream_base == fallback_base   # fallback at position 1

    server = gateway.build_server(cfg)
    server.serve_in_thread()
    try:
        status, body = _req(server.url + "/v1/chat/completions",
                            method="POST", payload={"model": "test-model"})
        assert status == 200
        assert body["choices"][0]["message"]["content"] == "fallback-ok"
        # The observer should show the primary failed and fallback served
        stats = server.status_snapshot()
        assert stats["providers"]["primary-p"]["failed"] >= 1
        assert stats["providers"]["fallback-p"]["served"] >= 1
        # Failover event logged
        assert any("test-model" == e["model"] for e in stats["recent_failovers"])
    finally:
        server.shutdown()
        primary_srv.shutdown()
        fallback_srv.shutdown()


def test_fallback_end_to_end_exhausted_then_served(monkeypatch, tmp_path):
    """Both primary and fallback return 429 — every provider in the pool is exhausted,
    so the gateway synthesizes a terminal "all providers exhausted" 503 (carrying the
    tracked failover reasons) rather than relaying the last raw 429."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    primary_srv, primary_base = _start_mock(_FailPrimary)
    fallback_srv, fallback_base = _start_mock(_FailPrimary)

    monkeypatch.setenv("PK", "key-p")
    monkeypatch.setenv("FK", "key-f")
    config.add_provider("exhausted-p", base_url=primary_base, key_env="PK")
    config.add_provider("exhausted-f", base_url=fallback_base, key_env="FK")
    config.add_model("m", provider="exhausted-p")
    config.set_fallback_providers(["exhausted-f"])

    cfg = gateway.load_config(state_dir=secrets.config_dir(), port=0)
    server = gateway.build_server(cfg)
    server.serve_in_thread()
    try:
        status, body = _req(server.url + "/v1/chat/completions",
                            method="POST", payload={"model": "m"})
        assert status == 503  # synthesized terminal — every provider exhausted
        assert body["error"]["type"] == "all_providers_exhausted"
    finally:
        server.shutdown()
        primary_srv.shutdown()
        fallback_srv.shutdown()
