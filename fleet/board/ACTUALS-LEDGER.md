tier: strong
difficulty: 3
work_class: greenfield-feature
branch: feat/actuals-ledger
depends_on:
owns: src/charon/capability/actuals.py, src/charon/capability/scorecard.py, tests/test_actuals_ledger.py
accept: |
  Every headless sub-session outcome appends one row to a VERSIONED append-only scorecard artifact
  (scorecard.v{n}.json), keyed by (model, work_class), from deterministic byproducts (run result,
  packet-parses, fail-on-revert+gate pass/fail, failover hops, tokens/wall). Manager accept/reject
  stored as a SEPARATE low-weight column (D2). Reader returns the latest FROZEN artifact with a
  last-known-good fallback. Fail-on-revert: corrupt the latest artifact -> reader falls back to
  last-known-good (test RED if fallback removed).
scope: |
  The real-outcomes ranker (GATEWAY-PROGRAM §1.2). Freeze-ring seam (red-team fix #2): the rig grader
  writes artifacts; product reads frozen versions only. NO `import benchmark`/`grader_daemon` on the
  product hot path (enforced by CI import-guard — see WORKCLASS-TAXONOMY/DIFFICULTY sibling gate).
ds: Wave 1 scaffold. Foundation for EXPLORE-PROMOTE + CAPABILITY-ENGINE. Disjoint (new files).
