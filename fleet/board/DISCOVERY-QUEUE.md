repo: charon-private
tier: strong
difficulty: 2
work_class: generalist
priority: 1
branch: feat/discovery-queue
depends_on:
owns: fleet/discovery/queue.py, fleet/state/discovery-review.tsv
note: |
  D4 of the DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN §3a/§3d/§3e, operator-approved P1, 2026-07-23).
  The human-review approval QUEUE + weekly board digest. REUSE-FIRST: mirror the existing
  discover.py::import_openrouter_models "fuzzy match -> manual review queue" pattern (discover_review.json)
  — a review file, NOT auto-apply. Discovery PROPOSES; a human+eval disposes (D5). [[real-work-is-the-trust-test]]
accept: |
  A review queue that consumes D3's NEW/CHANGED/GONE and stages them for human review — NEVER auto-wires:
    1. `fleet/state/discovery-review.tsv` — one row per candidate/alert; status ∈ {candidate, reviewing,
       approved, rejected, configured, gone}; DEDUP against prior dispositions (a rejected row carries a
       reason so the next cycle does not re-surface it).
    2. **Weekly board digest** — a rolled-up "NEW candidates / DRIFT alerts / GONE" batch to the board
       (don't page the operator daily; §3d cadence).
    3. **OUTAGE-RISK escalation** — a configured provider gone / free tier removed BREAKS the weekly
       cadence and alerts immediately (availability event).
  Mirrors the discover_review.json queue concept (review file, not auto-apply).
  FAIL-ON-REVERT: feed a CANDIDATE then the same candidate again -> deduped (one row); a REMOVED for a
  configured provider -> immediate OUTAGE-RISK escalation, not batched. Revert the dedup or the
  escalation branch -> RED.
  NON-VACUOUS: a queue run that examined ZERO delta records must RED, never report "nothing to review".
  RUNNER-REACHABLE: the red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  `fleet/tests/*.test.sh` glob or rig-ci-scope.sh CI_SUITES).
scope: |
  Build the discovery-review.tsv queue + weekly digest + OUTAGE-RISK immediate escalation, dedup against
  prior dispositions. Reuses the discover_review.json review-file pattern. Approval actuation is D5.
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. The DISCOVERY-DIFF edge was REMOVED 2026-07-24 and it was NOT a real build prereq:
    D4 consumes D3's NEW/CHANGED/GONE delta records, whose shape is specified in
    FREE-PROVIDER-DISCOVERY-DESIGN §3b/§3d, and this ticket's red-proof feeds HAND-WRITTEN candidate and
    REMOVED fixtures — it never executes offer_diff.py. Owns are disjoint (queue.py +
    discovery-review.tsv vs offer_diff.py). It was a data-format contract, not a code dependency.
  - feeds: DISCOVERY-APPROVAL-WIRE (D5) reads approved rows — also NOT a board edge, same reason.
  - reuse: discover.py/discover_review.json review-queue pattern.
  - concurrency: disjoint new files (queue.py + its own discovery-review.tsv). Safe to build in parallel
    with D2/D3/D5/D6.
  - UN-BUNDLED 2026-07-24: briefly absorbed into a DISCOVERY-PIPELINE mega-ticket; reverted. Grouping is
    one ROADMAP wave (`discovery-leg`) at one priority, not one serial ticket.
