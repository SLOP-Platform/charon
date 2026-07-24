#!/usr/bin/env python3
"""Coverage-SSOT gate — every declared gate is implemented AND wired.

Adapter around KSF's ``coverage_ssot`` detector (vendored verbatim in
``tools/_vendor/ksf_gates/coverage_ssot.py``). KSF's detector reads the
gate manifest from ``.ksf/manifest.toml``, auto-discovers implementations
in ``tools/_vendor/ksf_gates/``, and classifies each rule as mechanized,
guidance, or GAP. The gate fails on any GAP or mechanized rule that has no
implementation.

Exit 0 on clean (full coverage), 1 on any coverage gap or missing
implementation.
"""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from tools._vendor.ksf_gates.coverage_ssot import check_coverage_ssot  # noqa: E402
from tools.gate_contract import emit_work_units  # noqa: E402


def _load_manifest() -> dict:
    manifest_path = REPO_ROOT / ".ksf" / "manifest.toml"
    if not manifest_path.exists():
        return {}
    try:
        import tomllib
        return tomllib.loads(manifest_path.read_text())
    except Exception:
        return {}


def main() -> int:
    manifest = _load_manifest()
    shim_db_path = REPO_ROOT / "_ksf_shim" / "state.db"
    result = check_coverage_ssot(db_path=shim_db_path, manifest=manifest, modules=[])

    # Work units = rules in manifest
    gates = manifest.get("gates", {})
    gate_list = gates.get("list", []) if isinstance(gates, dict) else []
    emit_work_units(len(gate_list))

    for msg in result.messages:
        print(msg)

    if result.passed:
        print("check_coverage_ssot: OK")
        return 0

    print("\nFAIL: coverage gap or missing implementation", file=sys.stderr)
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
