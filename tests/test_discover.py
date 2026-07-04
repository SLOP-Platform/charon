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
    discover_openrouter,
    discover_provider,
    fuzzy_match_model_id,
    import_openrouter_models,
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


class TestOpenRouterImport:
    def test_discover_openrouter_parses_list(self, monkeypatch, tmp_path):
        raw = json.dumps([
            {"id": "openai/gpt-4o", "pricing": {"prompt": "5", "completion": "15"}},
            {"id": "anthropic/claude-sonnet", "pricing": {"prompt": "3", "completion": "15"}},
        ]).encode()
        monkeypatch.setattr("urllib.request.urlopen", lambda req, timeout: _FakeResp(200, raw))
        result = discover_openrouter()
        assert result is not None
        assert len(result) == 2

    def test_discover_openrouter_returns_none_on_error(self, monkeypatch):
        def _fail(*a, **kw):
            _raise(_fake_urlerr(500))
        monkeypatch.setattr("urllib.request.urlopen", _fail)
        assert discover_openrouter() is None

    def test_fuzzy_match_exact(self):
        assert fuzzy_match_model_id("gpt-4o", ["gpt-4o", "claude"]) == ("gpt-4o", 1)

    def test_fuzzy_match_case_insensitive(self):
        assert fuzzy_match_model_id("GPT-4O", ["gpt-4o"]) == ("gpt-4o", 1)

    def test_fuzzy_match_strips_prefix(self):
        assert fuzzy_match_model_id("openai/gpt-4o", ["gpt-4o"]) == ("gpt-4o", 2)

    def test_fuzzy_match_no_match(self):
        assert fuzzy_match_model_id("unknown/model", ["gpt-4o"]) == (None, 0)

    def test_fuzzy_match_alias_map(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        alias_file = tmp_path / "model_aliases.json"
        alias_file.write_text('{"custom/id": "gpt-4o"}')
        assert fuzzy_match_model_id("custom/id", ["gpt-4o"], config_dir=tmp_path) == ("gpt-4o", 3)

    def test_import_openrouter_dry_run(self, monkeypatch, tmp_path):
        raw = json.dumps([
            {"id": "openai/gpt-4o", "pricing": {"prompt": "5", "completion": "15"}},
            {"id": "gpt-4o", "pricing": {"prompt": "5", "completion": "15"}},
            {"id": "unknown/model-zzz", "pricing": {"prompt": "1", "completion": "1"}},
        ]).encode()
        monkeypatch.setattr("charon.discover.urllib.request.urlopen",
                            lambda req, timeout: _FakeResp(200, raw))
        monkeypatch.setattr("charon.discover.config.load_models",
                            lambda **kw: {"gpt-4o": {}, "claude": {}})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)
        result = import_openrouter_models(dry_run=True, config_dir=tmp_path)
        assert result["imported"] == 1      # gpt-4o → gpt-4o (exact, stage 1)
        assert result["fuzzy_review"] == 1  # openai/gpt-4o → gpt-4o (prefix, stage 2)
        assert result["new"] == 1           # unknown/model-zzz → no match

    def test_import_openrouter_writes_review(self, monkeypatch, tmp_path):
        raw = json.dumps([
            {"id": "brand-new-model", "pricing": {"prompt": "2", "completion": "8"}},
        ]).encode()
        monkeypatch.setattr("charon.discover.urllib.request.urlopen",
                            lambda req, timeout: _FakeResp(200, raw))
        monkeypatch.setattr("charon.discover.config.load_models", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)
        result = import_openrouter_models(dry_run=False, config_dir=tmp_path)
        assert result["new"] == 1
        assert result["imported"] == 0
        review_file = tmp_path / "discover_review.json"
        assert review_file.exists()
        review = json.loads(review_file.read_text())
        assert "brand-new-model" in review


def _FakeResp(code, body_bytes):
    class R:
        def read(self):
            return body_bytes
    return R()


def _raise(exc):
    raise exc


def _fake_urlerr(code):
    class E(Exception):
        pass
    return E("error")


# ── SR-5: pricing persistence from discovery ──────────────────────

class TestDiscoverPricingPersistence:
    def test_discover_updates_model_pricing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("gpt-4o", provider="openai")

        # OpenRouter quotes pricing PER TOKEN (e.g. "0.0000025" == $2.50/1M).
        # The canonical stored value is that raw per-token float — NO /1e6 scaling.
        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [
                {"id": "gpt-4o",
                 "pricing": {"prompt": "0.0000025", "completion": "0.00001"}},
            ]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)

        models = config.load_models(config_dir=tmp_path)
        assert "gpt-4o" in models
        # Stored verbatim as per-token USD — the exact figure OpenRouter sent.
        assert models["gpt-4o"].get("cost_input") == 0.0000025
        assert models["gpt-4o"].get("cost_output") == 0.00001
        assert models["gpt-4o"].get("priced_by") == "discovery"

    def test_discover_no_match_skips_pricing(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("existing-model", provider="openai")

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [
                {"id": "unrelated-model", "pricing": {"prompt": "1", "completion": "2"}},
            ]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)

        models = config.load_models(config_dir=tmp_path)
        assert "cost_input" not in models["existing-model"]
        assert "cost_output" not in models["existing-model"]

    def test_discover_preserves_existing_pricing_on_absent(self, monkeypatch, tmp_path):
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("gpt-4o", provider="openai", cost_input=0.001)

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [
                {"id": "gpt-4o"},
            ]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)

        models = config.load_models(config_dir=tmp_path)
        assert models["gpt-4o"].get("cost_input") == 0.001
        assert "cost_output" not in models["gpt-4o"]

    def test_operator_price_survives_discovery(self, monkeypatch, tmp_path):
        # An operator hand-set price (no discovery marker) must NOT be clobbered
        # when a discovery reports a different price for the same model.
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("gpt-4o", provider="openai",
                         cost_input=0.00009, cost_output=0.00042)

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [
                {"id": "gpt-4o",
                 "pricing": {"prompt": "0.0000025", "completion": "0.00001"}},
            ]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)

        models = config.load_models(config_dir=tmp_path)
        # Operator figures preserved; not overwritten by discovery.
        assert models["gpt-4o"].get("cost_input") == 0.00009
        assert models["gpt-4o"].get("cost_output") == 0.00042
        assert models["gpt-4o"].get("priced_by") != "discovery"

    def test_discovery_refreshes_its_own_earlier_price(self, monkeypatch, tmp_path):
        # A price previously written BY discovery (carries the marker) may be
        # refreshed on a subsequent discovery — only operator prices are frozen.
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("gpt-4o", provider="openai")

        prices = {"prompt": "0.0000025", "completion": "0.00001"}

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [{"id": "gpt-4o", "pricing": dict(prices)}]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)
        assert config.load_models(config_dir=tmp_path)["gpt-4o"]["cost_input"] == 0.0000025

        prices["prompt"] = "0.000003"  # upstream price change
        discover_models(timeout=5, config_dir=tmp_path)
        refreshed = config.load_models(config_dir=tmp_path)["gpt-4o"]
        assert refreshed["cost_input"] == 0.000003
        assert refreshed["priced_by"] == "discovery"

    def test_discovery_rejects_nonfinite_and_negative(self, monkeypatch, tmp_path):
        # NaN / inf / negative pricing must be skipped, never persisted.
        monkeypatch.setenv("CHARON_HOME", str(tmp_path))
        from charon import config
        config.add_model("m-nan", provider="openai")
        config.add_model("m-inf", provider="openai")
        config.add_model("m-neg", provider="openai")

        def _fake_discover(base_url, api_key, strip_v1=True, timeout=10):
            return [
                {"id": "m-nan", "pricing": {"prompt": "nan", "completion": "0.00001"}},
                {"id": "m-inf", "pricing": {"prompt": "inf", "completion": "0.00001"}},
                {"id": "m-neg", "pricing": {"prompt": "-5", "completion": "0.00001"}},
            ]

        monkeypatch.setattr("charon.discover.discover_provider", _fake_discover)
        monkeypatch.setattr("charon.discover.providers.PRESETS", {
            "openai": providers.ProviderPreset("http://openai/v1", strip_v1=True),
        })
        monkeypatch.setattr("charon.discover.config.load_providers", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.load_secrets", lambda **kw: {})
        monkeypatch.setattr("charon.discover.secrets.config_dir", lambda **kw: tmp_path)

        discover_models(timeout=5, config_dir=tmp_path)

        models = config.load_models(config_dir=tmp_path)
        # Bad prompt values rejected; the valid completion still lands.
        for mid in ("m-nan", "m-inf", "m-neg"):
            assert "cost_input" not in models[mid]
            assert models[mid].get("cost_output") == 0.00001
