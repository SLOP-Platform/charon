"""Red-proof test for the ``redproof`` gate: proves it goes RED when a gate is missing."""

import sys
from pathlib import Path


def test_redproof_detects_missing_proof(tmp_path: Path) -> None:
    """redproof should flag a gate with no companion red-proof test."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)
    (gates_dir / "my_gate.py").write_text(
        "from tools._vendor.ksf_gate_result import GateResult\n"
        "def check_my_gate(db, m, mods):\n"
        "    return GateResult(True, [], [])\n"
    )
    # NO .ksf/gates/test_redproof_my_gate.py — should be flagged

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.redproof import check_redproof

    db_path = repo_root / "_ksf_shim" / "state.db"
    result = check_redproof(db_path, {}, [])
    assert result.passed is False
    assert any("my_gate" in m for m in result.messages)


def test_redproof_passes_with_proof(tmp_path: Path) -> None:
    """redproof should pass when every gate has a companion red-proof test."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)
    (gates_dir / "my_gate.py").write_text(
        "from tools._vendor.ksf_gate_result import GateResult\n"
        "def check_my_gate(db, m, mods):\n"
        "    return GateResult(True, [], [])\n"
    )
    proofs_dir = repo_root / ".ksf" / "gates"
    proofs_dir.mkdir(parents=True)
    (proofs_dir / "test_redproof_my_gate.py").write_text(
        "def test_proof():\n    assert 1 == 1\n"
    )

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.redproof import check_redproof

    db_path = repo_root / "_ksf_shim" / "state.db"
    result = check_redproof(db_path, {}, [])
    assert result.passed is True
