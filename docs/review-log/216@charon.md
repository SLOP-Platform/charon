# Review: 216@charon
**PR:** docs(review-log): GATEWAY-GRADE-ORDER-MVP fragment — decision + accept-test mapping
**URL:** https://github.com/SLOP-Platform/charon/pull/216
**Date:** 2026-08-02T04:27:47Z
**Reviewer:** reviewer-Tardis-3528493
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- `_reorder`'s sort key third element is always `0`, so model_list chain order is never used as a tiebreaker when grades and confidence are equal — the documented "stable sort preserves chain order on ties" invariant is broken; `sorted()` with a key function is not guaranteed stable in Python
- The defect is masked in all existing tests: cold-start tests use an empty store (exits `_pick` early before `_reorder` is called), and grade-tie + confidence-tie scenarios are not exercised
- `uninstall_grade_overlay` fallback closes `_Passthrough` over `ml` captured at uninstall time — stale reference if router mutates after uninstall

## Fail-on-revert check
The cold-start tests (`TestByteIdenticalColdStart`) pass but do not exercise the `_reorder` path, so a revert that also removed `_reorder`'s tiebreaking logic would not be caught by the test suite

## Status
Pending Manager dispensation
