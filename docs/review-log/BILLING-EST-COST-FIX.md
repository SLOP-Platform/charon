# BILLING-EST-COST-FIX — review log

**Money-path.** Stop billing the phantom `est_cost` floor when a provider reports a
real $0 (free/flat routes). Owns: `src/charon/forwarder.py`, `tests/test_forwarder_billing.py`.

## What changed
- `forwarder.py` both record sites (non-stream + stream) now call a single helper
  `_spend_to_record(obs, est_cost)` instead of `record(cost if cost > 0 else est_cost)`.
- Bonus: the non-stream post-hook now runs the normalizer over **only**
  `choices[0].message.content` via `_normalize_message_content`, never the whole JSON
  envelope (`STANDARDIZE_MD` was regex-rewriting the serialized body).

## Key decision — keyed on `cost_source`, NOT on "cost==0"
The old `cost if cost > 0 else est_cost` substituted the fabricated floor
(`request_bytes/4 · $1.5e-6`) on **every** $0 response, inflating prod `spend.json` to
the fictional ~$223. The fix distinguishes by `obs.cost_source`:

| cost_source | meaning | recorded |
|---|---|---|
| `free` | model flagged free, provider $0 | **0.0** |
| `provider(0)` | provider reported an explicit real $0 | **0.0** |
| `provider` / `computed` | a real charge | the real cost |
| `unpriced` (usage, no cost field, no pricing) **or** no usage block | genuinely unknown | `est_cost` floor |

## Why `unpriced` KEEPS the floor (SR-7 preserved)
`tests/test_proxy_server.py::test_zero_cost_response_still_advances_spend_cap` (SR-7,
**not owned by this ticket**) drives a `_NoCostUpstream` that returns a usage block
with **no cost field** and no stored pricing → `cost_source == "unpriced"`. That is the
*genuinely unpriced* case the ticket says to leave alone ("only substitute est_cost when
genuinely unpriced"), so the floor still advances the universal monthly cap and SR-7
stays green. Keying on `usage is None` (my first attempt) was too aggressive — it zeroed
the unpriced case and broke SR-7. Corrected to key on `cost_source`.

## Known limitation / required companion change (NOT in this ticket's `owns:`)
The `provider(0)` cost_source **does not exist in the current `proxy.py` classifier**:
`_gateway_usage` collapses an *absent* cost field and an *explicit* `cost: 0` both to
`0.0`, and `classify()` then labels a flat-plan provider's explicit $0 as `unpriced`
(when there's no `models.json` pricing). So a flat-subscription provider like NanoGPT
(reports explicit `cost: 0`, no per-token pricing) is currently classified `unpriced` and
would **still** hit the floor.

This forwarder change is correct and forward-compatible: the moment `proxy.py` emits
`cost_source == "provider(0)"` for an explicit provider $0, this code records 0.0 with no
further change. Adding that classification belongs in `proxy.py` — owned by
**NORMALIZE-CASE-QUANT-FIX** (Wave 1) — not here. Flagging for the operator/manager: the
free-tier half of the $223 (models flagged `free: true`) is fixed by this ticket; the
flat-plan `provider(0)` half needs the proxy.py `_gateway_usage`/classify follow-up.

## Tests (`tests/test_forwarder_billing.py`, drive `forward_with_failover` e2e)
- `test_flat_provider_zero_cost_not_billed_est_floor` — FAIL-ON-REVERT: free route,
  cost==0, both non-stream + stream → `record(0.0)`. Verified RED on the old logic,
  GREEN with the fix, RED again when reverted.
- `test_unpriced_response_still_records_est_floor` — surgical boundary: a genuinely
  unpriced response still records a positive floor (both paths). Guards SR-7.
- `test_response_normalizer_receives_content_not_whole_body` — the post-hook is handed
  the message content string only; the served JSON envelope stays intact.

## Gate
Full suite 1303 passed; `charon.cli gate` all green (ruff / mypy / SLOP-boundary /
version / gate-registry / public-clean).
