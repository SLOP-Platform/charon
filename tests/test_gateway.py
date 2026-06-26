"""P1 — standalone ``charon gateway``: config loading, /v1/models, token gate,
loopback guard, and an end-to-end forward through a mock upstream.
"""
from __future__ import annotations

import http.server
import json
import socketserver
import threading
import urllib.error
import urllib.request

from charon import gateway
from charon.gateway import GatewayConfig
from charon.proxy_server import UpstreamRoute


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
        assert "upstream_base" not in json.dumps(body) and "api_key" not in json.dumps(body)
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


# ---- loopback guard -------------------------------------------------------

def test_run_refuses_nonloopback_without_token(capsys):
    cfg = GatewayConfig(host="0.0.0.0", token=None)
    assert gateway.run(cfg) == 2  # refused before binding
    assert "non-loopback" in capsys.readouterr().err
