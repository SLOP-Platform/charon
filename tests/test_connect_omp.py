"""CONNECT-OMP-WSL — fix omp config schema + WSL install routing.

Tests: omp writer emits the OHMYPI-ASSESS-confirmed schema; WSL detection routes
``--install`` to a native manager and never to a Windows-interop binary; clear
actionable error when native install is unavailable; token never in stdout.
"""
from __future__ import annotations

import platform
from pathlib import Path

import pytest

import charon.connect as connect
from charon.connect import (
    Wiring,
    _install_omp,
    _is_wsl_interop,
    _write_omp,
    detect_env,
)


# ----------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    monkeypatch.delenv("WSL_DISTRO_NAME", raising=False)
    return tmp_path


def _make_wiring(**kw: object) -> Wiring:
    defaults = {
        "base_url": "http://127.0.0.1:8080/v1",
        "token": "test-token",
        "model": "test-model",
        "config_path": Path("/tmp/test-models.yml"),
    }
    defaults.update(kw)
    return Wiring(**defaults)  # type: ignore[arg-type]


def _mock_which(mapping: dict[str, str | None]) -> object:
    """Return a ``shutil.which`` replacement that looks up ``mapping``."""
    def _f(name: str, *a: object, **kw: object) -> str | None:
        return mapping.get(name)
    return _f


def _mock_wsl(monkeypatch: pytest.MonkeyPatch, is_wsl: bool = True) -> None:
    """Mock platform to report WSL (or not)."""
    if is_wsl:

        class _WSLUname:
            system = "Linux"
            release = "5.15.146.1-microsoft-standard-WSL2"

        monkeypatch.setattr(platform, "uname", lambda: _WSLUname)
        monkeypatch.setenv("WSL_DISTRO_NAME", "")
    else:

        class _LinuxUname:
            system = "Linux"
            release = "6.8.0-45-generic"

        monkeypatch.setattr(platform, "uname", lambda: _LinuxUname)


# --------------------------------------------------- OHMYPI-ASSESS schema
def test_omp_schema_matches_ohmypi_assess(_home: Path) -> None:
    w = Wiring(base_url="http://127.0.0.1:8080/v1", token="test-token",
               model="test-model",
               config_path=_home / ".omp" / "agent" / "models.yml")
    _write_omp(w)
    text = (_home / ".omp" / "agent" / "models.yml").read_text()
    assert "charon:" in text
    assert "provider:" in text
    assert 'openai-compatible' in text
    assert "base_url:" in text
    assert 'http://127.0.0.1:8080/v1' in text
    assert "api_key:" in text
    assert 'test-token' in text
    assert "model:" in text
    assert 'test-model' in text


def test_omp_writer_preserves_existing_entries(_home: Path) -> None:
    config_path = _home / ".omp" / "agent" / "models.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("other:\n  provider: anthropic\n  model: claude\n")
    w = _make_wiring(config_path=config_path)
    _write_omp(w)
    text = config_path.read_text()
    assert "other:" in text
    assert "anthropic" in text
    assert "claude" in text
    assert "charon:" in text


def test_omp_writer_idempotent(_home: Path) -> None:
    config_path = _home / ".omp" / "agent" / "models.yml"
    config_path.parent.mkdir(parents=True, exist_ok=True)
    config_path.write_text("legacy:\n  keep: true\n")
    w = _make_wiring(config_path=config_path)
    _write_omp(w)
    first = config_path.read_text()
    _write_omp(w)
    second = config_path.read_text()
    assert first == second
    # charon block appears exactly once
    assert first.count("charon:") == 1


# -------------------------------------------------------- WSL install routing
def test_wsl_native_bun_preferred(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/usr/local/bin/bun",
                                     "npm": "/mnt/c/Program Files/nodejs/npm.exe",
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    assert env.is_wsl is True
    cmd = _install_omp(env)
    assert cmd is not None
    assert "bun install -g @oh-my-pi/pi-coding-agent" in cmd
    assert "unzip" not in cmd  # unzip already present


def test_wsl_native_npm_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": None,
                                     "npm": "/usr/bin/npm",
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    assert env.is_wsl is True
    cmd = _install_omp(env)
    assert cmd is not None
    assert "npm install -g @oh-my-pi/pi-coding-agent" in cmd


def test_wsl_windows_interop_bun_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/mnt/c/Users/u/.bun/bin/bun.exe",
                                     "npm": "/mnt/c/Program Files/nodejs/npm.exe",
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    assert env.is_wsl is True
    cmd = _install_omp(env)
    assert cmd is None  # no native bun or npm → fail rather than use Windows interop


def test_wsl_windows_interop_npm_also_rejected(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": None,
                                     "npm": "/mnt/c/Program Files/nodejs/npm.exe",
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    cmd = _install_omp(env)
    assert cmd is None


def test_wsl_missing_unzip_includes_prereq(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/usr/local/bin/bun",
                                     "npm": None,
                                     "unzip": None,
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    cmd = _install_omp(env)
    assert cmd is not None
    assert "sudo apt-get install -y unzip && " in cmd
    assert "bun install -g @oh-my-pi/pi-coding-agent" in cmd


def test_wsl_unzip_present_no_prereq(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/usr/local/bin/bun",
                                     "npm": None,
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    cmd = _install_omp(env)
    assert cmd is not None
    assert "unzip" not in cmd


def test_wsl_no_native_tools_prints_actionable(monkeypatch: pytest.MonkeyPatch,
                                                capsys: pytest.CaptureFixture[str],
                                                _home: Path) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: ["model-x"])
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/mnt/c/Users/u/.bun/bin/bun.exe",
                                     "npm": "/mnt/c/Program Files/nodejs/npm.exe",
                                     "unzip": None,
                                     "omp": None,  # omp binary not found
                                     "brew": None, "pip": None, "pip3": None}))
    rc = connect.run_connect(client="omp", runner=connect._shell_install)
    assert rc == 0  # config still written, just install skipped
    err = capsys.readouterr().err
    assert "requires a native WSL bun" in err
    assert "curl -fsSL https://bun.sh/install | bash" in err
    assert "sudo apt-get install -y unzip" in err


# ------------------------------------------------- non-WSL install unchanged
def test_non_wsl_linux_install_unchanged(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=False)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/usr/local/bin/bun",
                                     "npm": "/usr/bin/npm",
                                     "unzip": "/usr/bin/unzip",
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    assert env.is_wsl is False
    cmd = _install_omp(env)
    assert cmd == "bun install -g @oh-my-pi/pi-coding-agent"


def test_non_wsl_no_tools_fallback(monkeypatch: pytest.MonkeyPatch) -> None:
    _mock_wsl(monkeypatch, is_wsl=False)
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": None,
                                     "npm": None,
                                     "unzip": None,
                                     "brew": None, "pip": None, "pip3": None}))
    env = detect_env()
    cmd = _install_omp(env)
    assert cmd is not None
    assert "curl -fsSL https://bun.sh/install | bash" in cmd


# ------------------------------------------------------------ token safety
def test_omp_token_not_in_stdout(monkeypatch: pytest.MonkeyPatch,
                                  _home: Path,
                                  capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: ["m1"])
    monkeypatch.setattr(connect.shutil, "which", lambda b: "/usr/bin/omp")
    rc = connect.run_connect(client="omp", token="TOPSECRET",
                             runner=connect._shell_install)
    assert rc == 0
    out = capsys.readouterr().out
    assert "TOPSECRET" not in out


# --------------------------------------------------------- _is_wsl_interop
def test_is_wsl_interop_windows_path() -> None:
    assert _is_wsl_interop("/mnt/c/Users/u/.bun/bin/bun.exe") is True
    assert _is_wsl_interop("/mnt/d/some/binary") is True


def test_is_wsl_interop_native_path() -> None:
    assert _is_wsl_interop("/usr/local/bin/bun") is False
    assert _is_wsl_interop("/home/user/.local/bin/npm") is False
    assert _is_wsl_interop("/bin/sh") is False


def test_is_wsl_interop_none() -> None:
    assert _is_wsl_interop(None) is False


# ------------------------------------------------------ WSL install never uses
# Windows bun when --install is passed (integration test)
def test_wsl_install_never_runs_windows_command(monkeypatch: pytest.MonkeyPatch,
                                                 _home: Path,
                                                 capsys: pytest.CaptureFixture[str]) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: ["model-z"])
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/mnt/c/Users/u/.bun/bin/bun.exe",
                                     "npm": "/mnt/c/Program Files/nodejs/npm.exe",
                                     "unzip": "/usr/bin/unzip",
                                     "omp": None,
                                     "brew": None, "pip": None, "pip3": None}))

    installs: list = []

    def _rec_install(argv: object) -> int:
        installs.append(argv)
        return 0

    monkeypatch.setattr(connect, "_shell_install", _rec_install)
    rc = connect.run_connect(client="omp", token="tok", install=True,
                             runner=_rec_install)  # type: ignore[arg-type]
    assert rc == 0
    # _install_omp returned None → install was never attempted
    assert installs == []
    err = capsys.readouterr().err
    assert "requires a native WSL bun" in err


def test_wsl_install_uses_native_bun_command(monkeypatch: pytest.MonkeyPatch,
                                              _home: Path) -> None:
    _mock_wsl(monkeypatch, is_wsl=True)
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: ["model-z"])
    monkeypatch.setattr(connect.shutil, "which",
                        _mock_which({"bun": "/usr/local/bin/bun",
                                     "npm": None,
                                     "unzip": "/usr/bin/unzip",
                                     "omp": None,
                                     "brew": None, "pip": None, "pip3": None}))

    installs: list = []

    def _rec_install(argv: object) -> int:
        installs.append(argv)
        return 0

    monkeypatch.setattr(connect, "_shell_install", _rec_install)
    rc = connect.run_connect(client="omp", token="tok", install=True,
                             runner=_rec_install)  # type: ignore[arg-type]
    assert rc == 0
    assert len(installs) == 1
    cmd = installs[0][0]  # type: ignore[index]
    assert "bun install -g @oh-my-pi/pi-coding-agent" in cmd
    assert "/mnt/" not in cmd  # definitely not a Windows path
