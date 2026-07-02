"""CLIENT-CONNECT-GUI — add cline + continue to `charon connect`.

Tests: continue writes correct config.json shape + idempotent; cline guided
mode prints manual setup instructions; token never in stdout.
"""
from __future__ import annotations

import json
from pathlib import Path

import pytest

import charon.connect as connect


@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    return tmp_path


def _run(monkeypatch: pytest.MonkeyPatch, client: str, ids: list[str],
         **kw: object) -> int:
    monkeypatch.setattr(connect, "discover_models",
                        lambda *a, **k: [{"id": i, "free": False} for i in ids])
    monkeypatch.setattr(connect.shutil, "which", lambda b: None)
    return connect.run_connect(client=client, token="TOKEN1",  # type: ignore[arg-type]
                               runner=connect._shell_install, **kw)


# ------------------------------------------------------------- continue writer


def test_continue_writes_config_shape(monkeypatch: pytest.MonkeyPatch,
                                       _home: Path) -> None:
    rc = _run(monkeypatch, "continue", ["sonnet-4.5"])
    assert rc == 0
    path = _home / ".continue" / "config.json"
    data = json.loads(path.read_text())
    assert isinstance(data["models"], list)
    assert len(data["models"]) == 1
    m = data["models"][0]
    assert m["title"] == "Charon — sonnet-4.5"
    assert m["provider"] == "openai"
    assert m["model"] == "sonnet-4.5"
    assert m["apiBase"] == "http://127.0.0.1:8080/v1"
    assert m["apiKey"] == "TOKEN1"


def test_continue_idempotent(monkeypatch: pytest.MonkeyPatch,
                              _home: Path) -> None:
    _run(monkeypatch, "continue", ["sonnet-4.5"])
    first = (_home / ".continue" / "config.json").read_text()
    _run(monkeypatch, "continue", ["sonnet-4.5"])
    assert (_home / ".continue" / "config.json").read_text() == first


def test_continue_preserves_other_models(monkeypatch: pytest.MonkeyPatch,
                                          _home: Path) -> None:
    path = _home / ".continue" / "config.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({
        "models": [
            {"title": "Existing", "provider": "openai", "model": "old", "apiBase": "x"},
        ],
        "otherKey": "keep",
    }))
    _run(monkeypatch, "continue", ["new-model"])
    data = json.loads(path.read_text())
    assert len(data["models"]) == 2
    assert data["otherKey"] == "keep"
    titles = [m["title"] for m in data["models"]]
    assert "Charon — new-model" in titles
    assert "Existing" in titles


# -------------------------------------------------------------- cline guided


def test_cline_is_guided_entry(monkeypatch: pytest.MonkeyPatch,
                                capsys: pytest.CaptureFixture[str]) -> None:
    spec = connect.REGISTRY["cline"]
    assert spec.guided is True


def test_cline_prints_manual_instructions(monkeypatch: pytest.MonkeyPatch,
                                           _home: Path,
                                           capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(monkeypatch, "cline", ["gpt-5"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "Manual setup:" in out and "VS Code" in out
    assert "cline.apiProvider" in out or "openaiBaseUrl" in out
    assert "TOKEN1" in out  # token IS included in the manual instructions
    assert "gpt-5" in out


def test_cline_guided_writes_no_config(monkeypatch: pytest.MonkeyPatch,
                                        _home: Path) -> None:
    _run(monkeypatch, "cline", ["gpt-5"])
    path = _home / ".cline" / "config.json"
    assert not path.is_file()


# --------------------------------------------------------- token safety


def test_continue_token_not_in_stdout(monkeypatch: pytest.MonkeyPatch,
                                       _home: Path,
                                       capsys: pytest.CaptureFixture[str]) -> None:
    _run(monkeypatch, "continue", ["m1"])
    out = capsys.readouterr().out
    # Token written to config but never printed
    assert "TOKEN1" not in out


# --------------------------------------------------------------- registry SSOT


def test_registry_includes_continue_and_cline() -> None:
    names = connect.supported_clients()
    assert "continue" in names
    assert "cline" in names
    # All entries are in the registry
    assert len(names) == len(connect.REGISTRY)
