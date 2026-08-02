# Review: 397@charon-private
**PR:** docs: wire inert-checks — full wiring plan for 9 inert checks + G4 gaps + graphify affected
**URL:** https://github.com/Nnyan/charon-private/pull/397
**Date:** 2026-08-02T05:07:56Z
**Reviewer:** reviewer-tab-2793510
**Author:** frontier-2788767

## Verdict
NEEDS-REVISION

## Findings
- **CRITICAL — Self-inconsistent scope claim**: Both docs' "9 INERT CHECKS" header counts `selfcheck-cycle.sh` as inert (in need of wiring), yet Section 9 explicitly states it is "NOT INERT — already wired through gate.sh's test glob." The "9" is wrong; it should be "8 INERT CHECKS" (or "8 + 1 already-wired"). The PR's own analysis contradicts its own scope header.
- **MODERATE — Egress canary ambiguity**: `egress-key-canary.sh` is listed in the "9 inert checks" wiring table as needing wiring, but the section says "STATUS: NOT INERT — already wired via gate.sh" for `selfcheck-cycle.sh`. No equivalent "NOT INERT" marker is given for egress-key-canary, yet the section notes "product copy" and "product CI" — this creates ambiguity about whether the inertness finding is scoped to the fleet copy only.
- **MODERATE — PART 5 omits the selfcheck-cycle correction**: "What this ticket can actually do" lists only 3 actions but never notes that it has *already corrected* the selfcheck-cycle status in the negative (it's not inert), which is itself a finding worth explicit closure in the disposition.
- **LOW — Inconsistent framing of Faktory fix ownership**: The review log says "corrective: update the test docstring" but the state doc says "owner: PROOF-SUITES-ENFORCE or a sibling ticket — not this one." No ticket ID is referenced for the corrective action, leaving a dangling finding with no assignee.

## Fail-on-revert check
A revert would lose the documentation findings (scope mismatch, selfcheck-cycle already-wired, G4 gaps, graphify-affected dependency), even though the docs contain a critical self-inconsistency that must be corrected before they serve as a reliable implementation plan.

## Status
Pending Manager dispensation
