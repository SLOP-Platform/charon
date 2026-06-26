"""P3.5 — user-local secret storage + the `charon providers` setup CLI.

Keys are stored 0600 outside the repo, loaded into env without overriding an
explicit var, and NEVER echoed.
"""
from __future__ import annotations

import os
import stat

from charon import cli, secrets


def test_set_and_load_secret(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    p = secrets.set_secret("OPENROUTER_API_KEY", "sk-abc")
    assert p == tmp_path / "secrets.json"
    assert secrets.load_secrets()["OPENROUTER_API_KEY"] == "sk-abc"
    if os.name != "nt":  # 0600 on POSIX
        assert stat.S_IMODE(p.stat().st_mode) == 0o600


def test_apply_to_env_does_not_override_explicit(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    secrets.set_secret("CHARON_TEST_KEY", "stored")
    try:
        monkeypatch.setenv("CHARON_TEST_KEY", "explicit")
        secrets.apply_to_env()
        assert os.environ["CHARON_TEST_KEY"] == "explicit"  # explicit env wins
        monkeypatch.delenv("CHARON_TEST_KEY")
        secrets.apply_to_env()
        assert os.environ["CHARON_TEST_KEY"] == "stored"    # else the stored value loads
    finally:
        os.environ.pop("CHARON_TEST_KEY", None)


def test_providers_add_stores_key_without_echo(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert cli.main(["providers", "add", "openrouter", "--key", "sk-xyz"]) == 0
    assert secrets.load_secrets()["OPENROUTER_API_KEY"] == "sk-xyz"
    assert "sk-xyz" not in capsys.readouterr().out  # key is never printed


def test_providers_list_reports_set_and_missing(monkeypatch, tmp_path, capsys):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    cli.main(["providers", "add", "openrouter", "--key", "k"])
    capsys.readouterr()
    cli.main(["providers", "list"])
    out = capsys.readouterr().out
    assert "openrouter" in out and "key SET" in out and "MISSING" in out


def test_providers_add_unknown_without_base_url_errors(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert cli.main(["providers", "add", "totally-unknown"]) == 2


def test_providers_add_custom_with_base_url(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = cli.main(["providers", "add", "mygw", "--base-url", "http://localhost:9/v1",
                   "--key-env", "MYGW_KEY", "--key", "secret"])
    assert rc == 0 and secrets.load_secrets()["MYGW_KEY"] == "secret"
