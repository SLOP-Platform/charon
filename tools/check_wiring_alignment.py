#!/usr/bin/env python3
"""Wiring-alignment gate — production-path == test-path.

Adapter around KSF's ``wiring_alignment`` detector (vendored verbatim in
``tools/_vendor/ksf_gates/wiring_alignment.py``). KSF's detector reads
entrypoints from ``pyproject.toml`` and ``.ksf/entrypoints.json``, then
verifies that each entrypoint module has a corresponding ``import`` or
``from`` statement in the test suite (``tests/``).

Exit 0 on clean (every entrypoint has a test import), 1 on any entrypoint
with no test import.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_gates.wiring_alignment import check_wiring_alignment  # noqa: E402
from tools.gate_contract import emit_work_units  # noqa: E402


def main() -> int:
    shim_db_path = REPO_ROOT / "_ksf_shim" / "state.db"
    result = check_wiring_alignment(db_path=shim_db_path, manifest={}, modules=[])

    # Count entrypoints checked
    import json
    import tomllib

    entrypoints_count = 0
    pyproject = REPO_ROOT / "pyproject.toml"
    if pyproject.exists():
        try:
            data = tomllib.loads(pyproject.read_text())
            scripts = data.get("project", {}).get("scripts", {})
            entrypoints_count += len(scripts)
        except Exception:
            pass
    ep_file = REPO_ROOT / ".ksf" / "entrypoints.json"
    if ep_file.exists():
        try:
            with ep_file.open() as f:
                eps = json.load(f)
                if isinstance(eps, dict):
                    entrypoints_count += len(eps)
        except Exception:
            pass
    emit_work_units(entrypoints_count)

    for msg in result.messages:
        print(msg)

    if result.passed:
        print("check_wiring_alignment: OK")
        return 0

    print("\nFAIL: entrypoint(s) have no test import", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
