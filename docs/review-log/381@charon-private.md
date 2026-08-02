# Review: 381@charon-private
**PR:** feat(discovery): D2 normalize — RawOffer -> §3c inventory snapshot (DISCOVERY-NORMALIZE)
**URL:** https://github.com/Nnyan/charon-private/pull/381
**Date:** 2026-08-02T05:20:30Z
**Reviewer:** reviewer-tab-2808948
**Author:** Nnyan

## Verdict
NEEDS-REVISION

## Findings
- **Cross-source merge produces self-contradictory rows (`_merge_rows`).** When the same `(provider, normalized_model)` appears on multiple sources — guaranteed in practice, since cheahjs/models.dev/OpenRouter all index the same frontier models — `row[5]` collapses to funding_class=1 if ANY merged offer is free, while `row[6]`/`row[7]`/`row[12]`/`row[3]` keep only the FIRST row's value. A model free on one source and PAYG on another yields funding_class=1 carrying the paid offer's cost (or silently drops the paid cost). `row[3]` (base_url) is never merged at all: an OpenRouter row carries `https://openrouter.ai/api/v1`, a models.dev row carries `""`, and the survivor is pure input-order. Meanwhile `row[0]` (source) IS merged into a `|`-union — a precedent the author cites only for model_ids — while its companion `row[1]` (source_url) is not. These contradictory rows feed D7's authoritative re-derivation, so the corruption is not contained to an ephemeral file.
- **Injected `normalize_fn` is honored for grouping/first_seen but NOT for the final sort.** `normalize_offers` sorts with the hardcoded global `_normalize_model_id(r[4].split("|")[0])`, and `_load_prior_first_seen` also hardcodes the global. The module's stated contract is a pure, injectable function that D3/D7 import directly — a caller passing a custom fn gets a sort key that disagrees with the grouping key and prior-key lookups that miss. The selftest only passes coincidentally (the broken fn still yields duplicate keys regardless of sort order); it never proves the injected-fn contract holds.
- **Non-atomic write + unguarded prior read break the "first_seen preserved" invariant.** `write_inventory` truncates the destination in place (no temp-file + `os.replace`); a crash mid-write corrupts the snapshot, and the next run's `_load_prior_first_seen` dereferences `line[16]` with no length guard on truncated rows → IndexError bricks the entire daily loop. Overlapping daily runs race the read-modify-write on `output`, so a late writer can reset `first_seen` for keys the earlier run just preserved.
- **No None/empty guarding on the cells that ARE the key.** `_offer_row` writes `offer.provider`/`offer.model_id` raw (not via `_fmt`), so None → literal `"None"` in the TSV, while the merge key uses `_normalize_model_id` (which maps None → `""`). The sorts in `normalize_offers` and `write_inventory` then compare `(r[0], r[2], ...)` tuples where a single None alongside real strings raises TypeError, crashing the whole run. The author is defensive about `offer.raw` (`isinstance` check) but not these fields; the 6094-row live pull is exactly where a malformed offer would appear.
- **FAIL-ON-REVERT gate is a manual, single-direction check.** `--selftest` only exercises the under-collapse direction on two well-formed same-provider offers. It never covers the `--input` path, prior/first_seen preservation, or the cross-source merge where the findings above live, and it is not wired into any CI check — a revert that deletes the script entirely, or that regresses first_seen preservation or the merge, stays GREEN.

## Fail-on-revert check
The gate only runs when a human invokes `--selftest` and never exercises first_seen preservation, the `--input` path, or the cross-source merge — a revert that removes the script or breaks those paths passes GREEN.

## Status
Pending Manager dispensation
