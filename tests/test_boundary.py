from __future__ import annotations

import ast
import json
import os
import subprocess
import sys
from pathlib import Path

from tools.check_boundary import scan_engine, scan_file

# Repo root (…/charon) and its src/ dir, resolved absolutely from this file so
# subprocesses we spawn below do not depend on the ambient CWD or a *relative*
# PYTHONPATH=src — either of which a prior test could have perturbed. Pinning
# both makes the subprocess-based guards hermetic (test-isolation fix).
_REPO_ROOT = Path(__file__).resolve().parents[1]
_SRC_DIR = _REPO_ROOT / "src"


def _hermetic_env() -> dict[str, str]:
    """A child-process env whose PYTHONPATH points at this checkout's src/ by
    absolute path, so `import charon` resolves regardless of CWD or a polluted
    parent PYTHONPATH."""
    env = dict(os.environ)
    existing = env.get("PYTHONPATH", "")
    parts = [str(_SRC_DIR), str(_REPO_ROOT)]
    if existing:
        parts.append(existing)
    env["PYTHONPATH"] = os.pathsep.join(parts)
    return env

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
    # BR-4: the AST scan catches a literal __import__ argument naming a host project.
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


# ---------------------------------------------------------------------------
# ADR-0010 D2 / ADR-0005 R3 — engine stdlib-only boundary (unit tests)
# ---------------------------------------------------------------------------


def test_engine_scan_is_noop_when_dir_absent(tmp_path: Path) -> None:
    """scan_engine returns no violations when engine/ does not exist (build step 0)."""
    assert scan_engine(tmp_path) == []


def test_engine_scan_allows_stdlib_and_charon(tmp_path: Path) -> None:
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "board.py"
    f.write_text("import os\nimport json\nfrom charon.ledger import Ledger\n")
    assert scan_engine(tmp_path) == []


def test_engine_scan_flags_third_party_import(tmp_path: Path) -> None:
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


def test_engine_scan_allows_relative_import(tmp_path: Path) -> None:
    """Relative imports (from ..ledger import X) are intra-charon — must not be flagged."""
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "coordinator.py"
    f.write_text("from ..ledger import Ledger\nfrom .board import Board\n")
    assert scan_engine(tmp_path) == []


def test_engine_scan_flags_absolute_third_party_not_relative(tmp_path: Path) -> None:
    """Absolute third-party import must still fail; relative sibling must still pass."""
    eng = tmp_path / "charon" / "engine"
    eng.mkdir(parents=True)
    f = eng / "mixed.py"
    f.write_text("from .board import Board\nimport requests\n")
    violations = scan_engine(tmp_path)
    assert any("requests" in v for v in violations)
    assert not any(".board" in v or "board" in v and "requests" not in v for v in violations)


def test_ports_worker_scan_flags_third_party(tmp_path: Path) -> None:
    ports = tmp_path / "charon" / "ports"
    ports.mkdir(parents=True)
    worker = ports / "worker.py"
    worker.write_text("import pydantic\n")
    violations = scan_engine(tmp_path)
    assert any("pydantic" in v for v in violations)


# ---------------------------------------------------------------------------
# ADR-0010 D2 — transitive sys.modules guard (subprocess, not AST)
# ---------------------------------------------------------------------------


def test_gateway_path_does_not_import_engine_transitively() -> None:
    """ADR-0010 D2 anti-dilution: importing proxy_server/gateway/service.app must
    not transitively load any charon.engine.* module or charon.ports.worker.

    Uses a real subprocess so the check captures actual runtime import resolution,
    not a static AST walk (indirect imports via getattr or __import__ are caught).
    """
    code = (
        "import sys, json; "
        "import charon.proxy_server; "
        "import charon.gateway; "
        "import charon.service.app; "
        "leaked = ["
        "    m for m in sys.modules"
        "    if m.startswith('charon.engine') or m == 'charon.ports.worker'"
        "]; "
        "print(json.dumps(leaked))"
    )
    result = subprocess.run(
        [sys.executable, "-c", code],
        capture_output=True,
        text=True,
        cwd=str(_REPO_ROOT),
        env=_hermetic_env(),
        check=True,
    )
    leaked: list[str] = json.loads(result.stdout)
    assert not leaked, (
        f"Gateway path transitively imports engine module(s) {leaked} — "
        "ADR-0010 D2 anti-dilution violated; engine must not appear on the gateway import path"
    )
