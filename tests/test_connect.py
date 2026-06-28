"""Tests for ``charon connect <client>`` (CLIENT-CONNECT).

Covers: gateway-first verification (unreachable → non-zero, NO config written),
model discovery, every supported client's config writer (correct baseURL + token +
model at the right path) and idempotency, the token never leaking to stdout, no
install attempted without ``--install``, and the writer registry being the single
source of the supported-client list.
"""
from __future__ import annotations

import json
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer
from pathlib import Path

import pytest

import charon.connect as connect
from charon.cli import main


# ----------------------------------------------------------------- fixtures
@pytest.fixture(autouse=True)
def _home(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Redirect every HOME-relative client path into a tmp dir."""
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    monkeypatch.delenv("CHARON_GATEWAY_TOKEN", raising=False)
    return tmp_path


def _serve(payload: object, *, captured: dict) -> tuple[str, int, HTTPServer]:
    """A loopback HTTP server answering ``GET /v1/models`` with ``payload`` and
    recording the Authorization header it saw."""
    class H(BaseHTTPRequestHandler):
        def log_message(self, *a: object) -> None:  # silence
            pass

        def do_GET(self) -> None:  # noqa: N802
            captured["path"] = self.path
            captured["auth"] = self.headers.get("Authorization")
            body = json.dumps(payload).encode()
            self.send_response(200)
            self.send_header("Content-Type", "application/json")
            self.send_header("Content-Length", str(len(body)))
            self.end_headers()
            self.wfile.write(body)

    srv = HTTPServer(("127.0.0.1", 0), H)
    threading.Thread(target=srv.serve_forever, daemon=True).start()
    host, port = srv.server_address[0], srv.server_address[1]
    return str(host), int(port), srv


# ------------------------------------------------------------- discovery
def test_discover_models_live() -> None:
    captured: dict = {}
    payload = {"data": [{"id": "gpt-x"}, {"id": "claude-y"}]}
    host, port, srv = _serve(payload, captured=captured)
    try:
        ids = connect.discover_models(host, port, "secret-tok")
    finally:
        srv.shutdown()
    assert ids == ["gpt-x", "claude-y"]
    assert captured["path"] == "/v1/models"
    assert captured["auth"] == "Bearer secret-tok"


def test_discover_models_unreachable() -> None:
    # port 1 is not listening → transport error → GatewayUnreachable
    with pytest.raises(connect.GatewayUnreachable):
        connect.discover_models("127.0.0.1", 1, None, timeout=1.0)


# --------------------------------------------------------- gateway-first guard
def test_unreachable_gateway_writes_nothing(capsys: pytest.CaptureFixture[str],
                                            _home: Path) -> None:
    rc = main(["connect", "opencode", "--port", "1"])
    assert rc == 1
    err = capsys.readouterr().err
    assert "charon gateway" in err  # tells the user how to start it
    # NO config written
    assert not (_home / ".config" / "opencode" / "opencode.json").exists()


# ---------------------------------------------------- per-client writers + e2e
def _run(monkeypatch: pytest.MonkeyPatch, client: str, ids: list[str],
         **kw: object) -> int:
    """Run ``charon connect <client>`` with discovery + install stubbed."""
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: list(ids))
    installs: list = []
    def _rec_install(argv: object) -> int:
        installs.append(argv)
        return 0
    monkeypatch.setattr(connect, "_shell_install", _rec_install)
    monkeypatch.setattr(connect.shutil, "which", lambda b: None)  # client "missing"
    rc = connect.run_connect(client=client, token="TOPSECRET",  # type: ignore[arg-type]
                             runner=connect._shell_install, **kw)
    # no --install passed → install must NOT be attempted
    assert installs == []
    return rc


def test_opencode_writer_and_idempotent(monkeypatch: pytest.MonkeyPatch,
                                        _home: Path,
                                        capsys: pytest.CaptureFixture[str]) -> None:
    rc = _run(monkeypatch, "opencode", ["modelA", "modelB"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "TOPSECRET" not in out  # token never printed

    path = _home / ".config" / "opencode" / "opencode.json"
    data = json.loads(path.read_text())
    opts = data["provider"]["charon"]["options"]
    assert opts["baseURL"] == "http://127.0.0.1:8080/v1"
    assert opts["apiKey"] == "TOPSECRET"
    assert "modelA" in data["provider"]["charon"]["models"]  # first served model

    first = path.read_text()
    _run(monkeypatch, "opencode", ["modelA", "modelB"])
    assert path.read_text() == first  # idempotent


def test_opencode_preserves_existing_providers(monkeypatch: pytest.MonkeyPatch,
                                               _home: Path) -> None:
    path = _home / ".config" / "opencode" / "opencode.json"
    path.parent.mkdir(parents=True)
    path.write_text(json.dumps({"provider": {"other": {"keep": 1}}, "theme": "x"}))
    _run(monkeypatch, "opencode", ["m1"])
    data = json.loads(path.read_text())
    assert data["provider"]["other"] == {"keep": 1}  # unrelated provider preserved
    assert data["theme"] == "x"
    assert data["provider"]["charon"]["options"]["apiKey"] == "TOPSECRET"


def test_omp_writer_and_idempotent(monkeypatch: pytest.MonkeyPatch,
                                   _home: Path) -> None:
    rc = _run(monkeypatch, "omp", ["k2-coder"])
    assert rc == 0
    path = _home / ".omp" / "agent" / "models.yml"
    text = path.read_text()
    assert "http://127.0.0.1:8080/v1" in text
    assert "TOPSECRET" in text
    assert "k2-coder" in text
    first = text
    _run(monkeypatch, "omp", ["k2-coder"])
    assert path.read_text() == first  # idempotent


def test_aider_writer_and_path(monkeypatch: pytest.MonkeyPatch,
                               _home: Path) -> None:
    rc = _run(monkeypatch, "aider", ["deep-v3"])
    assert rc == 0
    path = _home / ".aider.conf.yml"
    text = path.read_text()
    assert 'openai-api-base: "http://127.0.0.1:8080/v1"' in text
    assert 'openai-api-key: "TOPSECRET"' in text
    assert 'model: "openai/deep-v3"' in text


def test_explicit_model_overrides_discovery(monkeypatch: pytest.MonkeyPatch,
                                            _home: Path) -> None:
    _run(monkeypatch, "opencode", ["auto1", "auto2"], model="pinned")
    data = json.loads((_home / ".config" / "opencode" / "opencode.json").read_text())
    assert "pinned" in data["provider"]["charon"]["models"]


def test_no_models_served_is_error(monkeypatch: pytest.MonkeyPatch,
                                   _home: Path,
                                   capsys: pytest.CaptureFixture[str]) -> None:
    monkeypatch.setattr(connect, "discover_models", lambda *a, **k: [])
    monkeypatch.setattr(connect.shutil, "which", lambda b: None)
    rc = connect.run_connect(client="aider")
    assert rc == 1
    assert "serves no models" in capsys.readouterr().err
    assert not (_home / ".aider.conf.yml").exists()  # nothing written


def test_unknown_client_lists_supported(capsys: pytest.CaptureFixture[str]) -> None:
    rc = connect.run_connect(client="nope")
    assert rc == 2
    err = capsys.readouterr().err
    for name in connect.supported_clients():
        assert name in err


# --------------------------------------------------- yaml merge + registry SSOT
def test_yaml_merge_preserves_unrelated_and_idempotent(tmp_path: Path) -> None:
    p = tmp_path / "c.yml"
    p.write_text("# header\nkeep_me: 7\nnested:\n  a: 1\n")
    connect.yaml_merge_toplevel(p, {"charon": {"base_url": "u", "model": "m"}})
    text = p.read_text()
    assert "keep_me: 7" in text  # unrelated top-level preserved verbatim
    assert "# header" in text
    assert "  a: 1" in text  # nested block of an unrelated key preserved
    assert 'base_url: "u"' in text
    once = p.read_text()
    connect.yaml_merge_toplevel(p, {"charon": {"base_url": "u", "model": "m"}})
    assert p.read_text() == once  # idempotent (replaces, never duplicates)


def test_registry_is_single_source_of_supported_list() -> None:
    assert connect.supported_clients() == sorted(connect.REGISTRY)
    # every spec wires the three writer hooks the orchestration relies on
    for spec in connect.REGISTRY.values():
        assert callable(spec.write) and callable(spec.config_path)
        assert callable(spec.install) and callable(spec.launch)
