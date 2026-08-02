# Review: 215@charon
**PR:** feat(ci): enable ruff S and BLE security rule families
**URL:** https://github.com/SLOP-Platform/charon/pull/215
**Date:** 2026-08-02T04:29:22Z
**Reviewer:** reviewer-Tardis-3528526
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- The `tests/**` blanket glob in `per-file-ignores` suppresses 11 S/BLE rules for ALL future test files, contradicting the claim that "New/untouched files are fully checked." A new test with a dangerous subprocess call (argv form, no shell=True) would be silently exempted by the S603 baseline.
- The ratchet tests only guard the `select` list. No test prevents an attacker from silently widening the `per-file-ignores` baseline — e.g. adding `"src/**" = ["S602"]` would disable shell=True enforcement across all source code without touching `select` or failing any existing test.
- The `test_fail_on_revert_removing_a_family_goes_red` test's second assertion is a tautology (it tests the helper function against a locally-computed list, not the actual config file). Its name implies it validates a revert scenario but the core protection comes only from `test_security_families_are_selected`.
- Prescribed fix: add a ratchet test asserting that `per-file-ignores` contains NO blanket glob pattern other than the explicit `"tests/**"` entry, and that the total key count does not shrink (ratchet floor). Consider narrowing `tests/**` to a file-by-file snapshot like the src baselines, so new test files are fully security-checked.

## Fail-on-revert check
Reverting S/BLE from select would lose flake8-bandit and blind-except enforcement on all non-test files, including the shell=True guard that detects the genuine S602 in acceptance.py.

## Status
Pending Manager dispensation
