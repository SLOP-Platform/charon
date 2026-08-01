repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 1
branch: design/blast-tier-enforcement
depends_on:
owns: fleet/state/BLAST-TIER-ENFORCEMENT-DESIGN.md
work_class_note: |
  Operator-set (2026-07-23). ROOT PATTERN this session: norms/ADOPT-decisions exist but nothing
  ENFORCES them, so they fire only when the operator asks. Three coupled gaps share ONE substrate
  (a blast-tier taxonomy); design them together, operator reviews BEFORE any build. High blast
  (touches the merge gate + the grading substrate that DRIVES routing) — hence design-first.
  [[standing-blast-radius-lens]] [[adversarial-review-default-for-droid-prs]] [[security-is-a-ratchet-gate]]
  [[scorecard-live-lane-is-the-ledger]] [[document-model-self-report-lies]] [[eval-system-under-repair]]
accept: |
  DELIVERABLE = fleet/state/BLAST-TIER-ENFORCEMENT-DESIGN.md, a design (NOT a build) for OPERATOR
  REVIEW, covering all three consumers of one shared blast-tier taxonomy:

  1. BLAST-TIER TAXONOMY (the shared substrate). A machine-derivable classification of a change into
     tiers — e.g. doc < tooling/rig < hot-path < money-path < security. Derive it, don't hand-maintain
     it: reuse signals we already have — the `owns:`/`blast` count already computed in claim.sh, path
     patterns (src/charon/forwarder.py|proxy.py|balance.py = hot/money; egress/keys = security), and
     `work_class` (money-path/routing/ci-infra). State the exact rule + where it lives (one function,
     consumed by both the gate and the grader — no second copy).

  2. MANDATORY ADVERSARIAL-REVIEW GATE (executes EVAL-REGISTRY row #61's unbuilt ADOPT — this is NOT a
     new decision, it is wiring a decided-but-inert adopt). For a change at/above a blast threshold, an
     INDEPENDENT adversarial review (recorded: reviewer identity + verdict + findings in docs/review-log/
     or a marker) MUST exist before land/merge. No recorded review on high-blast code = BLOCK, at BOTH
     land.sh AND CI required-check (so a "green" without a review cannot land). Reuse ReviewerCircuitBreaker
     (src/charon/failover.py:73-142) so a review doom-loop trips rather than retries (per #61). ADOPT-FIRST:
     first consult whether branch-protection required-reviews / an existing review bot covers this before
     specifying any hand-roll (AP-12 / hand-roll-never-default apply). Design must answer: what counts as
     an "independent" review when the fleet is one operator + model droids?

  3. MULTI-AXIS REAL-OUTCOME GRADE + BLAST-TIER ROUTING. Today every live row writes MERGE/pass/score=100
     and leaves the ALREADY-MODELED columns (time_s, cost_usd, corrections, tokens_in/out) EMPTY — a
     built-but-not-captured gap. Design:
       (a) POPULATE the existing columns (done.sh + charon-run.sh + a new reject.sh capture path).
       (b) ADD structured axes the scalar score hides: FAIL-CLASS (correctness | method/brief-compliance |
           false-success | latency), BLAST-TIER of the work, DEFECT-SEVERITY, and TRUST-OF-GREEN (did the
           model's PASS survive adversarial review — the single most routing-critical axis: both recent
           minimax-m3-free runs self-reported SUCCESS and both were wrong).
       (c) assign.py routes PER BLAST-TIER, not per scalar: a model is gated OUT of hot-path/money-path/
           security work until it has clean, review-survived high-blast samples. Preserve the existing
           Wilson-interval smoothing (grades.py) — feed it richer inputs, don't replace it.
       (d) "passed the automated gate but review caught a bug" feeds TWO ledgers: a model-trust signal
           AND a gate-blindness finding (the automated gate is blind to that defect class).
     Then a plan to BACKFILL this session's two real outcomes (WORKLOOP-attempt-1 bounce; PRIORITY-
     CONSOLIDATION landed-with-review-caught-bug) WITH these dimensions, not as bare scalars.

  CONSTRAINTS: design-only (spawns build tickets on review); note the CIRCULARITY (a grade substrate
  graded/routed by the same substrate) and how the design avoids it; each build slice is its own
  one-lens ticket. Do NOT mass-build.
scope: |
  Design the shared blast-tier taxonomy + its three consumers (mandatory adversarial-review merge gate
  [executes registry #61], and multi-axis real-outcome grade + blast-tier routing) as ONE coherent
  design for operator review. Root fix for the recurring "norm exists but is not enforced" class.
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Design/eval only; owns one doc.
  - CANDIDATE FOR MANAGER-BUILD (not a free-claim droid): high-blast architecture + the circularity of a
    grade substrate being produced by a model whose grade we don't yet trust. Operator decides executor.
  - sequence: taxonomy first (both other pieces consume it), then the review-gate and the grade/routing
    designs in parallel within the one doc. Build tickets are spawned per-slice AFTER operator review.
