"""Gate — no_vacuous: zero items checked = RED (generalized empty-discovery-fails).

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/no_vacuous.py`` (Keystone Framework).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only changes from the KSF original are the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package)
and the gates_dir path (``ksf/gates/`` -> ``tools/_vendor/ksf_gates/`` so the
detector finds Charon's vendored copies). Everything else — including the
KSF-native ``check_no_vacuous(db_path, manifest, modules)`` signature — is
untouched; see ``tools/check_no_vacuous.py`` for the Charon-side adapter.
Do not hand-edit the logic below; re-copy from KSF and re-apply this header
if the upstream detector changes. See ``tools/_vendor/README.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools._vendor.ksf_gate_result import GateResult


def check_no_vacuous(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    """Fail if pytest collects 0 tests or the runner discovers 0 gates."""
    repo_root = db_path.parent.parent
    gaps: list[str] = []
    messages: list[str] = []

    # 1) pytest collection must find >0 tests
    result = subprocess.run(
        [sys.executable, "-m", "pytest", "--collect-only", "-q", str(repo_root)],
        capture_output=True,
        text=True,
    )
    if result.returncode == 5:
        gaps.append("vacuous-tests")
        messages.append("vacuous-tests: pytest collected 0 tests — zero-test run is RED")
    elif result.returncode not in (0, 5):
        # Any other unexpected failure is also flagged so we never silently pass.
        gaps.append("vacuous-tests")
        messages.append(f"vacuous-tests: pytest collection failed (exit={result.returncode})")

    # 2) gate discovery must find >0 gates
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    gate_files = [
        p for p in gates_dir.glob("*.py")
        if not p.name.startswith("_") and not p.name.startswith("test_redproof")
    ]
    if not gate_files:
        gaps.append("vacuous-gates")
        messages.append("vacuous-gates: No gates discovered — zero-gate run is RED")

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
