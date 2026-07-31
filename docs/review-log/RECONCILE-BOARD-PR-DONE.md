# RECONCILE-BOARD-PR-DONE — review note

## What this does
Standalone check composing reconcile-merged.sh's branch/owns indexing. Detects
three drift classes and the AMBIGUOUS N>1 owns-overlap wedge:
- R-A: merged PR but ticket not done (RED)
- R-B: merged PR with no ticket and no board file (RED)
- R-C: stale branch with no activity (WARN)
- AMBIGUOUS: N>1 owns overlap, resolved via ladder (branch > title/commit > sha-ledger > NEEDS-MANUAL-ADJUDICATION)

## Adversarial review findings
The AMBIGUOUS ladder implements the ordered proof chain from
UNIFIED-RECONCILIATION-GATE-DESIGN §1.1. It NEVER auto-closes on hash guess.
The check is standalone, wireable per REVISION-2. Fail-on-revert tests cover
all three drift classes plus the ambiguous wedge.

## Implementation note
Indexing logic replicated from reconcile-merged.sh (same awk-based branch/owns
pre-pass). The check does not modify state — it's a detector only.

## Stass-allie WLS-7 validation cited
Implement-as-pattern sanctioned: K8s/Terraform desired-vs-observed; no external
tool reconciles Charon's own state. This file is the per-ticket review-log
fragment per the fleet review-gate convention.
