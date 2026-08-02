repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: ci-infra
branch: feat/cost-per-task-replay
depends_on:
owns: fleet/state/COST-PER-TASK-REPLAY.md, docs/review-log/COST-PER-TASK-REPLAY.md
serial_justified: |
  One metric with one denominator. A split that computes spend separately from acceptance
  produces two numbers neither of which is the metric.
substrate: N/A
substrate-novel: |
  Every input is already adopted: the board's landed tickets, the launcher's per-ticket gate
  result and model chain, review verdicts, assign.py real-outcome ranking, the live
  model-scorecard. Nothing new is measured. The novel slice is the JOIN — spend to ticket to
  outcome — and the selection policy that keeps the sample representative.
accept: |
  OPERATOR-DIRECTED 2026-08-02, recommendation accepted: do NOT build a synthetic benchmark
  suite. The rig already recorded that lesson — synthetic S0-S6 was ruled "smoke only; PIVOT to
  real outcomes" and "benchmark is NOT a valid ranker". A synthetic suite drifts from real work
  and then ranks models on a fiction.
  BUILD A REPLAY HARNESS OVER REAL LANDED TICKETS instead. The "representative task sequence" is
  then a SELECTION over real history and cannot drift from the work we actually do.
  THE METRIC — cost per ACCEPTED task:
      (total spend across ALL attempts: every retry, every failover leg, every model tried)
    / (tasks passing ADVERSARIAL REVIEW WITH NO CHANGES REQUIRED)
  The quality floor is load-bearing. Without "no changes required", cheap degenerates into
  "fails cheaply" — measured: 6 of 8 PRs bounced in one review round, several from price-chosen
  models.
  Done contract:
  1. Selection stays representative BY CONSTRUCTION: sample landed tickets across the real
     work_class x difficulty distribution, refresh on a cadence, and GATE on drift between the
     sample and current board composition. That is the mechanical gate that keeps it relevant.
  2. Join spend -> ticket -> outcome. That join is the deliverable; the inputs already exist.
  3. Feed the result into model grading as a model x PROVIDER pair (quantization, hardware and
     hidden prompts make provider part of the identity — see GRADE-MODEL-PROVIDER-PAIR). Price
     informs; it never decides alone.
  4. Report cheapest-per-ACCEPTED-task per work_class x tier — that becomes the routing sort key,
     replacing cheapest-per-token.
  5. Fail-on-revert: a model that passes review but burns 5x tokens must rank WORSE than a
     dearer model that lands first time; assert it on seeded data.

## Dependencies & Sequence

P0. Consumes SPEND-METRIC-TRUSTWORTHY's per-provider attribution — start the selection/replay
half now, join real spend when that lands. Feeds GRADE-MODEL-PROVIDER-PAIR and the routing key.
