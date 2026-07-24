"""Red-proof test for the ``wiring_alignment`` gate."""

import sys
from pathlib import Path


def test_wiring_alignment_detects_missing_test_import(tmp_path: Path) -> None:
    """wiring_alignment goes RED when an entrypoint module has no test import."""
    repo_root = tmp_path / "repo"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "tests" / "__init__.py").write_text("")
    (repo_root / "tests" / "test_other.py").write_text("")

    # pyproject.toml declares an entrypoint module that has NO test import
    (repo_root / "pyproject.toml").write_text(
        '[project]\nscripts = {mycli = "my_module:main"}\n'
    )
    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.wiring_alignment import check_wiring_alignment

    result = check_wiring_alignment(db_path, {}, [])
    assert result.passed is False
    assert any("missing-test-import" in m for m in result.messages)


def test_wiring_alignment_passes_with_test_import(tmp_path: Path) -> None:
    """wiring_alignment goes GREEN when every entrypoint has a test import."""
    repo_root = tmp_path / "repo"
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "tests" / "__init__.py").write_text("")
    (repo_root / "tests" / "test_my.py").write_text("import my_module\n")

    (repo_root / "pyproject.toml").write_text(
        '[project]\nscripts = {mycli = "my_module:main"}\n'
    )
    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.wiring_alignment import check_wiring_alignment

    result = check_wiring_alignment(db_path, {}, [])
    assert result.passed is True
