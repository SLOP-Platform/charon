repo: charon-private
tier: strong
difficulty: 3
work_class: greenfield-feature
priority: 0
branch: feat/model-grade-preseed
depends_on:
owns: fleet/state/MODEL-GRADE-PRESEED.md
work_class_note: |
  Cold-start BRIDGE for the ranking pipeline (audit 2026-07-23). Today grades.py returns 0 real-outcome
  grades, so CG has NO usable ranking to route on. ADR-0017 §Cold-start (docs/adr/0017:49-54, 121-123) names
  a "seed scorecard / importable scorecard" need but marks it "required design, not yet designed"; a
  grades_import/product_grades seed path is named. External-benchmark data is ALREADY curated in
  fleet/state/MODEL-ROLE-EVALUATION.md. Operator wants a PRELIM prior that real work supersedes.
  [[charon-eval-system-under-repair]] [[benchmark-not-a-valid-ranker]] [[charon-strategy-outcome-graded-gateway]]
accept: |
  Seed a PRELIMINARY per-(model, work_class) prior from legitimate external benchmarks so CG has a usable
  day-1 ordering, structured as a DECAYING PRIOR that real graded outcomes override — NOT a fixed leaderboard
  rank. This resolves the doctrinal tension ([[benchmark-not-a-valid-ranker]] / MODEL-ROLE-EVALUATION.md:203
  "your own signal outranks any leaderboard"): the prior is explicitly provisional and loses weight as real
  outcomes accumulate, so own-signal still wins once it exists.
  1. Import the curated external-benchmark scores (MODEL-ROLE-EVALUATION.md; refresh from legit sources —
     aider-polyglot, LMArena, Artificial Analysis, models.dev) via the ADR-0017 grades_import/product_grades
     seed path (do NOT invent a parallel store).
  2. Tag every seeded score PROVISIONAL with a decay/confidence weight; a real graded outcome for that
     (model, work_class) supersedes/downweights the prior. Never let the prior override real signal.
  3. Verify CG can now produce a non-empty ordering to route on (paired with EVAL-CONTROL-GATE-FIX which
     fixes the real-outcome LOOP — this fixes the COLD-START; both are needed).
  Deliverable = the seeded prior live + the decay/override rule + proof CG ranks day-1.
scope: |
  Seed a provisional external-benchmark PRIOR (decaying, real-work-overridden) via ADR-0017's grades_import
  path so CG has a usable day-1 ranking while real outcomes accumulate. The cold-start bridge; not a
  substitute for the real-outcome loop (EVAL-CONTROL-GATE-FIX) or the product consumer wiring.
ds: |
  ## Dependencies & sequence
  - depends_on: none to seed. Pairs with EVAL-CONTROL-GATE-FIX (loop) — this is the cold-start half.
  - consumer: GATEWAY-GRADE-ORDER-MVP (blocked on GW-CUTOVER-LIVE-WIRE) is what actually routes on the
    ranking — flag that as the downstream unblock for the ranking to reach live routing.
