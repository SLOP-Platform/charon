"""Tests for the discover module — provider model discovery and cost-map building."""
from __future__ import annotations

import http.server
import json
import threading
from http.server import HTTPServer

from charon import providers
from charon.discover import (
    build_cost_map,
    discover_models,
    discover_provider,
    load_cost_map,
    save_cost_map,
)


def _mock_server(handler_class: type[http.server.BaseHTTPRequestHandler]) -> tuple[str, HTTPServer]:
    """Start a mock HTTP server on a random port.  Returns (base_url, server)."""
    srv = HTTPServer(("127.0.0.1", 0), handler_class)
    t = threading.Thread(target=srv.serve_forever, daemon=True)
    t.start()
    host, bound_port = srv.server_address[:2]
    if isinstance(host, bytes):
        host = host.decode()
    return f"http://{host}:{bound_port}", srv


class TestDiscoverProvider:
    def test_mock_success(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                body = json.dumps({
                    "object": "list",
                    "data": [
                        {"id": "gpt-4", "pricing": {"prompt": 0.03, "completion": 0.06}},
                        {"id": "gpt-3.5-turbo"},
                    ],
                }).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            result = discover_provider(base + "/v1", None)
            assert result is not None
            assert len(result) == 2
            assert result[0]["id"] == "gpt-4"
            assert result[0]["pricing"] == {"prompt": 0.03, "completion": 0.06}
            assert result[1]["id"] == "gpt-3.5-turbo"
        finally:
            srv.shutdown()

    def test_returns_none_on_http_error(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                body = b'{"error":"internal"}'
                self.send_response(500)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            assert discover_provider(base + "/v1", None) is None
        finally:
            srv.shutdown()

    def test_returns_none_on_timeout(self):
        def _raise_os_error(*a, **kw):  # noqa: ANN002, ANN003
            raise OSError("timed out")

        import charon.discover
        orig = charon.discover.urllib.request.urlopen
        charon.discover.urllib.request.urlopen = _raise_os_error
        try:
            assert discover_provider("http://127.0.0.1:1/v1", None, timeout=0.001) is None
        finally:
            charon.discover.urllib.request.urlopen = orig

    def test_returns_none_on_invalid_json(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                body = b"garbage not json"
                self.send_response(200)
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            assert discover_provider(base + "/v1", None) is None
        finally:
            srv.shutdown()

    def test_auth_header(self):
        captured: dict[str, str | None] = {}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                captured["auth"] = self.headers.get("Authorization")
                body = b'{"object":"list","data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            discover_provider(base + "/v1", "sk-test-key")
            assert captured["auth"] == "Bearer sk-test-key"
        finally:
            srv.shutdown()

    def test_auth_header_absent_when_no_key(self):
        captured: dict[str, str | None] = {}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                captured["auth"] = self.headers.get("Authorization")
                body = b'{"object":"list","data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            discover_provider(base + "/v1", None)
            assert captured.get("auth") is None
        finally:
            srv.shutdown()

    def test_strip_v1_false_appends_v1_models(self):
        captured: dict[str, str] = {}

        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                captured["path"] = self.path
                body = b'{"object":"list","data":[]}'
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            discover_provider(base, None, strip_v1=False)
            assert captured["path"] == "/v1/models"
        finally:
            srv.shutdown()

    def test_bare_list_response(self):
        class H(http.server.BaseHTTPRequestHandler):
            def log_message(self, *a):  # noqa: ANN002, ANN003
                pass

            def do_GET(self):  # noqa: N802
                body = json.dumps([{"id": "m1"}, "m2"]).encode()
                self.send_response(200)
                self.send_header("Content-Type", "application/json")
                self.send_header("Content-Length", str(len(body)))
                self.end_headers()
                self.wfile.write(body)

        base, srv = _mock_server(H)
        try:
            result = discover_provider(base + "/v1", None)
            assert result is not None
            assert len(result) == 2
            assert result[0]["id"] == "m1"
            assert result[1]["id"] == "m2"
        finally:
            srv.shutdown()


class TestBuildCostMap:
    def test_single_provider(self):
        discoveries = {
            "openai": [
                {"id": "gpt-4", "pricing": {"prompt": 0.03, "completion": 0.06}},
                {"id": "gpt-3.5-turbo", "pricing": {"prompt": 0.001, "completion": 0.002}},
                {"id": "dall-e-3"},
            ],
        }
        result = build_cost_map(discoveries)
        assert len(result) == 3
        assert set(result) == {"gpt-4", "gpt-3.5-turbo", "dall-e-3"}
        for mid in result:
            assert len(result[mid]["providers"]) == 1
            assert result[mid]["providers"][0]["provider"] == "openai"

    def test_cross_references_models(self):
        discoveries = {
            "openai": [{"id": "gpt-4", "pricing": {"prompt": 0.03, "completion": 0.06}}],
            "openrouter": [{"id": "gpt-4", "pricing": {"prompt": 0.025, "completion": 0.05}}],
        }
        result = build_cost_map(discoveries)
        assert len(result) == 1
        assert "gpt-4" in result
        providers_list = result["gpt-4"]["providers"]
        assert len(providers_list) == 2
        assert {p["provider"] for p in providers_list} == {"openai", "openrouter"}

    def test_free_detection_by_suffix(self):
        discoveries = {"openrouter": [{"id": "llama-3:free"}]}
        result = build_cost_map(discoveries)
        assert result["llama-3:free"]["providers"][0]["free"] is True

    def test_free_detection_by_zero_pricing(self):
        discoveries = {
            "openrouter": [{"id": "free-model", "pricing": {"prompt": 0, "completion": 0}}],
        }
        result = build_cost_map(discoveries)
        assert result["free-model"]["providers"][0]["free"] is True

    def test_pricing_extraction(self):
        discoveries = {
            "openai": [{"id": "gpt-4", "pricing": {"prompt": 0.03, "completion": 0.06}}],
        }
        result = build_cost_map(discoveries)
        assert result["gpt-4"]["providers"][0]["pricing"] == {"prompt": 0.03, "completion": 0.06}

    def test_pricing_absent(self):
        discoveries = {"openai": [{"id": "gpt-4"}]}
        result = build_cost_map(discoveries)
        assert "pricing" not in result["gpt-4"]["providers"][0]

    def test_skips_none_provider(self):
        discoveries = {
            "down": None,
            "openai": [{"id": "gpt-4"}],
        }
        result = build_cost_map(discoveries)
        assert "gpt-4" in result
        assert len(result["gpt-4"]["providers"]) == 1

    def test_case_insensitive_grouping(self):
        discoveries = {
            "a": [{"id": "GPT-4"}],
            "b": [{"id": "gpt-4"}],
        }
        result = build_cost_map(discoveries)
        assert len(result) == 1
        # first-seen case wins as the dict key
        key = next(iter(result))
        assert key == "GPT-4"
        assert len(result[key]["providers"]) == 2


class TestSaveLoadCostMap:
    def test_roundtrip(self, tmp_path):
        cost_map = {
            "gpt-4": {
                "providers": [
                    {"provider": "openai", "pricing": {"prompt": 0.03}, "free": False},
                ],
            },
        }
        save_cost_map(cost_map, config_dir=tmp_path)
        loaded = load_cost_map(config_dir=tmp_path)
        assert loaded == cost_map

    def test_missing_file_returns_empty(self, tmp_path):
        assert load_cost_map(config_dir=tmp_path / "nope") == {}

    def test_corrupt_file_returns_empty(self, tmp_path):
        p = tmp_path / "cost_map.json"
        p.write_text("garbage")
        assert load_cost_map(config_dir=tmp_path) == {}


class TestDiscoverModels:
    def test_parallel_queries_all_providers(self, monkeypatch, tmp_path):
        called: list[str] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            called.append(base_url)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "prov-a": providers.ProviderPreset("http://a.example/v1", strip_v1=True),
            "prov-b": providers.ProviderPreset("http://b.example/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        result = discover_models(timeout=5, config_dir=tmp_path)
        assert len(called) == 2
        assert "http://a.example/v1" in called
        assert "http://b.example/v1" in called
        assert "test-model" in result

    def test_skips_provider_without_base_url(self, monkeypatch, tmp_path):
        called: list[str] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            called.append(base_url)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {})
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {
            "no-base": {},
            "has-base": {"base_url": "http://ok.example/v1"},
        })
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)
        assert len(called) == 1
        assert "http://ok.example/v1" in called

    def test_env_key_takes_precedence_over_secrets(self, monkeypatch, tmp_path):
        key_used: list[str | None] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            key_used.append(api_key)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "prov-a": providers.ProviderPreset("http://a/v1", key_env="MY_KEY", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)
        monkeypatch.setenv("MY_KEY", "env-key-value")

        discover_models(timeout=5, config_dir=tmp_path)
        assert key_used == ["env-key-value"]

    def test_secrets_fallback_when_env_not_set(self, monkeypatch, tmp_path):
        key_used: list[str | None] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            key_used.append(api_key)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "prov-a": providers.ProviderPreset("http://a/v1", key_env="MY_KEY", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr(
            "charon.discover.secrets.load_secrets", lambda **kw: {"MY_KEY": "secret-value"},
        )
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)
        monkeypatch.delenv("MY_KEY", raising=False)

        discover_models(timeout=5, config_dir=tmp_path)
        assert key_used == ["secret-value"]

    def test_custom_provider_config_included(self, monkeypatch, tmp_path):
        called: list[str] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            called.append(base_url)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {})
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {
            "custom": {"base_url": "http://custom.example/v1", "strip_v1": False},
        })
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)
        assert "http://custom.example/v1" in called

    def test_preset_strip_v1_used(self, monkeypatch, tmp_path):
        called_strip: list[bool] = []

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):  # noqa: ANN001
            called_strip.append(strip_v1)
            return [{"id": "test-model"}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "prov-a": providers.ProviderPreset("http://a/v1", strip_v1=False),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)
        assert called_strip == [False]
