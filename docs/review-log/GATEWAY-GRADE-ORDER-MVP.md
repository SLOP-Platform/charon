# GATEWAY-GRADE-ORDER-MVP — review log

## Decision

Build the NOVEL outcome-grade slice as ONE inseparable seam: a neutral
product-side grade store (`product_grades.py`) + a grade-ordering overlay
wired into `litellm.Router.set_custom_routing_strategy` (`grade_order.py`).
Splitting them across tickets recreated the build-against-a-changing-API
defect (overlay built before the store it queries), so they ship together.

## What was built

- `src/charon/capability/product_grades.py` — NEUTRAL product-owned grade
  format (NOT the rig `model-scorecard.tsv`). Stdlib-only. JSON on-disk
  schema with `version`, `entries` (refuse-on-empty, per-`(model,
  work_class)` key, coarse A–F band). `load_cached` is the canonical
  hot-path reader (memoised per resolved path; no per-request parse).
  Imports NO fleet code (rig→product leak boundary enforced by an AST
  guard test).
- `src/charon/routing_policy/grade_order.py` — `GradeOrderStrategy`
  implements BOTH `get_available_deployment` (sync) and
  `async_get_available_deployment` (async) with the same reorder-by-grade
  logic. Wired via `Router.set_custom_routing_strategy` (the LIVE routing
  decision hook). Keyed by the existing deterministic
  `WorkClassTaxonomy.classify_request`. FAIL-OPEN: empty/missing grades
  file → byte-identical chain order. Cooldown/blocked/health filtering
  preserved (delegates to Router's own helpers). Never-introduces-
  unlisted-id (only reorders `router.model_list` candidates).

## Acceptance tests (the minimum bar — both met)

1. GRADE ORDERS — `TestGradeOrdersReorderCandidateSet`: a fixture store
   where grade-A is the 2nd-cheapest and grade-F is cheapest → overlay
   attempts A-FIRST. Proven by asserting the ORDER the Router attempts
   (`get_available_deployment` return value's `litellm_params.model`),
   not a function-call stub. Revert (empty store) → F-first → the
   `test_revert_to_chain_order_picks_cheapest_first` RED.
2. BYTE-IDENTICAL COLD START — `TestByteIdenticalColdStart`: no grades
   file → overlay returns `candidates[0]` (chain order), byte-identical
   to the no-overlay path. Missing file → shared EMPTY sentinel (never
   strands). `test_overlay_strands_when_grades_file_is_empty` pins the
   refuse-on-empty contract (empty file raises, not silently no-ops).

## Adversarial invariants (reviewer confirm)

- Grade load is CACHED: `load_cached` memoises per resolved path; the
  overlay's per-routing-decision lookups never re-parse the file
  (`TestLoadCached.test_caches_per_path`).
- No test asserts against a pre-mocked ordering: tests drive a REAL
  `litellm.Router` and observe the attempt order via the actual
  `get_available_deployment` method the Router calls on every request.
- Never-introduce-unlisted-id: `TestNeverIntroducesUnlistedId` asserts
  the returned deployment is in `router.model_list`.
- Cooldown honoured: `test_attempt_order_is_a_then_f_across_repeated_calls`
  drives the REAL `cooldown_cache.add_deployment_to_cooldown` and proves
  the overlay reads it back.
- Unknown work-class → `general` fallback (never-strand): pinned by
  `TestUnknownWorkClassDefaultsToGeneral`.
- Sync/async parity: `TestAsyncPathMirrorsSync`.

## Dependency note

`depends_on: GW-CUTOVER-LIVE-WIRE`. The cutover ticket landed as a STOP
("land the guards, not the wire-in") — but the litellm.Router plane it
unblocks (GW-BRIDGE-1..4, already merged) exposes the
`set_custom_routing_strategy` / `cooldown_cache` surface this overlay
hooks into. Verified live: `Router` has `set_custom_routing_strategy`,
`_reset_custom_routing_strategy`, and `cooldown_cache` in the current
tree. The overlay's attach point is real and served.

## Gate

2475 passed, 3 skipped, 1 xfailed, 1 xpassed. ruff clean. mypy clean.
boundary + version checks clean.
