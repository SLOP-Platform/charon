"""Setup phase — user-local gateway config (providers/models/pools) and the
custom-provider end-to-end path: add a provider + model, and the gateway resolves
a working route from the user config dir with NO hand-edited TOML.
"""
from __future__ import annotations

import os

import pytest

from charon import cli, config, gateway, secrets


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


# ------------------------------------------- D013: SandboxPolicy (S1)

from charon.config import SandboxPolicy


def test_sandbox_policy_default_is_hybrid(monkeypatch) -> None:
    monkeypatch.delenv("CHARON_SANDBOX", raising=False)
    assert SandboxPolicy.from_env({}) is SandboxPolicy.hybrid


def test_sandbox_policy_from_env_all_values(monkeypatch) -> None:
    for val in ("hybrid", "container", "host"):
        monkeypatch.setenv("CHARON_SANDBOX", val)
        assert SandboxPolicy.from_env() is SandboxPolicy(val)


def test_sandbox_policy_from_env_invalid_raises(monkeypatch) -> None:
    monkeypatch.setenv("CHARON_SANDBOX", "nope")
    with pytest.raises(ValueError, match="CHARON_SANDBOX"):
        SandboxPolicy.from_env()


def test_sandbox_policy_from_toml_value() -> None:
    assert SandboxPolicy.from_toml_value("hybrid") is SandboxPolicy.hybrid
    assert SandboxPolicy.from_toml_value("container") is SandboxPolicy.container
    assert SandboxPolicy.from_toml_value("host") is SandboxPolicy.host
    with pytest.raises(ValueError, match="sandbox="):
        SandboxPolicy.from_toml_value("bad")


def test_sandbox_policy_enum_values() -> None:
    assert SandboxPolicy.hybrid.value == "hybrid"
    assert SandboxPolicy.container.value == "container"
    assert SandboxPolicy.host.value == "host"


def test_cli_run_sandbox_flag_sets_env(monkeypatch, tmp_path) -> None:
    """CLI: --sandbox container sets CHARON_SANDBOX before the run call."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # monkeypatch.delenv is a no-op (no cleanup registered) when the var is absent,
    # so we guard with an explicit try/finally to clean up the direct os.environ
    # mutation the CLI makes.
    _prev = os.environ.pop("CHARON_SANDBOX", None)
    try:
        captured: list[str] = []
        import charon.api as _api

        def _spy(*a, **kw):
            captured.append(os.environ.get("CHARON_SANDBOX", "UNSET"))
            raise RuntimeError("short-circuit")

        monkeypatch.setattr(_api, "run_task", _spy)
        rc = cli.main(["run", "--goal", "x", "--accept", "true", "--sandbox", "container"])
        assert rc == 2  # RuntimeError → caught as RuntimeError → exit 2
        assert captured and captured[0] == "container"
    finally:
        if _prev is None:
            os.environ.pop("CHARON_SANDBOX", None)
        else:
            os.environ["CHARON_SANDBOX"] = _prev


def test_cli_run_sandbox_invalid_exits_2(monkeypatch, tmp_path) -> None:
    # argparse validates choices and calls sys.exit(2) directly.
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    import pytest as _pytest
    with _pytest.raises(SystemExit) as exc:
        cli.main(["run", "--goal", "x", "--accept", "true", "--sandbox", "bad"])
    assert exc.value.code == 2


def test_cli_doctor_shows_sandbox(monkeypatch, tmp_path) -> None:
    import json as _json
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.delenv("CHARON_SANDBOX", raising=False)
    from charon.doctor import DoctorReport
    import charon.cli as _cli

    def _fake_probe(cmd):
        rep = DoctorReport()
        rep.spawned = True
        rep.initialized = True
        return rep

    # patch the reference that cli already bound via "from .doctor import probe"
    monkeypatch.setattr(_cli, "probe", _fake_probe)
    output: list[str] = []
    monkeypatch.setattr("builtins.print", lambda *a, **kw: output.append(str(a[0])))
    rc = cli.main(["doctor"])
    assert rc == 0
    combined = "\n".join(output)
    data = _json.loads(combined)
    assert "sandbox" in data
    assert data["sandbox"]["policy"] == "hybrid"
    assert "ceiling" in data["sandbox"]
