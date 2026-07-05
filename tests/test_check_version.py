"""Guards for tools/check_version.py — the version single-source-of-truth check.

Locks in the two drift modes + the CI-aware behavior (no test shipped with the
original CI-aware fix; this closes that gap)."""
from __future__ import annotations

import importlib.util
from pathlib import Path

_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("cv_tool", _ROOT / "tools" / "check_version.py")
assert _spec and _spec.loader
cv = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(cv)


def _mk(tmp_path, pyver, literals=None):
    (tmp_path / "src" / "charon").mkdir(parents=True)
    (tmp_path / "pyproject.toml").write_text(f'[project]\nname="charon"\nversion="{pyver}"\n')
    # the sanctioned home carries a non-version fallback literal — must be ignored
    (tmp_path / "src" / "charon" / "__init__.py").write_text('__version__ = "0+unknown"\n')
    for name, v in (literals or {}).items():
        (tmp_path / "src" / "charon" / name).write_text(f'__version__ = "{v}"\n')


def test_in_ci(monkeypatch):
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert cv._in_ci() is False
    monkeypatch.setenv("CI", "true")
    assert cv._in_ci() is True


def test_literal_drift_flags_duplicate_but_skips_init(tmp_path, monkeypatch):
    _mk(tmp_path, "1.2.3", {"dup.py": "1.2.2"})
    monkeypatch.chdir(tmp_path)
    drift = cv._literal_drift("1.2.3")
    assert any("dup.py:1.2.2" in d for d in drift)          # caught
    assert not any("__init__" in d for d in drift)          # fallback ignored


def test_stale_local_metadata_warns_not_fails(tmp_path, monkeypatch):
    _mk(tmp_path, "1.2.3")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cv, "version", lambda pkg: "0.0.1")  # stale installed
    monkeypatch.delenv("CI", raising=False)
    monkeypatch.delenv("GITHUB_ACTIONS", raising=False)
    assert cv.main() == 0                                    # warn, not fail


def test_ci_metadata_drift_fails(tmp_path, monkeypatch):
    _mk(tmp_path, "1.2.3")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cv, "version", lambda pkg: "0.0.1")
    monkeypatch.setenv("CI", "true")
    assert cv.main() == 1                                    # fresh CI install must match


def test_source_literal_drift_fails_everywhere(tmp_path, monkeypatch):
    _mk(tmp_path, "1.2.3", {"dup.py": "9.9.9"})
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(cv, "version", lambda pkg: "1.2.3")  # metadata matches...
    monkeypatch.delenv("CI", raising=False)
    assert cv.main() == 1                                    # ...but a source literal drifts
