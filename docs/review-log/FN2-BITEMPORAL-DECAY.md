# FN2-BITEMPORAL-DECAY — review log

## Decision

Created a single shared bi-temporal decay primitive (`bitemporal.py`) in
`/home/stack/charon-private/fleet/memory/`. Borrows Zep/Graphiti's pattern
(valid_from / valid_until / learned_at / last_referenced) without the graph DB.

## Approach

- **decay_weight()**: Exponential-decay blend of valid-time age and
  last_referenced recency. Controlled by `half_life_seconds` (default 7d) and
  `recency_fraction` (0=all valid-time, 1=all recency).

- **Two factory functions**: `memory_fact()` for memory-store entries (no
  predefined expiry), `model_signal()` for model-signal ledgers (caller
  supplies valid_from).

- **touch()**: Bumps `last_referenced` on access — callers tick this when a
  memory fact is used.

- **decayed_rank()**: Sorts records by weight descending for retrieval ranking.

## Scope

- Owns: `/home/stack/charon-private/fleet/memory/bitemporal.py` (NEW)
- Tests: `/home/stack/charon-private/fleet/memory/tests/test_bitemporal.py` (NEW)
- Review fragment: `docs/review-log/FN2-BITEMPORAL-DECAY.md` (this file, NEW)

The module is a READ-ONLY decay calculator — it never writes to any ledger.
Scorecard-side wiring must coordinate with the bench-grader to respect the
tamper boundary (per ticket scope note).

## Fail-on-revert tests

1. `test_stale_model_signal_downweighted_vs_fresh`: 90d-old model score MUST
   weigh less than a 1d-old fresh one. Revert the decay → equal weights (RED).
2. `test_stale_memory_fact_downweighted_vs_recently_referenced`: a fact with
   30d-old last_referenced MUST weigh less than a just-touched one. Revert the
   decay → equal weights (RED).

Both include explicit revert-guard tests that prove the no-decay stub would
assign equal weight.

## Cross-reference

Resolves ROUTER gap B2 (model-ledger decay). The bitemporal.py primitive is
the shared engine — both memory-store and routing-brain consumers wire through
it. Ledger writes stay behind the bench-grader tamper boundary.
