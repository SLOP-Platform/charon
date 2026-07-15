# DESTIFF-RECOMMEND — class-level failover for recommend

**Ticket:** DESTIFF-RECOMMEND
**Branch:** feat/destiff-recommend
**Date:** 2026-07-15

## Problem (operator directive 2026-07-15)

The same "stiff single-provider" pattern that bit `decompose_planner` lived
unchanged in `recommend._ask_model`: pick ONE model, hard-fail on a 401/limit/
network problem, and silently hand back a heuristic ranking — even when
other configured providers would have served a valid answer. One dead
provider was enough to zero out a tier recommendation.

## Fix (class-level, via composition — MANAGER-OPERATING-RULES §12)

`recommend_tiers` now routes its model call through
`failover_loop.invoke_with_failover` over the FULL ordered trusted pool,
reusing the existing primitive that `decompose_planner` already consumes.
This is a composition fix, not a bespoke loop — the same transport-vs-quality
classification, the same per-candidate retry, the same exhaustion-with-
recommendation.

### What changed

1. `_ask_model` was refactored from a blanket-`except` "give up" into a
   thin wrapper that calls the new `_post_tier_ranking` transport.
2. New `_post_tier_ranking(model_id, base_url, api_key, prompt)` is the
   per-candidate transport. Mirrors `decompose_planner._post_chat`:
   - PROVIDER-level fault (auth 401/403/407, limit 402/429, infra
     5xx/URLError/timeout) → raise `_TierTransportError` (failure_class +
     status + detail), so the failover loop advances.
   - 200 but the body/content is not a parseable JSON dict → return `None`
     (a parse/quality fault of THIS model → re-prompt the SAME model).
3. `recommend_tiers` now walks up to 3 ordered trusted candidates via
   `invoke_with_failover`, retries each once on a quality fault, and uses
   the first valid ranking. On pool exhaustion it falls back to the
   heuristic ranker (preserving the public return contract).
4. The transport-vs-quality split distinguishes a real "unparseable
   reply" from a "dead provider", so a single bad key no longer zeroes
   the recommendation.
5. The tier-voter path is allowed to use Anthropic models — the
   `SG-never-Anthropic` guard is planner-only (`decompose_planner`) and is
   not added here.

### Why not just retry on None (the old behavior)?

The old `_ask_model` collapsed every failure (transport OR parse) into
`None`. That made a 401 on the first model indistinguishable from an
unparseable plan and gave the loop no signal to advance. The new
classifier puts each fault on the right rail: transport → next candidate
(FAILOVER), quality → same model with feedback (RETRY).

### Public contract preserved

- `recommend_tiers(...)` still returns three `TierRecommendation` rows
  (high/med/low) covering every catalog id (anti-hallucination).
- On full pool exhaustion it returns the heuristic ranking, not a hang or
  a raised exception.
- The CLI `charon tier recommend` path is unchanged.

## Tests

- `test_recommend_tiers_fails_over_when_first_candidate_401s` — first
  candidate raises `_TierTransportError("auth", 401, ...)`; second returns
  a valid ranking → recommend_tiers uses the SECOND (proves failover).
- `test_recommend_tiers_all_candidates_fail_returns_heuristic` — every
  candidate raises → all catalog ids still classified (heuristic
  fallback), no hang, no exception escape.
- `test_recommend_tiers_quality_fault_reprompts_same_model` — first
  candidate returns `None` (200-but-garbage) → loop re-prompts the SAME
  candidate once, then advances; second candidate's valid ranking wins.
- The two pre-existing order tests (pinned worker, tier-high worker) are
  updated to patch the new `_post_tier_ranking` seam.

## Gate

`PYTHONPATH=src python3 -m pytest -q tests/test_recommend.py` → 17 passed.
`PYTHONPATH=src python3 -m charon.cli gate` → all GREEN.
