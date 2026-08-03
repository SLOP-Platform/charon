# REVIEW-DISPENSATION-CANARY — Review / Decision Log

## What this ticket does
Implements the "review" plane dogfood canary per DESIGN-PLANE-CANARY-SUITE.md Phase 3 P5.
Drives `fleet/checks/reconcile-review-gate.sh` (RECONCILE-REVIEW-GATE, unmodified) against
seeded fixture state at `fleet/state/reviewed/REVIEW-DISPENSATION-CANARY`, testing the
#200 self-review class (reviewer == author_model on the same marker → BLOCK).

## Fixture path chosen
`fleet/state/reviewed/REVIEW-DISPENSATION-CANARY` — follows the pattern of other canary
fixtures using the ticket-id as the marker filename.

## Test classes covered
- (a) reviewer == author_model (self-review) → RED (#200 class)
- (b) stale reviewed_sha → RED (R-K composite smoke)
- (c) hot-path merge with no review fragment → RED (R-J)
- GREEN: distinct reviewer, matching sha, fragment present → GREEN
- (e) fail-on-revert: revert self-review marker → (a) goes RED (proves non-tautology)

## Registry verification
`fleet/plane-canary-registry.tsv` row for `review` already seeded by PLANE-CANARY-REGISTRY
at `fleet/tests/review-dispensation-canary.test.sh` — no separate registration edit needed.

## Design doc reference
"folds into RECONCILE-REVIEW-GATE" — did not fork a second checker.
Fails are R-J/R-K classes, all already implemented in the owned check.
Self-review (reviewer == author_model) check at reconcile-review-gate.sh:252-257.
