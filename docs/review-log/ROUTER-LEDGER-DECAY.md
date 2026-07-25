# ROUTER-LEDGER-DECAY — router-side model-signal ledger decay

Implements exponential half-life decay for model-signal ledger entries in the
routing policy package. Extracted intent from the retired bitemporal reference
(FN-MEMORY-RETIRE-ADOPT) — pure stdlib router code, no retired-module dependency.

## Decisions

- **Pure function, no state**: `model_signal_weight()` is a deterministic
  function of (learned_at, last_referenced, as_of, half_life). No IO, no
  persistence. Callers supply their own entries and timestamps.
- **exp2 decay**: Same formula as the retired reference (`math.exp2(-age/hl)`),
  anchored on `learned_at` with optional `last_referenced` extension.
- **Routing-path wiring**: Exported via `routing_policy/__init__.py` alongside
  `derived_cost_rank`. A standalone `rank_by_decayed_score()` function shows
  how to use it in a ranking pipeline. When the model-signal ledger becomes a
  live router input, callers compose decay into their existing sort key.
- **`ModelSignalEntry` dataclass**: Lightweight carrier for `(model_id,
  raw_score, learned_at, last_referenced)`. No ledger storage — that lives
  in the future model-signal ledger implementation.

## Scope check

Owns: `src/charon/routing_policy/ledger_decay.py`, `tests/test_ledger_decay.py`.
Also touched: `src/charon/routing_policy/__init__.py` (imports + exports).

## Verification

- 16 tests cover: fresh vs stale weighting, half-life math, configurable
  half-life, last_referenced extension, ranking flips, gateway contract.
- `test_ranking_flips_because_of_decay`: raw score orders model-old > model-young
  (60 > 50), but decay reverses it (50-day-old signal at 20d age ~0.63× → 37.8 vs
  5d age ~0.89× → 44.55).
- `test_ranking_flips_stale_high_score_loses_to_fresh_lower_score`: 90-raw at -90d
  decays to 11.25; 50-raw at -2d decays to 47.74 — routing decision flips.
- `test_ranking_path_changes_order_when_decay_applied`: 3-model pool reorders from
  raw order a→b→c to decayed order b→c→a.
- Full suite: 2281 passed, ruff clean, mypy clean, boundary OK.
