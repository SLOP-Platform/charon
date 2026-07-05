"""SETUP-KEY-UX — validate the provider key at setup + stop the blind key input.

Covers:
1. Masked confirmation echo (length + last 4 chars) — the "confirm path"
2. Completion probe triggered after key storage in setup
3. Auth failure surfaced as a WARNING on stderr (not silent)
4. Successful probe prints validated
5. No full key written to stdout or stderr
6. providers add: masked confirmation on the stored key
"""

from __future__ import annotations

from charon import cli, config


def _drive_setup(monkeypatch, inputs, keys=()):
    """Feed a fixed script to ``input`` and ``getpass`` and run the wizard."""
    it_in = iter(inputs)
    it_key = iter(keys)
    monkeypatch.setattr("builtins.input", lambda *a: next(it_in))
    import getpass
    monkeypatch.setattr(getpass, "getpass", lambda *a: next(it_key))
    return cli.main(["setup"])


# ---------- Masked confirmation echo (length + last 4 chars) — the "confirm path"

def test_setup_key_echoes_masked_confirmation(monkeypatch, tmp_path, capsys):
    """Storing a key echoes masked confirmation (length + last 4); full key never on stdout."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key", lambda *a: None)
    key = "sk-abcdefghijklmnopqrstuvwxyz-1234567890"
    rc = _drive_setup(monkeypatch,
                      ["openrouter", "n", "", ""],
                      keys=[key])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(40 chars, ends in ...7890)" in out
    assert key not in out


def test_setup_key_short_echoes_full_in_quotes(monkeypatch, tmp_path, capsys):
    """A key with <= 4 chars echoes the full value in quotes (safe, not secret)."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key", lambda *a: None)
    rc = _drive_setup(monkeypatch,
                      ["openrouter", "n", "", ""],
                      keys=["abc"])
    out = capsys.readouterr().out
    assert rc == 0
    assert "(3 chars, ends in 'abc')" in out


def test_setup_key_blank_echoes_nothing(monkeypatch, tmp_path, capsys):
    """A blank key (user skips entry) emits no masked echo and no 'key stored'."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    rc = _drive_setup(monkeypatch,
                      ["openrouter", "", "", ""],
                      keys=[""])
    out = capsys.readouterr().out
    assert rc == 0
    assert "chars, ends in" not in out
    assert "key stored" not in out


# ---------- Completion probe triggered after key storage

def test_setup_triggers_completion_probe(monkeypatch, tmp_path):
    """Storing a key triggers a completion probe with the correct api_key."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    probes: list = []
    def _record(preset, api_key):
        probes.append(api_key)
        return None
    monkeypatch.setattr(cli, "_probe_key", _record)
    key = "sk-probe-test-key"
    _drive_setup(monkeypatch,
                 ["openrouter", "n", "", ""],
                 keys=[key])
    assert len(probes) == 1
    assert probes[0] == key


def test_setup_does_not_probe_when_key_blank(monkeypatch, tmp_path):
    """When the user enters a blank key, no probe is triggered."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    probes: list = []
    monkeypatch.setattr(cli, "_probe_key", lambda *a: probes.append(1) or None)
    _drive_setup(monkeypatch, ["openrouter", "", "", ""], keys=[""])
    assert len(probes) == 0


# ---------- Auth failure surfaced as WARNING (not silent success)

def test_auth_failure_surfaced_as_warning(monkeypatch, tmp_path, capsys):
    """A probe returning 'key rejected' prints WARNING to stderr."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key",
                        lambda *a: "HTTP 401: key rejected")
    key = "sk-bad-key-12345"
    _drive_setup(monkeypatch,
                 ["openrouter", "n", "", ""],
                 keys=[key])
    cap = capsys.readouterr()
    assert "WARNING: key check failed" in cap.err
    assert "key rejected" in cap.err


def test_network_error_surfaced_as_warning(monkeypatch, tmp_path, capsys):
    """A network-level probe failure is also surfaced as a WARNING on stderr."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key",
                        lambda *a: "unreachable — timeout")
    key = "sk-net-error-key"
    _drive_setup(monkeypatch,
                 ["openrouter", "n", "", ""],
                 keys=[key])
    cap = capsys.readouterr()
    assert "WARNING: key check failed" in cap.err
    assert "unreachable" in cap.err


def test_successful_probe_prints_validated(monkeypatch, tmp_path, capsys):
    """A successful probe prints 'key validated' and no WARNING."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key", lambda *a: None)
    key = "sk-valid-key-99"
    _drive_setup(monkeypatch,
                 ["openrouter", "n", "", ""],
                 keys=[key])
    cap = capsys.readouterr()
    assert "key validated" in cap.out
    assert "WARNING" not in cap.err


# ---------- No full key written to logs

def test_no_full_key_in_setup_output(monkeypatch, tmp_path, capsys):
    """The full key must never appear on stdout or stderr during setup."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    monkeypatch.setattr(cli, "_probe_key", lambda *a: None)
    key = "sk-very-secret-key-do-not-leak-abc123"
    _drive_setup(monkeypatch,
                 ["openrouter", "n", "", ""],
                 keys=[key])
    cap = capsys.readouterr()
    assert key not in cap.out
    assert key not in cap.err


# ---------- providers add: masked confirmation echo

def test_providers_add_echoes_masked_confirmation(monkeypatch, tmp_path, capsys):
    """providers add (interactive getpass) echoes masked confirmation and never
    prints the full key."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    key = "sk-provider-add-key-xyz"
    keys_iter = iter([key])
    import getpass
    monkeypatch.setattr(getpass, "getpass", lambda *a: next(keys_iter))
    rc = cli.main(["providers", "add", "openrouter"])
    assert rc == 0
    out = capsys.readouterr().out
    assert f"({len(key)} chars, ends in" in out
    assert key not in out


def test_providers_add_blank_key_no_mask(monkeypatch, tmp_path, capsys):
    """Blank key entry in providers add shows no mask and returns non-zero."""
    monkeypatch.setenv("CHARON_HOME", str(tmp_path))
    config.add_provider("openrouter", key_env="OPENROUTER_API_KEY")
    import getpass
    monkeypatch.setattr(getpass, "getpass", lambda *a: "")
    rc = cli.main(["providers", "add", "openrouter"])
    assert rc == 2
    out = capsys.readouterr().out
    assert "chars, ends in" not in out
