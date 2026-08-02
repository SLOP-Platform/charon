# Review: 222@charon
**PR:** docs(review-log): correct PYLINT-UNUSED-ARGS baseline note (46 product; ksf in separate checkout)
**URL:** https://github.com/SLOP-Platform/charon/pull/222
**Date:** 2026-08-02T15:07:15Z
**Reviewer:** reviewer-tab-2541120
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- CRITICAL: `TestBaselineCountSanity.test_product_tree_has_findings` (line 191) has a logically broken assertion: `assert result.returncode != 0 or "W0613" in result.stderr` — passes on any non-zero exit for any reason, does not verify W0613 is actually found. The second disjunct `"W0613" in result.stderr` is also dead code since pylint reports W0613 on stdout, not stderr. This completely defeats the stated purpose of proving the product tree has unused-argument findings at baseline (~46). The session report confirms `RED-PROOF: broken=1`.
- MINOR: `tests/test_pylint_unused_args.py` lacks a trailing newline at EOF.
- MINOR: `_ruff_check` (line 25) omits `capture_output=True`, unlike `_run_pylint` — inconsistent, and with inherited stdout/stderr the ruff output leaks to the test runner's terminal.

## Fail-on-revert check
A revert would remove the test file but the broken baseline sanity assertion would not catch the regression of losing W0613 detection in the gate, since it passes on any non-zero pylint exit.

## Status
Pending Manager dispensation
