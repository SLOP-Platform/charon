# GW-BRIDGE-2-METERING-SPEND — Review log

- **Ticket:** GW-BRIDGE-2-METERING-SPEND
- **Branch:** feat/gw-bridge2-metering-spend
- **Owner:** gw-bridge2-metering-spend session

## Summary

BRIDGE 2 of 4.  Implements the litellm cost callback as a VERIFY-ONLY
CROSS-CHECK (ADR-0020 Accepted verify-only).  Charon's own cost computation
REMAINS the source of record advancing BalanceTracker + drain-then-park.

The callback runs alongside Charon's authoritative accounting; its ONLY job
is to surface divergence — it must NEVER override, correct, or reorder
Charon's authoritative spend / drain-then-park.

### Files created

- `src/charon/litellm_plane/metering.py` — verify-only cost cross-check module
- `tests/test_gw_bridge2_metering.py` — acceptance tests (fail-on-revert)

### Key design decisions

1. **No edit to litellm_router.py** — the module is a sibling that provides
   pure functions and a wrapper entry point (`classify_and_crosscheck`).
   The existing `make_router` / `complete_via_router_guarded` are untouched.
2. **No BalanceTracker mutation** — every function in metering.py is pure
   observation; none calls `record_spend`, `record`, `park`, or `drain`.
3. **Divergence threshold** — $0.001 absolute; below this, costs are treated
   as equal.  Configurable via `_COST_TOLERANCE`.
4. **Dual extraction** — `litellm_cost()` reads from the raw ModelResponse;
   `charon_cost()` reads from a ProxyObservation.  Both understand dict and
   object inputs.

### Acceptance criteria verified

| # | Criterion | Test | Assertion |
|---|---|---|---|
| 1 | AUTHORITY UNCHANGED | `test_authority_unchanged` | `crosscheck_observation` does not call any money-path mutation |
| 2 | DIVERGENCE SURFACED | `test_divergence_surfaced` | delta > tolerance logs WARNING; delta within tolerance stays quiet |
| 3 | NO CORRUPTION | `test_no_corruption_non_token` | zero litellm cost + zero charon cost => no divergence, no mutation |
