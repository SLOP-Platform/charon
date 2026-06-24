from __future__ import annotations

import ast
from pathlib import Path

from tools.check_boundary import scan_file

# Privileged-exec symbols the exposed web process must NOT reference in-process
# (DTC 2026-06-24 / ADR-0002 §2.3 / INV-B4): running the coordinator loop or an
# acceptance dispatch inside the exposed FastAPI process contradicts the "the
# privileged loop runs in its own container" topology. `api.show_ledger` is
# read-only and allowed; `api.run_task` and the coordinator are not.
_PRIVILEGED_EXEC_SYMBOLS = {"run_task", "coordinator", "dispatch"}


def _attr_and_name_refs(src: str) -> set[str]:
    tree = ast.parse(src)
    refs: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Attribute):
            refs.add(node.attr)
        elif isinstance(node, ast.Name):
            refs.add(node.id)
        elif isinstance(node, ast.ImportFrom) and node.module == "coordinator":
            refs.add("coordinator")
    return refs


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


def test_service_app_runs_no_privileged_loop_in_process() -> None:
    """INV-B4 / ADR-0002 §2.3: the exposed web process must not run the
    privileged coordinator loop in-process. Structural guard — would have caught
    the pre-DTC scaffold that called `api.run_task` from the POST handler."""
    app_src = Path("src/charon/service/app.py").read_text()
    refs = _attr_and_name_refs(app_src)
    leaked = refs & _PRIVILEGED_EXEC_SYMBOLS
    assert not leaked, (
        f"service/app.py references privileged-exec symbol(s) {sorted(leaked)} — "
        f"the web process must stay read-only; the loop runs in the worker container"
    )
