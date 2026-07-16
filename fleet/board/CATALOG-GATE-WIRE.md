repo: charon
tier: economy
difficulty: 2
work_class: ci-infra
branch: feat/catalog-gate-wire
owns: tools/gates.json, src/charon/gate_runner.py, tests/test_catalog_gate_wire.py
serial_justified: One registration of an existing detector into the gate registry + its test; cohesive, nothing to parallelize.
depends_on:
note: |
  Wiring-gap audit (TOOL-WIRING-AUDIT.md, P0): tools/check_catalog_case_quant.py — the mechanized
  catalog case+quantity mismatch detector that directive #30 [[always-fix-catalog-mismatches]] asked
  for — is BUILT + unit-tested but registered NOWHERE (absent from tools/gates.json's 17 gates + from
  gate_runner.py CHECKS), so catalog/routing casing+quantity drift ships SILENTLY. Wire it into the gate
  so `charon.cli gate` (and CI/preflight) runs find_mismatches against the LIVE catalog.
accept: |
  - check_catalog_case_quant registered in tools/gates.json AND gate_runner.py CHECKS; `charon.cli gate`
    invokes it against the live catalog and FAILS on a real casing/quantity mismatch.
  - tests/test_catalog_gate_wire.py: seed a catalog mismatch -> gate RED; clean catalog -> GREEN (fail-on-revert).
  - No new detector logic (reuse check_catalog_case_quant.find_mismatches) — this is WIRING only.
