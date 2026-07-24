"""Red-proof test for the ``no_vacuous`` gate."""

import sys
from pathlib import Path


def test_no_vacuous_detects_zero_gates(tmp_path: Path) -> None:
    """no_vacuous goes RED when no gate files are discovered."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)
    # No .py files beyond __init__ — but __init__ is filtered by _
    (gates_dir / "__init__.py").write_text("")

    # Create a dummy pyproject.toml so pytest --collect-only doesn't crash
    (repo_root / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.no_vacuous import check_no_vacuous

    result = check_no_vacuous(db_path, {}, [])
    assert result.passed is False
    assert any("zero-gate" in m.lower() or "0 tests" in m.lower() for m in result.messages)


def test_no_vacuous_passes_with_gates(tmp_path: Path) -> None:
    """no_vacuous goes GREEN when gate files are discovered."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)
    (gates_dir / "some_gate.py").write_text(
        "from tools._vendor.ksf_gate_result import GateResult\n"
        "def check_some_gate(db, m, mods):\n"
        "    return GateResult(True, [], [])\n"
    )
    (repo_root / "tests").mkdir(parents=True)
    (repo_root / "tests" / "__init__.py").write_text("")
    # A test file so pytest --collect-only finds something
    (repo_root / "tests" / "test_dummy.py").write_text(
        "def test_ok():\n    assert True\n"
    )
    (repo_root / "pyproject.toml").write_text("[project]\nname = 'test'\n")

    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.no_vacuous import check_no_vacuous

    result = check_no_vacuous(db_path, {}, [])
    assert result.passed is True
