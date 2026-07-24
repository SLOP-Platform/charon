"""Gate (c) — redproof: every gate/module must ship a companion negative test.

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/redproof.py`` (Keystone Framework, a
sibling development checkout — not a runtime or install-time dependency).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only changes from the KSF original are the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package)
and the gates_dir path (``ksf/gates/`` -> ``tools/_vendor/ksf_gates/`` so the
detector finds Charon's vendored copies). Everything else — including the
KSF-native ``check_redproof(db_path, manifest, modules)`` signature — is
untouched; see ``tools/check_redproof.py`` for the Charon-side adapter that
supplies those KSF-shaped arguments. Do not hand-edit the logic below;
re-copy from KSF and re-apply this header if the upstream detector changes.
See ``tools/_vendor/README.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools._vendor.ksf_gate_result import GateResult


def _run_pytest(test_path: Path) -> int:
    result = subprocess.run(
        [sys.executable, "-m", "pytest", str(test_path), "-q"],
        capture_output=True,
        text=True,
    )
    return result.returncode


def check_redproof(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    repo_root = db_path.parent.parent
    gates_dir = repo_root / "tools" / "_vendor" / "ksf_gates"
    proofs_dir = repo_root / ".ksf" / "gates"
    gaps: list[str] = []
    messages: list[str] = []

    # 1) For each gate in tools/_vendor/ksf_gates/, look for red-proof test in .ksf/gates/
    gate_files = []
    if gates_dir.exists():
        gate_files = [
            p for p in gates_dir.glob("*.py")
            if not p.name.startswith("_") and not p.name.startswith("test_redproof")
        ]

    for gfile in gate_files:
        gate_name = gfile.stem
        rp_test = proofs_dir / f"test_redproof_{gate_name}.py"
        if not rp_test.exists():
            gaps.append("never-gone-red")
            messages.append(f"never-gone-red: gate '{gate_name}' missing {rp_test.name}")
            continue
        # The red-proof test must itself PASS (it asserts non-zero exit on known-bad input)
        rc = _run_pytest(rp_test)
        if rc != 0:
            gaps.append("redproof-failed")
            messages.append(f"redproof-failed: {rp_test.name} did not pass (exit={rc})")

    # 2) For each module, test_redproof.py must exist and pass
    for mod in modules:
        mod_name = mod["name"]
        mod_toml: Path | None = None
        for candidate in repo_root.rglob("module.toml"):
            if f'name = "{mod_name}"' in candidate.read_text():
                mod_toml = candidate
                break
        if mod_toml is None:
            continue
        rp = mod_toml.parent / "test_redproof.py"
        if not rp.exists():
            gaps.append("never-gone-red")
            messages.append(f"never-gone-red: module '{mod_name}' missing test_redproof.py")
            continue
        rc = _run_pytest(rp)
        if rc != 0:
            gaps.append("redproof-failed")
            messages.append(f"redproof-failed: module '{mod_name}' test_redproof.py failed (exit={rc})")

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
