"""Setup phase — user-local gateway config (providers/models/pools) and the
custom-provider end-to-end path: add a provider + model, and the gateway resolves
a working route from the user config dir with NO hand-edited TOML.
"""
from __future__ import annotations

import os

import pytest

from charon import cli, config, gateway, secrets
from charon.config import SandboxPolicy, load_sandbox_policy


def test_add_provider_model_pool_and_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DK", "sk-deep")
    config.add_provider("deepseek", base_url="https://api.deepseek.com/v1", key_env="DK")
    config.add_model("deepseek-chat", provider="deepseek", upstream_model="deepseek-chat",
                     cost_rank=5)
    config.add_model("free-one", provider="deepseek", free=True, cost_rank=0)
    config.set_pool("auto", ["deepseek-chat", "free-one"])

    assert config.load_providers()["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
    assert config.load_models()["deepseek-chat"]["provider"] == "deepseek"
    assert config.load_pools()["auto"] == ["deepseek-chat", "free-one"]
    s = config.summary()
    assert s["providers"]["deepseek"]["key_set"] is True       # key present...
    assert "sk-deep" not in str(s)                              # ...but the value is NOT exposed


def test_invalid_names_rejected(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        config.add_provider("bad name")
    with pytest.raises(ValueError):
        config.set_pool("auto", ["bad id"])           # space in a member id
    with pytest.raises(ValueError):
        config.add_model("m")                          # neither provider nor upstream_base


def test_remove(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("p", base_url="http://x/v1")
    assert config.remove("provider", "p") is True
    assert config.remove("provider", "p") is False


def test_custom_provider_resolves_to_gateway_route(monkeypatch, tmp_path):
    """The whole point: `providers add` a custom provider + a model → the gateway
    builds a working route from ~/.charon with no TOML."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("DEEPSEEK_KEY", "sk-deep")
    config.add_provider("deepseek", base_url="https://api.deepseek.com/v1",
                        key_env="DEEPSEEK_KEY")
    config.add_model("deepseek-chat", provider="deepseek", upstream_model="deepseek-chat")
    cfg = gateway.load_config(state_dir=secrets.config_dir())
    r = cfg.routes["deepseek-chat"]
    assert r.upstream_base == "https://api.deepseek.com/v1"
    assert r.api_key == "sk-deep" and r.upstream_model == "deepseek-chat"


def test_setup_wizard_end_to_end(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    inputs = iter([
        "openrouter", "n", "gpt-4o", "", "n", "",      # provider 1: key, NO import, model (paid)
        "deepseek", "n", "deepseek-chat", "", "y", "",  # provider 2: key, NO import, model (free)
        "",                                        # finish providers
        "y", "auto",                               # build a pool named "auto"
    ])
    keys = iter(["sk-or", "sk-deep"])
    monkeypatch.setattr("builtins.input", lambda *a: next(inputs))
    import getpass
    monkeypatch.setattr(getpass, "getpass", lambda *a: next(keys))

    assert cli.main(["setup"]) == 0
    provs, models, pools = config.load_providers(), config.load_models(), config.load_pools()
    assert "openrouter" in provs and "deepseek" in provs
    assert "gpt-4o" in models and models["deepseek-chat"]["free"] is True
    assert pools["auto"] == ["gpt-4o", "deepseek-chat"]
    secs = secrets.load_secrets()
    assert secs["OPENROUTER_API_KEY"] == "sk-or" and secs["DEEPSEEK_API_KEY"] == "sk-deep"


def test_setup_no_tty_exits_gracefully(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))

    def _raise(*a):
        raise EOFError

    monkeypatch.setattr("builtins.input", _raise)
    assert cli.main(["setup"]) == 2


def test_reset_keeps_keys_by_default(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    secrets.set_secret("OPENROUTER_API_KEY", "sk-x")
    assert cli.main(["reset", "--yes"]) == 0
    assert config.load_providers() == {}                            # config wiped
    assert secrets.load_secrets()["OPENROUTER_API_KEY"] == "sk-x"   # keys kept


def test_reset_all_removes_keys(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    secrets.set_secret("OPENROUTER_API_KEY", "sk-x")
    assert cli.main(["reset", "--all", "--yes"]) == 0
    assert config.load_providers() == {} and secrets.load_secrets() == {}


def test_reset_nothing(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert cli.main(["reset", "--yes"]) == 0  # empty config dir → no-op, exit 0


def test_providers_add_custom_persists_provider(monkeypatch, tmp_path):
    """CLI: `providers add` a non-preset provider persists base_url+key_env to config
    AND stores the key — so it's usable immediately."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = cli.main(["providers", "add", "deepseek", "--base-url", "https://api.deepseek.com/v1",
                   "--key-env", "DEEPSEEK_KEY", "--key", "sk-deep"])
    assert rc == 0
    assert config.load_providers()["deepseek"]["base_url"] == "https://api.deepseek.com/v1"
    assert secrets.load_secrets()["DEEPSEEK_KEY"] == "sk-deep"
    os.environ.pop("DEEPSEEK_KEY", None)


# ----------------------------------------------- S1: sandbox policy (D013)

def test_sandbox_policy_default_is_hybrid():
    assert load_sandbox_policy({}) == SandboxPolicy.HYBRID


def test_sandbox_policy_reads_env_var():
    assert load_sandbox_policy({"CHARON_SANDBOX": "container"}) == SandboxPolicy.CONTAINER
    assert load_sandbox_policy({"CHARON_SANDBOX": "host"}) == SandboxPolicy.HOST
    assert load_sandbox_policy({"CHARON_SANDBOX": "hybrid"}) == SandboxPolicy.HYBRID


def test_sandbox_policy_case_insensitive():
    assert load_sandbox_policy({"CHARON_SANDBOX": "CONTAINER"}) == SandboxPolicy.CONTAINER
    assert load_sandbox_policy({"CHARON_SANDBOX": "HOST"}) == SandboxPolicy.HOST
    assert load_sandbox_policy({"CHARON_SANDBOX": "Hybrid"}) == SandboxPolicy.HYBRID


def test_sandbox_policy_invalid_value_falls_back_to_hybrid():
    assert load_sandbox_policy({"CHARON_SANDBOX": "bogus"}) == SandboxPolicy.HYBRID
    assert load_sandbox_policy({"CHARON_SANDBOX": ""}) == SandboxPolicy.HYBRID


# ── SR-5: pricing / cost visibility ───────────────────────────────

def test_model_with_pricing_yields_nonzero_cost(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_model("expensive", provider="test", cost_input=0.01, cost_output=0.05)
    m = config.load_models()["expensive"]
    assert m["cost_input"] == 0.01
    assert m["cost_output"] == 0.05
    cost = 100 * m["cost_input"] + 50 * m["cost_output"]
    assert cost > 0
    assert cost == 100 * 0.01 + 50 * 0.05


def test_unknown_pricing_flagged_in_summary(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_model("mystery", provider="unknown")
    config.add_model("priced", provider="openai", cost_input=0.01, cost_output=0.03)
    config.add_model("freebie", provider="openai", free=True)
    s = config.summary()
    assert "unknown_pricing" in s
    assert "mystery" in s["unknown_pricing"]
    assert "priced" not in s["unknown_pricing"]
    assert "freebie" not in s["unknown_pricing"]


def test_fallback_pricing_roundtrip(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_fallback_pricing(0.001, 0.002)
    fb = config.load_fallback_pricing()
    assert fb["cost_input"] == 0.001
    assert fb["cost_output"] == 0.002


def test_fallback_pricing_makes_unknown_cost_nonzero(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.set_fallback_pricing(0.005, 0.01)
    fb = config.load_fallback_pricing()
    assert fb["cost_input"] == 0.005
    assert fb["cost_output"] == 0.01
    cost = 100 * fb["cost_input"] + 50 * fb["cost_output"]
    assert cost > 0


def test_fallback_pricing_absent_returns_empty(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert config.load_fallback_pricing() == {}


def test_set_fallback_pricing_rejects_negative(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    with pytest.raises(ValueError):
        config.set_fallback_pricing(-0.01, 0.02)
    with pytest.raises(ValueError):
        config.set_fallback_pricing(0.01, -0.02)


def test_save_honors_config_dir_roundtrip(tmp_path):
    # _save must write to the SAME dir a matching _load reads from, for a
    # non-default config_dir (the discovery pricing-write path). Regression:
    # _save used to hardcode secrets.config_dir() and ignore config_dir.
    d = tmp_path / "alt-config"
    config._save("models.json", {"m": {"cost_input": 0.0000025}}, config_dir=d)
    assert (d / "models.json").exists()
    loaded = config.load_models(config_dir=d)
    assert loaded["m"]["cost_input"] == 0.0000025


def test_save_default_config_dir_unaffected(monkeypatch, tmp_path):
    # With no config_dir, _save still targets the default (CHARON_HOME) dir.
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config._save("models.json", {"m": {"cost_output": 0.00001}})
    assert config.load_models()["m"]["cost_output"] == 0.00001


# ── PROVIDER-PROBE-FIX: validation logic + skip_probe escape hatch ─────────

def test_validate_provider_key_models_ok_short_circuits_chat_probe():
    """FAIL-ON-REVERT (PROVIDER-PROBE-FIX): /models returns 200 + a parseable
    list → validate_provider_key returns valid=True WITHOUT the chat probe
    needing to succeed. The old code ran the chat probe with model="." and
    wrongly rejected valid keys when the upstream 400'd on the placeholder id.

    Must be RED if the fix is reverted: the chat probe's HTTPError(400) would
    trip the unconditional `return {valid: False, ...}` branch. Must be GREEN
    with the fix: the /models short-circuit returns valid=True first."""
    import urllib.error
    from unittest.mock import MagicMock, patch

    from charon.config import keyprobe as kp

    models_body = b'{"data": [{"id": "real-model-1"}, {"id": "real-model-2"}]}'

    class _ModelsResp:
        def read(self, *_a):
            return models_body

    def _fake_open(req, timeout=None):
        # /models → 200 + list. /chat/completions → HTTP 400 (provider rejects
        # model=".") — this is the case the bug used to mis-handle.
        path = req.selector or ""
        if path.endswith("/models"):
            return _ModelsResp()
        if path.endswith("/chat/completions"):
            raise urllib.error.HTTPError(
                url=path, code=400, msg="Bad Request", hdrs=None, fp=None)
        raise AssertionError(f"unexpected probe to {path!r}")

    opener = MagicMock()
    opener.open.side_effect = _fake_open
    with patch("urllib.request.build_opener", return_value=opener):
        result = kp.validate_provider_key("test", "https://api.example.com/v1", "sk-x")

    assert result["valid"] is True, f"expected valid=True, got {result!r}"
    assert result["models_count"] == 2
    # /models was reachable → the chat probe's 400 must NOT be reported as the
    # deciding signal.
    assert "HTTP 400" not in result["message"]


def test_validate_provider_key_models_unreachable_still_rejects_on_chat_400():
    """When /models is unreachable AND the chat probe returns a non-401/403
    HTTPError, the key is rejected — the fix is NOT a free pass."""
    import urllib.error
    from unittest.mock import MagicMock, patch

    from charon.config import keyprobe as kp

    def _fake_open(req, timeout=None):
        # /models → unreachable (simulate). /chat → 400.
        path = req.selector or ""
        if path.endswith("/models"):
            raise ConnectionError("simulated")
        if path.endswith("/chat/completions"):
            raise urllib.error.HTTPError(
                url=path, code=400, msg="Bad Request", hdrs=None, fp=None)
        raise AssertionError(f"unexpected probe to {path!r}")

    opener = MagicMock()
    opener.open.side_effect = _fake_open
    with patch("urllib.request.build_opener", return_value=opener):
        result = kp.validate_provider_key("test", "https://api.example.com/v1", "sk-x")

    assert result["valid"] is False
    assert "HTTP 400" in result["message"]


def test_validate_provider_key_skip_probe_returns_skipped_without_network():
    """skip_probe=True → valid=True, no HTTP calls, 'skipped' surface flag set
    so the caller/UI can show a 'not validated' state instead of silence."""
    from unittest.mock import MagicMock, patch

    from charon.config import keyprobe as kp

    opener = MagicMock()
    with patch("urllib.request.build_opener", return_value=opener) as bo:
        result = kp.validate_provider_key(
            "test", "https://api.example.com/v1", "sk-x", skip_probe=True)

    assert result["valid"] is True
    assert result.get("skipped") is True
    assert "skipped" in result["message"].lower()
    # No HTTP work done.
    assert bo.call_count == 0  # build_opener was never called
    assert opener.open.call_count == 0


def test_providers_gateway_action_skip_probe_end_to_end(monkeypatch, tmp_path):
    """The /charon/providers web-setup action honours skip_probe=True: the
    provider is persisted unvalidated, no probe network call is made, and the
    response marks the probe as skipped."""
    from unittest.mock import patch

    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("BADPROBE_KEY", raising=False)

    cfg = gateway.load_config(state_dir=tmp_path)
    import dataclasses
    cfg = dataclasses.replace(cfg, token="t", port=0)
    server = gateway.build_server(cfg, setup_dir=tmp_path)
    server.serve_in_thread()
    try:
        base = server.url
        # Hand-roll the POST so we don't depend on the test_console_provider_mgmt
        # _req helper (owned by that ticket's tests).
        import json as _json
        import urllib.request

        body = _json.dumps({
            "name": "skipprov",
            "base_url": "https://api.example.com/v1",
            "key_env": "BADPROBE_KEY",
            "key": "sk-dead",
            "skip_probe": True,
        }).encode()
        req = urllib.request.Request(
            base + "/charon/providers", data=body, method="POST")
        req.add_header("Content-Type", "application/json")
        req.add_header("Authorization", "Bearer t")
        # Patch the re-export in the config package (where gateway.py's handler
        # looks it up) so we can assert the call was made with skip_probe=True.
        with patch("charon.config.validate_provider_key") as vpk:
            vpk.return_value = {
                "valid": True, "message": "probe skipped",
                "models_count": 0, "skipped": True}
            resp = urllib.request.urlopen(req, timeout=10)
            data = _json.loads(resp.read().decode("utf-8"))

        assert resp.status == 200, f"expected 200, got {resp.status}: {data!r}"
        assert data["ok"] is True
        assert data["provider"] == "skipprov"
        assert data["probe"] is not None
        assert data["probe"].get("skipped") is True
        assert vpk.call_count == 1, \
            f"expected one validate_provider_key call, got {vpk.call_count}"
        assert vpk.call_args.kwargs.get("skip_probe") is True, \
            f"expected skip_probe=True kwarg, got {vpk.call_args!r}"
    finally:
        server.shutdown()
