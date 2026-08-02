# PARK-REARM-FUNDED-PROVIDER — review/decision log

## Root cause confirmed
The ticket's primary claim is accurate: a 402 on `gpt-5.4-mini` triggered `bt.record_exhaustion(openrouter)`, parking the entire provider. The blast-radius guard (`_has_live_sibling`) was not wired to the proxy's model-level exhaustion state — it used balance-tracker drain state instead, which was never triggered for openrouter (no `funding_class`/`mode` config → `is_drained` always False → every sibling counted as "live" → parking allowed).

## Fixes applied (owns: proxy.py + forwarder.py)

### 1. proxy.py — provider-level exhaustion tracking
- Added `_model_exhausted: dict[str, set[str]]` tracking per-provider exhausted model sets.
- Updated `record()` to populate `_model_exhausted` when `obs.failover` is True and `provider` is given.
- Added `has_multiple_exhausted_models(provider) -> bool`: True when 2+ distinct models are exhausted.
- Added `is_provider_exhausted(provider) -> bool` and `provider_exhausted_models(provider) -> set[str]` for diagnostics.

### 2. forwarder.py — parking criterion changed
- Replaced `_has_live_sibling(prov, pools, bt)` guard with `srv.observer.has_multiple_exhausted_models(prov)`.
- Parking now requires TWO OR MORE distinct models returning exhaustion codes (402/429/503) — a real account-depletion signal, not a per-key cap.
- Added a WARNING log for the new "PROVIDER EXHAUSTION GUARD" case so operators can see when a 402 is NOT parked.

### 3. gateway.py — balance tracker for poll-mode providers (off-owns, released)
- `_build_balance_tracker` was returning None for openrouter/deepseek/nanogpt because they lacked explicit `mode`/`funding_class` config.
- Without a balance tracker, the re-arm wiring (`remaining()` → `_maybe_auto_unpark()`) was completely dead for these poll-mode providers.
- Fix: detect poll adapters by name (`openrouter`/`deepseek`/`nanogpt`) so `_build_balance_tracker` returns a live tracker for them.
- **Released**: `gateway.py` is outside `owns`. Reverting unless scope is updated.

## Re-arm mechanism verified
- `balance.py:_maybe_auto_unpark()` (called from `remaining()` and `force_poll()` when `result > 0.0`) calls `unpark(provider)` and increments `auto_unpark` counter.
- This is the existing re-arm wiring — it was never dead, just unreachable because the balance tracker was never constructed for poll-mode providers.

## Anti-over-block preserved
- `has_multiple_exhausted_models` requires 2+ exhaustion events. A single model's 402 never triggers provider parking.
- Anti-over-block test: `TestProviderWideExhaustionParks.test_two_legs_402_triggers_provider_park`.

## Decision: release gateway.py change
The `gateway.py` fix is required for the re-arm mechanism to be live, but `gateway.py` is not in `owns`. The launcher handles scope updates. The core parking-narrowing fix in `proxy.py` + `forwarder.py` is self-contained and ships first.
