repo: charon-private
tier: strong
difficulty: 2
work_class: generalist
priority: 1
branch: feat/discovery-queue
depends_on: DISCOVERY-DIFF
dep-kind: build
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
  configured provider -> immediate OUTAGE-RISK escalation, not batched.
scope: |
  Build the discovery-review.tsv queue + weekly digest + OUTAGE-RISK immediate escalation, dedup against
  prior dispositions. Reuses the discover_review.json review-file pattern. Approval actuation is D5.
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-DIFF (real build dep — queues its NEW/CHANGED/GONE output).
  - feeds: DISCOVERY-APPROVAL-WIRE (D5) reads approved rows.
  - reuse: discover.py/discover_review.json review-queue pattern.
  - concurrency: disjoint new files (queue.py + its own discovery-review.tsv).
