"""Red-proof test for the ``fail_loud`` gate."""

import sys
from pathlib import Path


def test_fail_loud_passes_with_nonzero_exit() -> None:
    """fail_loud goes GREEN when the gate infrastructure forces non-zero on failure.

    The vendored check_fail_loud creates a temp fixture that correctly exits
    non-zero on a failing gate result. This proves the infrastructure is not
    vulnerable to the #200 gate_contract-class bug (a check that prints FAIL
    but exits 0 looking green).
    """
    repo_root = Path(__file__).resolve().parent.parent.parent
    sys.path.insert(0, str(repo_root))
    from tools._vendor.ksf_gates.fail_loud import check_fail_loud

    db_path = repo_root / "_ksf_shim" / "state.db"
    result = check_fail_loud(db_path, {}, [])
    # The vendored check creates a temp fixture that exits non-zero on failure,
    # so the infrastructure is proven correct -> GREEN.
    assert result.passed is True
