from __future__ import annotations

import ast
from pathlib import Path

from tools.check_boundary import scan_engine, scan_file

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


# ---------------------------------------------------------------------------
# ADR-0010 D2 / ADR-0005 R3 — engine stdlib-only boundary (unit tests)
# ---------------------------------------------------------------------------


def test_engine_scan_is_noop_when_dir_absent(tmp_path: Path) -> None:
    assert scan_engine(tmp_path) == []


def test_engine_scan_allows_stdlib_and_charon(tmp_path: Path) -> None:
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "board.py"
    f.write_text("import os\nimport json\nfrom charon.ledger import Ledger\n")
    assert scan_engine(tmp_path) == []


def test_engine_scan_allows_relative_imports(tmp_path: Path) -> None:
    """Regression: from ..ledger import X and from .board import X must PASS.

    E0's scan_engine_file had no level check — it called _engine_allowed("ledger")
    which returned False, falsely flagging intra-charon relative imports.
    """
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "coordinator.py"
    f.write_text(
        "from ..ledger import Ledger\n"
        "from .board import Board\n"
        "from . import utils\n"
    )
    assert scan_engine(tmp_path) == [], (
        "Relative imports inside engine/ must be allowed (they are intra-charon)"
    )


def test_engine_scan_flags_third_party_absolute_import(tmp_path: Path) -> None:
    """Regression: import requests (absolute, third-party) must FAIL."""
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "bad.py"
    f.write_text("import requests\n")
    violations = scan_engine(tmp_path)
    assert any("requests" in v for v in violations)


def test_engine_scan_flags_third_party_from_import(tmp_path: Path) -> None:
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "bad.py"
    f.write_text("from httpx import AsyncClient\n")
    violations = scan_engine(tmp_path)
    assert any("httpx" in v for v in violations)


def test_engine_scan_flags_worker_third_party(tmp_path: Path) -> None:
    ports = tmp_path / "charon" / "ports"
    ports.mkdir(parents=True)
    worker = ports / "worker.py"
    worker.write_text("import pydantic\n")
    violations = scan_engine(tmp_path)
    assert any("pydantic" in v for v in violations)


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
