#!/usr/bin/env python3
"""Fail-loud gate — runner must exit non-zero on a failing fixture.

Adapter around KSF's ``fail_loud`` detector (vendored verbatim in
``tools/_vendor/ksf_gates/fail_loud.py``). KSF's detector creates a
known-failing gate fixture and verifies that the runner exits with a
non-zero code — catching the exact #200 gate_contract-class bug where a
check that prints FAIL but exits 0 looks green to the merge gate.

Exit 0 on clean (infrastructure correctly forces non-zero on failure),
1 if a failing fixture could exit 0.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_gates.fail_loud import check_fail_loud  # noqa: E402
from tools.gate_contract import emit_work_units  # noqa: E402


def main() -> int:
    shim_db_path = REPO_ROOT / "_ksf_shim" / "state.db"
    result = check_fail_loud(db_path=shim_db_path, manifest={}, modules=[])

    emit_work_units(1)  # always runs 1 fixture

    for msg in result.messages:
        print(msg)

    if result.passed:
        print("check_fail_loud: OK")
        return 0

    print("\nFAIL: fail-loud — failing fixture could exit 0", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
