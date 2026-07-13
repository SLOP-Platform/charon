"""Red-proof tests for tools/check_inert_code.py (the inert-code merge gate).

Two layers, mirroring tests/test_check_arch.py's shape:

1. The vendored KSF detector itself (tools/_vendor/ksf_inert_code.py) —
   proven against synthetic fixtures, exactly like KSF's own upstream
   red-proof (.ksf/gates/test_redproof_inert_code.py in the keystone repo).
2. The Charon-side adapter (tools/check_inert_code.py) — the "src." prefix
   stripping / "charon." scoping, and the green-without-hiding disposition
   contract (undisposed dead symbol -> FAIL; disposed -> PASS; malformed
   disposition entry -> FAIL).

Plus a clean-codebase assertion: the real repo, as tracked today via
tools/inert-code-disposition.json, must pass.
"""
from __future__ import annotations

import json
from pathlib import Path

import tools.check_inert_code as M
from tools._vendor.ksf_inert_code import check_inert_code


class TestVendoredDetector:
    """Proves the vendored KSF detector logic itself still behaves as KSF's
    own upstream red-proof expects (see keystone's
    .ksf/gates/test_redproof_inert_code.py — same fixture shapes)."""

    def test_flags_unregistered_unreachable(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        src = repo / "src"
        src.mkdir(parents=True)
        (src / "alive.py").write_text(
            "def used():\n    pass\n\ndef unused():\n    pass\n"
        )
        (src / "entry.py").write_text(
            "from alive import used\n\ndef main():\n    used()\n"
        )
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {run = "entry:main"}\n'
        )
        db = repo / ".ksf" / "keystone.db"
        db.parent.mkdir(parents=True, exist_ok=True)

        result = check_inert_code(db, {}, [])
        assert result.passed is False
        assert any("inert-code:" in m and "unused" in m for m in result.messages)

    def test_passes_when_reachable(self, tmp_path: Path) -> None:
        repo = tmp_path / "repo"
        src = repo / "src"
        src.mkdir(parents=True)
        (src / "helpers.py").write_text("def helper():\n    pass\n")
        (src / "main.py").write_text(
            "from helpers import helper\n\ndef run():\n    helper()\n"
        )
        (repo / "pyproject.toml").write_text(
            '[project]\nscripts = {cli = "main:run"}\n'
        )
        db = repo / ".ksf" / "keystone.db"
        db.parent.mkdir(parents=True, exist_ok=True)

        result = check_inert_code(db, {}, [])
        assert result.passed is True
        assert not any("helper" in m for m in result.messages)


def _write_charon_fixture(repo: Path) -> None:
    """A minimal src/charon/ tree with one reachable and one unreachable
    public symbol, plus a pyproject.toml declaring the real entrypoint shape
    (charon.cli:main) so the adapter's 'charon.' scoping has something to
    match against."""
    pkg = repo / "src" / "charon"
    pkg.mkdir(parents=True)
    (pkg / "__init__.py").write_text("")
    (pkg / "cli.py").write_text(
        "from .used_module import wired_function\n\n"
        "def main():\n    wired_function()\n"
    )
    (pkg / "used_module.py").write_text(
        "def wired_function():\n    pass\n\n"
        "def throwaway_unreachable_probe():\n    pass\n"
    )
    (repo / "pyproject.toml").write_text(
        '[project]\nscripts = {charon = "charon.cli:main"}\n'
    )


class TestAdapterScopingAndDisposition:
    """Proves the Charon-side adapter: 'src.' stripping + 'charon.' scoping,
    and the disposition-file gate contract."""

    def test_find_dead_symbols_strips_prefix_and_scopes_to_charon(
        self, tmp_path: Path
    ) -> None:
        _write_charon_fixture(tmp_path)
        dead = M.find_dead_symbols(repo_root=tmp_path)
        assert dead == ["charon.used_module.throwaway_unreachable_probe"]

    def test_undisposed_dead_symbol_fails(self, tmp_path: Path, monkeypatch) -> None:
        _write_charon_fixture(tmp_path)
        empty_disposition = tmp_path / "disposition.json"
        empty_disposition.write_text("{}")
        monkeypatch.setattr(M, "DISPOSITION_PATH", empty_disposition)

        passed, undisposed, dead, schema_issues = M.check(repo_root=tmp_path)
        assert passed is False
        assert schema_issues == []
        assert undisposed == ["charon.used_module.throwaway_unreachable_probe"]
        assert dead == undisposed

    def test_disposed_dead_symbol_passes(self, tmp_path: Path, monkeypatch) -> None:
        _write_charon_fixture(tmp_path)
        disposition = tmp_path / "disposition.json"
        disposition.write_text(json.dumps({
            "charon.used_module.throwaway_unreachable_probe": {
                "reason": "throwaway fixture symbol for the red-proof test",
                "disposition": "keep-fixture",
            }
        }))
        monkeypatch.setattr(M, "DISPOSITION_PATH", disposition)

        passed, undisposed, dead, schema_issues = M.check(repo_root=tmp_path)
        assert passed is True
        assert undisposed == []
        assert dead == ["charon.used_module.throwaway_unreachable_probe"]
        assert schema_issues == []

    def test_malformed_disposition_entry_fails(self, tmp_path: Path, monkeypatch) -> None:
        _write_charon_fixture(tmp_path)
        disposition = tmp_path / "disposition.json"
        disposition.write_text(json.dumps({
            "charon.used_module.throwaway_unreachable_probe": {
                "reason": "",
                "disposition": "maybe-later",
            }
        }))
        monkeypatch.setattr(M, "DISPOSITION_PATH", disposition)

        passed, undisposed, dead, schema_issues = M.check(repo_root=tmp_path)
        assert passed is False
        assert len(schema_issues) == 2  # empty reason + invalid disposition value


class TestCleanCodebase:
    """The real repo, as tracked today via tools/inert-code-disposition.json,
    must pass — every currently-known 0-caller symbol is disposed."""

    def test_current_codebase_passes(self) -> None:
        passed, undisposed, _dead, schema_issues = M.check()
        assert schema_issues == []
        assert undisposed == [], (
            f"new dead symbol(s) not tracked in {M.DISPOSITION_PATH.name}: {undisposed}"
        )
        assert passed is True
