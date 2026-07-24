# KSF-VENDOR-GATES — Vendor 5 KSF anti-theater/completeness gates into Charon

**Date**: 2026-07-24
**Reviewer**: pending (adversarial review required before merge)
**Verdict**: IMPLEMENTED — all gates wired, green, red-proofed.

## Summary

Vendored 5 KSF gates from the keystone project's `ksf/gates/` into
`tools/_vendor/ksf_gates/`, following the same pattern as the existing
`tools/_vendor/ksf_inert_code.py` vendoring. Each gate has:
- A vendored module in `tools/_vendor/ksf_gates/<gate>.py` (verbatim KSF copy
  with only the `GateResult` import path and `gates_dir` path changed)
- A Charon-side wrapper in `tools/check_<gate>.py` (adapter supplying
  KSF-shaped arguments via `_ksf_shim` path)
- A red-proof test in `.ksf/gates/test_redproof_<gate>.py`
- A gate entry in `tools/gates.json` (with `ci_step: true` and `min_work_units: 1`)
- Registration in `src/charon/gate_runner.py` CHECKS

## Changes

| File | Type | Description |
|---|---|---|
| `tools/_vendor/ksf_gates/__init__.py` | new | Package init for vendored gates |
| `tools/_vendor/ksf_gates/redproof.py` | vendor | Every gate must ship a companion negative test |
| `tools/_vendor/ksf_gates/wiring_alignment.py` | vendor | prod-path == test-path alignment |
| `tools/_vendor/ksf_gates/coverage_ssot.py` | vendor | SSOT meta-gate: every declared gate is implemented |
| `tools/_vendor/ksf_gates/no_vacuous.py` | vendor | 0 tests/0 gates = RED |
| `tools/_vendor/ksf_gates/fail_loud.py` | vendor | Runner must exit non-zero on failure |
| `tools/check_redproof.py` | new | Adapter for redproof |
| `tools/check_wiring_alignment.py` | new | Adapter for wiring_alignment |
| `tools/check_coverage_ssot.py` | new | Adapter for coverage_ssot |
| `tools/check_no_vacuous.py` | new | Adapter for no_vacuous |
| `tools/check_fail_loud.py` | new | Adapter for fail_loud |
| `.ksf/manifest.toml` | new | Gate registry for coverage_ssot |
| `.ksf/entrypoints.json` | new | Static entrypoints for wiring_alignment |
| `.ksf/gates/test_redproof_redproof.py` | new | Red-proof: redproof gate |
| `.ksf/gates/test_redproof_wiring_alignment.py` | new | Red-proof: wiring_alignment gate |
| `.ksf/gates/test_redproof_coverage_ssot.py` | new | Red-proof: coverage_ssot gate |
| `.ksf/gates/test_redproof_no_vacuous.py` | new | Red-proof: no_vacuous gate |
| `.ksf/gates/test_redproof_fail_loud.py` | new | Red-proof: fail_loud gate |
| `src/charon/gate_runner.py` | edit | Registered 5 new checks in CHECKS (line 49-53) |
| `tools/gates.json` | edit | Added 5 new gate entries |
| `tests/test_ksf_vendor_gates.py` | new | 16 fail-on-revert tests (all green) |

## Decisions

1. **Vendor, don't depend**: All 5 gates are vendored verbatim from KSF with
   the same shim pattern as the existing `ksf_inert_code.py` (change only
   `GateResult` import path). No pip-install dependency on keystone.

2. **Path shim**: KSF expects `ksf/gates/` → Charon uses `tools/_vendor/ksf_gates/`.
   The vendored modules use the latter path. The `_ksf_shim/state.db` synthetic
   path trick (db_path.parent.parent = repo_root) is reused from check_inert_code.py.

3. **Separate domains**: Each gate has its own unique domain in gates.json
   (redproof, wiring-alignment, coverage-ssot, no-vacuous, fail-loud) to avoid
   DOMAIN-OVERLAP in the gate registry checker.

4. **EXTENDS, not replaces**: Does not touch the reconcile-gate-wired script
   (RECONCILE-GATE-WIRED owns it) — these are complementary engines for
   different axes (Python-AST reachability vs bash/fleet firing).

5. **fail_loud adaptation**: The KSF version uses `ksf.cli gate` but Charon
   has no such CLI. The vendored version creates a temp fixture that tests
   the GateResult→exit_code pipeline directly, catching the #200 bug class.

## Verification

```bash
# All 2286 tests pass
PYTHONPATH=src python3 -m pytest -q   # 2286 passed, 0 failed

# Ruff clean
ruff check   # All checks passed!

# Mypy clean
mypy src tests   # No issues found

# Boundary clean
python3 tools/check_boundary.py src   # OK

# Version check (note: stale editable metadata is pre-existing noise)
python3 tools/check_version.py   # OK

# All 5 gate wrappers exit clean
python3 tools/check_redproof.py && echo OK
python3 tools/check_wiring_alignment.py && echo OK
python3 tools/check_coverage_ssot.py && echo OK
python3 tools/check_no_vacuous.py && echo OK
python3 tools/check_fail_loud.py && echo OK
```

## Open items

- `ALL_DOMAINS` in `tools/check_gate_registry.py` does not include the 5 new
  domains. This is outside our owns — a follow-up ticket should register them.
  The gate registry prints "Unknown domains (not in ALL_DOMAINS)" as an
  informational note, not an error.

- Adversarial review required before merge: a different reviewer must verify
  the `src/charon/gate_runner.py` CHECKS registration is complete and correct.
