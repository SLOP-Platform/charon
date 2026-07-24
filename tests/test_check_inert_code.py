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

Plus a CAPABILITY-ACTUALS-DEADREF-CLEANUP fail-on-revert: no reference to
the deleted `charon.capability.actuals` module's symbols (the
``ActualsLedger`` / ``ActualRow`` types, or the ``capability.actuals``
dotted name) survives in any of the three files that ticket owned. Revert
any one of the three cleanups and this test fails on the next pytest run.
"""
from __future__ import annotations

import json
import re
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


class TestActualsDeadrefFailOnRevert:
    """CAPABILITY-ACTUALS-DEADREF-CLEANUP contract: no reference to the
    DELETED ``charon.capability.actuals`` module's symbols survives in the
    three files that ticket owned. The deleted module
    (``src/charon/capability/actuals.py`` — ``ActualsLedger`` /
    ``ActualRow``) is gone from origin/master; every stale pointer that
    named it must stay gone. Revert any one of the three cleanups and this
    test fails on the next pytest run."""

    _REPO_ROOT = Path(__file__).resolve().parent.parent
    _OWNED_FILES = (
        _REPO_ROOT / "src" / "charon" / "decompose_sizing.py",
        _REPO_ROOT / "tools" / "check_inert_code.py",
        _REPO_ROOT / "tools" / "inert-code-disposition.json",
    )
    _DEADREF_RE = re.compile(r"capability\.actuals|ActualsLedger|ActualRow")

    def _scan(self) -> dict[Path, list[tuple[int, str]]]:
        hits: dict[Path, list[tuple[int, str]]] = {}
        for path in self._OWNED_FILES:
            text = path.read_text(encoding="utf-8")
            for lineno, line in enumerate(text.splitlines(), start=1):
                if self._DEADREF_RE.search(line):
                    hits.setdefault(path, []).append((lineno, line))
        return hits

    def test_no_actuals_deadref_in_three_owned_files(self) -> None:
        hits = self._scan()
        assert not hits, (
            "CAPABILITY-ACTUALS-DEADREF-CLEANUP fail-on-revert: stale reference "
            "to the deleted charon.capability.actuals module survived in:\n"
            + "\n".join(
                f"  {p.relative_to(self._REPO_ROOT)}:{ln}: {line.strip()}"
                for p, items in hits.items()
                for ln, line in items
            )
        )

    def test_owned_files_exist(self) -> None:
        """Belt-and-suspenders: the three files this contract pins must
        still exist on disk; if a rename/refactor happens, the grep above
        would silently pass against an empty result. This forces a loud
        failure so the contract is updated alongside the refactor."""
        for path in self._OWNED_FILES:
            assert path.exists(), f"owned file vanished: {path}"
