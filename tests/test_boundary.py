from __future__ import annotations

from pathlib import Path

from tools.check_boundary import scan_file


def test_clean_file_has_no_violations(tmp_path: Path) -> None:
    f = tmp_path / "clean.py"
    f.write_text("import os\nfrom pathlib import Path\nx = 1\n")
    assert scan_file(f) == []


def test_direct_slop_import_is_flagged(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text("import slop\n")
    assert any("slop" in v for v in scan_file(f))


def test_from_mediastack_import_is_flagged(tmp_path: Path) -> None:
    f = tmp_path / "bad.py"
    f.write_text("from mediastack.core import thing\n")
    assert any("mediastack" in v for v in scan_file(f))


def test_dynamic_import_obfuscation_is_flagged(tmp_path: Path) -> None:
    # BR-4: the AST scan catches a literal __import__ argument naming SLOP.
    f = tmp_path / "sneaky.py"
    f.write_text("m = __import__('slop')\n")
    assert any("slop" in v for v in scan_file(f))


def test_repo_source_is_clean() -> None:
    # The actual src/ tree must be boundary-clean.
    from tools.check_boundary import main

    assert main("src") == 0
