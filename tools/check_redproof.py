#!/usr/bin/env python3
"""Redproof gate — every gate must ship a companion negative test.

Adapter around KSF's ``redproof`` detector (vendored verbatim in
``tools/_vendor/ksf_gates/redproof.py``). KSF's detector checks that every
gate in ``tools/_vendor/ksf_gates/`` has a corresponding red-proof test in
``.ksf/gates/test_redproof_<gate>.py``, and that each such test passes.

For Charon, no modules list is provided (``modules=[]`` — Charon has no
KSF module.toml registrations), so the module-level red-proof check is a
no-op. Gate-level red-proof scanning uses the vendored gates directory.

Exit 0 on clean (all gates have passing red-proof tests), 1 on any missing
or failing red-proof test.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_gates.redproof import check_redproof  # noqa: E402
from tools.gate_contract import emit_work_units  # noqa: E402


def main() -> int:
    shim_db_path = REPO_ROOT / "_ksf_shim" / "state.db"
    result = check_redproof(db_path=shim_db_path, manifest={}, modules=[])

    # Work units = gate files scanned for red-proof presence
    gates_dir = REPO_ROOT / "tools" / "_vendor" / "ksf_gates"
    gate_count = len([
        p for p in gates_dir.glob("*.py")
        if not p.name.startswith("_") and not p.name.startswith("test_redproof")
    ]) if gates_dir.exists() else 0
    emit_work_units(gate_count)

    for msg in result.messages:
        print(msg)

    if result.passed:
        print("check_redproof: OK")
        return 0

    print("\nFAIL: redproof gate(s) have no or failing negative test", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
