# FREE-TIER-QUOTA-ROUTING — review fragment

## What landed

A quota-aware free-tier router layered onto the existing `routing_policy`
package without modifying it:

- `src/charon/routing_policy/free_tier.py` — `FreeTierLedger` (per-provider
  quota ledger wrapping `charon.quota.QuotaTracker`), `order_chain_free_first`
  (the selection rule), `FreeTierPolicy` (a `Policy` implementation), and the
  TSV seed loader (`load_tsv_seed`, `_limit_from_row`).
- `tests/test_free_tier_quota.py` — 38 hermetic DONE-contract tests
  (injectable clocks, mock routes, no network).
- the repo TSV seed (``FREE-TIER-LIMITS.tsv``) — the operator-verified seed (dated
  2026-07-22 figures, reconciled 2026-08-01).

## Selection rule (the wire)

`order_chain_free_first` returns four preference buckets, in order:

1. FREE legs with known headroom — most headroom first.
2. PAID legs — ordered by `cost_rank` (`cost_rank_key`), fall through unchanged.
3. FREE legs with UNKNOWN limits — surfaced, not preferred, not dropped.
4. FREE legs at/exceeding a known limit — last resort only; re-admitted at
   window rollover automatically (rollover ⇒ headroom > 0 ⇒ back to bucket 1).

This keeps the ANTI-OVER-BLOCK guarantee (DONE contract (c)) and the
"skip BEFORE the 429, never after" rule (DONE contract (b)): an exhausted
free leg is never sent to while a paid leg can serve.

## Defects fixed from the first committed attempt

A prior commit (`114ef47`) had the shape right but four real defects, all
found by reading + RED proof, none caught by the original tests:

1. **`_LIMIT_PATH` resolved 3 parents up → a nonexistent `src/…` state dir.**
   Default `from_tsv()` silently loaded NO limits — the gateway would never
   see the seed.  Fixed to `Path(__file__).resolve().parents[3]` (repo root).
   Regression test: `test_default_seed_path_resolves_to_repo_tsv`.
2. **Exhausted free legs sorted BEFORE paid legs.** A request would hit the
   exhausted free leg first (a 429) whenever all free legs were spent —
   directly violating DONE (b) "skipped before the request is sent" and (c)
   "falls back to the cheapest paid leg".  Paid bucket now precedes the
   exhausted bucket.  New tests: `test_free_leg_at_limit_never_precedes_paid`,
   strengthened `test_all_free_exhausted_falls_back_to_paid`.
3. **`mistral` `1000000000_per_month` was unparseable** → the LARGEST free
   budget silently treated as "unknown".  `_parse_window_value` now maps
   `N_per_month` cells to the calendar `tmo` window.  Tests:
   `test_parse_window_value_suffixed_month`, `test_load_tsv_seed_parses_suffixed_month`,
   `test_ledger_from_tsv_mistral_monthly_is_known`,
   `test_remaining_quota_calendar_monthly_window`.
4. **Dead classification loop** in `order_chain_free_first` (three branches
   appending identically) and a docstring claiming a `limit_drift` counter
   that was never bumped.  Cleaned up; `reconcile_from_observed` now bumps
   `limit_drift` on seed-vs-observed disagreement, and
   `record_headers`/`header_inventory` deliver the "which providers emit
   which headers" fly-blind inventory the ticket calls for.

## DONE contract coverage (RED then GREEN)

- (a) headroom leg chosen over near-limit leg — + revert-is-red.
- (b) at-limit free leg deprioritised; never precedes a paid leg — + revert-is-red.
- (c) all-free-exhausted falls back to cheapest paid leg, reached BEFORE the
  exhausted free legs — + cost_rank_key test.
- (d) exhausted distinct from faulty; re-admitted at window rollover.
- (e) unknown-limit provider surfaced, after known-headroom legs, after paid
  legs (not preferred as unlimited, not dropped).

## Dogfood

Headroom reporting works per provider via `remaining_quota` /
`get_headroom`; the ledger is provider-keyed so nvidia / mistral /
google-aistudio / groq / cerebras all report headroom (or None for the
unpublished-limit ones, which are surfaced via `is_unknown_limit`).  Live
limit discovery is wired via `reconcile_from_observed` + `record_headers`
(observed > our accounting > TSV seed; drift bumps `limit_drift`).

## Notes / out of scope

- Per-provider ledger granularity (ticket: "per (provider, window)");
  per-(provider, model) widening is a noted follow-up in quota.py.
- Response-header parsing inventory is recorded but the header→limit
  extraction itself is the forwarder/consumer's job.
- No re-derivation of limits: all figures come from the operator-verified
  seed, reconciled on 2026-08-01.
