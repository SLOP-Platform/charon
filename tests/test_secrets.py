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
    # Stored against the PROVIDER, never the shared env-var name (KEY-EXFIL FIX).
    assert secrets.load_secrets()["provider:openrouter"] == "sk-xyz"
    assert "OPENROUTER_API_KEY" not in secrets.load_secrets()
    assert secrets.get_provider_key(
        "openrouter", key_env="OPENROUTER_API_KEY",
        base_url="https://openrouter.ai/api/v1") == "sk-xyz"
    out = capsys.readouterr()
    assert "sk-xyz" not in out.out and "sk-xyz" not in out.err  # never printed (stdout or stderr)


def test_set_secret_rejects_bad_key_env(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    import pytest
    for bad in ("", "BAD=NAME", "has space", "x\ny"):
        with pytest.raises(ValueError):
            secrets.set_secret(bad, "v")


def test_apply_to_env_skips_sensitive_and_malformed(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    # write a hostile secrets.json directly (simulating a tampered file)
    (tmp_path / "secrets.json").write_text(
        '{"LD_PRELOAD": "/evil.so", "PATH": "/evil", "bad name": "x", "GOOD_KEY": "ok"}')
    for v in ("LD_PRELOAD", "GOOD_KEY"):
        monkeypatch.delenv(v, raising=False)
    secrets.apply_to_env()
    try:
        assert os.environ.get("GOOD_KEY") == "ok"            # normal key loads
        assert "LD_PRELOAD" not in os.environ                # loader-sensitive skipped
        assert "bad name" not in os.environ                  # malformed name skipped
    finally:
        os.environ.pop("GOOD_KEY", None)


def test_providers_test_never_sends_key(monkeypatch, tmp_path):
    import http.server
    import socketserver
    import threading
    seen: dict = {}

    class H(http.server.BaseHTTPRequestHandler):
        def log_message(self, *a):
            pass

        def do_GET(self):
            seen["auth"] = self.headers.get("Authorization")
            self.send_response(200)
            self.send_header("Content-Length", "2")
            self.end_headers()
            self.wfile.write(b"{}")

    class T(socketserver.ThreadingMixIn, http.server.HTTPServer):
        daemon_threads = True
        allow_reuse_address = True

    srv = T(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    base = f"http://127.0.0.1:{srv.server_address[1]}/v1"
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setenv("OPENROUTER_API_KEY", "sk-should-not-leave")
    try:
        rc = cli.main(["providers", "test", "openrouter", "--base-url", base])
        assert rc == 0
        assert seen.get("auth") is None  # the key is NEVER sent on a base probe
    finally:
        srv.shutdown()


def test_providers_test_rejects_non_http_scheme(monkeypatch, tmp_path):
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    assert cli.main(["providers", "test", "custom", "--base-url", "file:///etc/passwd"]) == 2


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
    assert rc == 0 and secrets.load_secrets()["provider:mygw"] == "secret"
