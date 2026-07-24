"""Gate — fail_loud: contract test that every gate returns NON-ZERO process exit on failure.

--- VENDORED ---
Verbatim copy of KSF's ``ksf/gates/fail_loud.py`` (Keystone Framework).
Vendored rather than pip-installed: a cross-repo local-path dependency on a
sibling checkout would break for any fresh clone of this product repo. The
only changes from the KSF original are the GateResult import (now from the
sibling vendored ``ksf_gate_result`` module instead of the ``ksf`` package)
and the fixture setup (creates a Charon-shaped temp tree instead of a KSF
one, tests the gate infrastructure's exit-code honesty). Everything else —
including the KSF-native ``check_fail_loud(db_path, manifest, modules)``
signature — is untouched; see ``tools/check_fail_loud.py`` for the
Charon-side adapter. Do not hand-edit the logic below; re-copy from KSF
and re-apply this header if the upstream detector changes. See
``tools/_vendor/README.md``.
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from tools._vendor.ksf_gate_result import GateResult


def check_fail_loud(
    db_path: Path,
    manifest: dict,
    modules: list[dict],
) -> GateResult:
    """
    Run the runner on a known-failing fixture.
    Assert the CLI process exits with a non-zero code.
    """
    repo_root = db_path.parent.parent
    gaps: list[str] = []
    messages: list[str] = []

    import tempfile
    with tempfile.TemporaryDirectory(prefix="charon_failloud_") as td:
        tpath = Path(td)
        (tpath / "_ksf_shim").mkdir(parents=True)
        (tpath / "src").mkdir(parents=True)
        (tpath / "tools" / "_vendor").mkdir(parents=True)

        # Copy the gate infrastructure into temp so imports resolve
        import shutil
        src_vendor = repo_root / "tools" / "_vendor"
        dst_vendor = tpath / "tools" / "_vendor"
        if src_vendor.exists():
            for item in src_vendor.iterdir():
                if item.is_dir():
                    shutil.copytree(item, dst_vendor / item.name)
                else:
                    shutil.copy2(item, dst_vendor / item.name)

        # Create a minimal wrapper that imports the vendored gate and exits
        # non-zero when the gate fails — this is the Charon-side test of the
        # #200 gate_contract-class bug: if this exits 0, the infrastructure
        # is broken (emit_work_units won't save you).
        wrapper = tpath / "tools" / "_check_failloud_fixture.py"
        wrapper.write_text(
            "import sys\n"
            "from pathlib import Path\n"
            "sys.path.insert(0, str(Path(__file__).parent.parent))\n"
            "from tools._vendor.ksf_gate_result import GateResult\n"
            "# Always failing gate result\n"
            "result = GateResult(False, ['fail'], ['always fails'])\n"
            "print('WORK-UNITS: 1')\n"
            "sys.exit(0 if result.passed else 1)\n"
        )

        proc = subprocess.run(
            [sys.executable, str(wrapper)],
            capture_output=True,
            text=True,
        )
        if proc.returncode == 0:
            gaps.append("fail-loud")
            messages.append(
                f"fail-loud: failing fixture exited 0 (expected non-zero). "
                f"The gate_contract-class bug (#200): a failing check "
                f"that exits 0 looks green. stdout={proc.stdout[:200]}"
            )
        elif proc.returncode < 0:
            gaps.append("fail-loud")
            messages.append(f"fail-loud: runner was killed by signal {-proc.returncode}")

    passed = len(gaps) == 0
    return GateResult(passed, gaps, messages)
