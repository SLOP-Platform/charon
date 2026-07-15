tier: economy
difficulty: 3
work_class: ci-infra
branch: feat/fn2-bitemporal-decay
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/memory/bitemporal.py
accept: |
  Build ONE shared bi-temporal decay primitive (BORROW Zep/Graphiti's pattern — valid_from / valid_until /
  learned_at / last_referenced — NOT the graph DB). Apply the SAME primitive to two stores:
  - (a) memory facts: age/last-referenced weighting so stale notes rank lower and route to curation.
  - (b) model-signal ledgers (scorecard / reliability / exhaustion): a model flagged bad on an old date must
    DECAY vs a fresh signal — this fixes GAP-REGISTER B2 (stale scores corrupting the routing/ranking brain).
  FAIL-ON-REVERT: a test where a stale-dated model score is down-weighted vs a fresh one; revert the decay →
  they weigh equal (red). A second test for memory-fact staleness weighting.
scope: Shared primitive; ONE idea fixes both the memory-decay and the ROUTER routing-brain-decay bugs. Ledger
  writes MUST stay behind the bench-grader tamper boundary (coordinate the scorecard-side application with the grader).
ds: After FN1. CROSS-PROJECT: resolves ROUTER gap B2 (model-ledger decay) — note it there; do not double-ticket.
  Owns a NEW file (`bitemporal.py`); the ledger-side wiring is read-only against grader-owned files → no collision.
