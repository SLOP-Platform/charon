"""import-all-models — pull a provider's /models catalog and add it all to config.

Covers the pure parse/free detection, the security guards on the keyed fetch, the
atomic bulk write (with bad-id skipping), the CLI command, and the web endpoint.
"""
from __future__ import annotations

import http.server
import json
import threading
import urllib.error
import urllib.request

import pytest

from charon import cli, config, gateway, providers
from charon.gateway import GatewayConfig

# ---- pure parsing / free detection ------------------------------------------

def test_parse_models_openai_shape_and_free():
    data = {"data": [
        {"id": "gpt-4o"},
        {"id": "free-model:free"},
        {"id": "cheap", "pricing": {"prompt": "0", "completion": "0"}},
        {"id": "paid", "pricing": {"prompt": "0.001", "completion": "0.002"}},
        {"no_id": True},        # skipped
    ]}
    out = providers._parse_models(data)
    assert {m["id"] for m in out} == {"gpt-4o", "free-model:free", "cheap", "paid"}
    free = {m["id"] for m in out if m["free"]}
    assert free == {"free-model:free", "cheap"}


def test_parse_models_bare_and_string_lists():
    assert providers._parse_models(["a", "b"]) == [
        {"id": "a", "free": False}, {"id": "b", "free": False}]
    assert providers._parse_models("garbage") == []


# ---- keyed fetch + security guards ------------------------------------------

class _ModelsHandler(http.server.BaseHTTPRequestHandler):
    def log_message(self, *a):  # quiet
        pass

    def do_GET(self):
        self.server.seen_auth = self.headers.get("Authorization")  # type: ignore[attr-defined]
        body = json.dumps({"data": [{"id": "m1"}, {"id": "m2:free"}]}).encode()
        self.send_response(200)
        self.send_header("Content-Type", "application/json")
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)


def test_list_models_sends_key_and_parses(monkeypatch):
    srv = http.server.HTTPServer(("127.0.0.1", 0), _ModelsHandler)
    srv.seen_auth = None
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    try:
        base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
        got = providers.list_models("p", {"base_url": base}, api_key="sk-secret")
        assert {m["id"] for m in got} == {"m1", "m2:free"}
        assert any(m["free"] for m in got)               # m2:free flagged free
        assert srv.seen_auth == "Bearer sk-secret"       # key WAS sent (to the local base)
    finally:
        srv.shutdown()


def test_list_models_refuses_link_local_and_bad_scheme():
    with pytest.raises(ValueError):
        providers.list_models("p", {"base_url": "http://169.254.169.254/v1"}, api_key="k")
    with pytest.raises(ValueError):
        providers.list_models("p", {"base_url": "ftp://h/v1"}, api_key="k")


# ---- atomic bulk write ------------------------------------------------------

def test_add_models_bulk_skips_bad_ids_and_sets_fields(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    added, skipped = config.add_models_bulk(
        [{"id": "good-1"}, {"id": "free-1", "free": True}, {"id": "bad id"}, {"id": ""}],
        provider="openrouter")
    assert added == ["good-1", "free-1"] and len(skipped) == 2
    models = config.load_models()
    assert models["good-1"] == {"free": False, "cost_rank": 1000, "provider": "openrouter"}
    assert models["free-1"] == {"free": True, "cost_rank": 0, "provider": "openrouter"}


def test_add_models_bulk_empty_no_write(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    added, skipped = config.add_models_bulk([{"id": "bad id"}], provider="p")
    assert added == [] and config.load_models() == {}  # nothing written


# ---- CLI command ------------------------------------------------------------

def test_cli_models_import_into_catalog(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    monkeypatch.setattr(providers, "list_models",
                        lambda *a, **k: [{"id": "a", "free": False}, {"id": "b", "free": True}])
    assert cli.main(["models", "import", "openrouter"]) == 0
    models = config.load_models()
    assert set(models) == {"a", "b"} and models["b"]["free"] is True
    assert config.load_pools() == {}  # catalog only — pools untouched


def test_cli_models_import_free_only_and_into_pool(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    monkeypatch.setattr(providers, "list_models",
                        lambda *a, **k: [{"id": "a", "free": False}, {"id": "b", "free": True}])
    assert cli.main(
        ["models", "import", "openrouter", "--free-only", "--into-pool", "freebies"]) == 0
    assert set(config.load_models()) == {"b"}          # free-only filtered
    assert config.load_pools()["freebies"] == ["b"]    # explicit opt-in pool


def test_cli_models_import_reports_failure(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")

    def _boom(*a, **k):
        raise urllib.error.URLError("nope")

    monkeypatch.setattr(providers, "list_models", _boom)
    assert cli.main(["models", "import", "openrouter"]) == 1
    assert "could not list models" in capsys.readouterr().err


# ---- web endpoint -----------------------------------------------------------

def _req(url, method="GET", token=None, body=None):
    data = json.dumps(body).encode() if body is not None else None
    headers = {"Content-Type": "application/json"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, data=data, headers=headers, method=method)
    try:
        r = urllib.request.urlopen(req, timeout=10)
        return r.status, r.read().decode()
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode()


def test_web_models_import_hot_reloads(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    monkeypatch.setattr(
        providers, "list_models",
        lambda *a, **k: [{"id": "x", "free": False}, {"id": "y:free", "free": True}])
    server = gateway.build_server(
        GatewayConfig(host="127.0.0.1", port=0, token="t", model_ids=[]), setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        st, body = _req(server.url + "/charon/models/import", "POST", token="t",
                        body={"provider": "openrouter"})
        assert st == 200 and json.loads(body)["added"] == 2
        # hot reload: both models now appear at /v1/models with no restart
        st, body = _req(server.url + "/v1/models", token="t")
        ids = {m["id"] for m in json.loads(body)["data"]}
        assert st == 200 and {"x", "y:free"} <= ids
    finally:
        server.shutdown()
