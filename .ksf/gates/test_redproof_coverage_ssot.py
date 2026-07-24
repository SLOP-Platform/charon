"""Red-proof test for the ``coverage_ssot`` gate."""

import sys
from pathlib import Path


def test_coverage_ssot_detects_gap(tmp_path: Path) -> None:
    """coverage_ssot goes RED when a declared gate has no implementation."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)

    # Manifest declares "nonexistent_gate" but no implementation exists
    manifest = {"gates": {"list": ["nonexistent_gate"]}}

    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.coverage_ssot import check_coverage_ssot

    result = check_coverage_ssot(db_path, manifest, [])
    assert result.passed is False
    # Gaps contain "coverage-gap" and messages contain "GAP: ..."
    gap_found = "coverage-gap" in result.gaps
    msg_found = any("GAP:" in m for m in result.messages)
    assert gap_found or msg_found


def test_coverage_ssot_passes_when_implemented(tmp_path: Path) -> None:
    """coverage_ssot goes GREEN when all declared gates are implemented."""
    repo_root = tmp_path / "repo"
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gates_dir.mkdir(parents=True)
    (gates_dir / "my_gate.py").write_text(
        "from tools._vendor.ksf_gate_result import GateResult\n"
        "def check_my_gate(db, m, mods):\n"
        "    return GateResult(True, [], [])\n"
    )

    # coverage_ssot also checks for red-proof tests for mechanized gates
    proofs_dir = repo_root / ".ksf" / "gates"
    proofs_dir.mkdir(parents=True)
    (proofs_dir / "test_redproof_my_gate.py").write_text(
        "def test_proof():\n    assert True\n"
    )

    manifest = {"gates": {"list": ["my_gate"]}}

    db_path = repo_root / "_ksf_shim" / "state.db"

    sys.path.insert(0, str(Path(__file__).resolve().parent.parent.parent))
    from tools._vendor.ksf_gates.coverage_ssot import check_coverage_ssot

    result = check_coverage_ssot(db_path, manifest, [])
    assert result.passed is True
