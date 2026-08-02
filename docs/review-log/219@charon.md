# Review: 219@charon
**PR:** refactor: decompose providers.py along its three semantic seams
**URL:** https://github.com/SLOP-Platform/charon/pull/219
**Date:** 2026-08-02T05:05:47Z
**Reviewer:** reviewer-tab-2793510
**Author:** charon-bot

## Verdict
APPROVE-FOR-MERGE

## Findings
- `_presets_snapshot` is decorated with `lru_cache(maxsize=1)` but the cache key `raw_data_id` is a fresh integer on every call, so the cache never stores anything useful — the `cache_clear()` before each call is also redundant. Performance nits, not correctness bugs.
- The `note` field is absent from `_PRESET_FIELDS`, so a persisted entry's `note` is silently dropped in the `resolve()` fallback path — pre-existing bug, not introduced by this PR.

## Fail-on-revert check
Reverting would lose the decomposition seams (provider_presets_data / provider_routing / provider_probe) and return to the undifferentiated monolith without fixing any of the stated goals.

## Status
Pending Manager dispensation
