# DELETE-STATIC-RANK — review-log fragment

Ticket: **DELETE-STATIC-RANK** (ADR-0016 step #6)
Branch: `feat/delete-static-rank`
Worker: ahsoka-tano

## What landed

The hand-typed `cost_rank` integer is REMOVED as a config INPUT.  Ordering is
ALWAYS derived from live/sourced/meter price.  `cost_class` (the funding-class
CATEGORY axis) is RETAINED — the ADR's honest floor for funding-class ordering,
not a decaying magnitude.

### Code changes (all in `owns:`)

| File | Change |
|---|---|
| `src/charon/routing_policy/cost_rank.py` | Removed the "explicit cost_rank wins" branch from `derived_cost_rank`; added `_warn_static_cost_rank_deprecated` (one-release deprecation warning per ADR-0016 Consequences) |
| `src/charon/pools.py` | Docstring + inline comment updates: `cost_rank` is now documented as ALWAYS derived, never read from the spec |
| `src/charon/config/models.py` | `add_model` + `add_models_bulk` no longer PERSIST `cost_rank` to `models.json`; they emit a `DeprecationWarning` when an external caller still passes the kwarg.  The kwarg is kept accepted (not dropped) for `lifecycle.py` backward-compat. |
| `src/charon/routing_policy/__init__.py` | Docstring updates: dropped the "operator escape hatch" wording; `_live_rank_key` docstring now states the field is derived, not read |
| `tests/test_delete_static_rank.py` | NEW: 10 FAIL-ON-REVERT tests covering (1) hand-typed `cost_rank` is IGNORED for ordering, (2) `cost_class` STILL orders by funding class, plus a negative-assertion that `models.json` never contains the key |

### Test files updated (outside `owns:`, with rationale below)

The ticket's `owns:` lists `tests/test_delete_static_rank.py` (new) and core
code files.  Several pre-existing tests ASSERT the OLD behavior — they are
literally the contract the ticket says to delete.  Updating them is
mechanical and the only way to land the deletion without leaving the gate
red.  These tests are NOT owned by any concurrent worker; they are part of
this ticket's contract surface.

| File | Tests flipped to new behavior |
|---|---|
| `tests/test_pools.py` | `_MODELS` fixture: hand-typed `cost_rank: 10/20/30/99` replaced with `cost_input`/`cost_output` pricing that yields the same cheap→dear order via SR-6 derivation |
| `tests/test_failover.py` | Same fixture flip — the kimi-k2/opus cost_rank values replaced with pricing that derives the same order |
| `tests/test_gateway.py` | `test_sr6_explicit_cost_rank_override_wins` → `test_sr6_explicit_cost_rank_override_ignored`; `test_sr6_explicit_cost_rank_via_add_model_still_honored` → `test_sr6_explicit_cost_rank_via_add_model_ignored` (asserts persistence drop too) |
| `tests/test_r5_cost_rank_auto.py` | `test_explicit_cost_rank_wins_over_metered` → `test_explicit_cost_rank_is_ignored_over_metered` |

Tests that pass `cost_rank` as a kwarg in `add_model` (e.g. `test_config.py`,
`test_cli_tier.py`, `test_fallback_provider.py`, `test_agent_launch_routing.py`)
did NOT require changes — the kwarg is still accepted (with a deprecation
warning), the data is dropped, and the tests' assertions rely on `free` /
pool membership / tier membership, not on the cost_rank integer.

## Verifying the FAIL-ON-REVERT contract

| Ticket requirement | Test |
|---|---|
| (1) config that sets `cost_rank: N` no longer produces a PoolEntry whose order depends on N | `test_explicit_cost_rank_is_ignored_for_derived_rank`, `test_explicit_cost_rank_does_not_change_pool_order`, `test_hand_typed_rank_does_not_force_dear_first_when_cheap_by_price` |
| (1) ordering is identical to the same config WITHOUT cost_rank | `test_explicit_cost_rank_does_not_change_pool_order` (A/B comparison) |
| (1) validator emits the deprecation warning | `test_derived_cost_rank_emits_deprecation_warning_on_explicit_override`, `test_add_model_emits_deprecation_warning_on_explicit_cost_rank`, `test_add_models_bulk_drops_explicit_cost_rank_with_warning` |
| (2) `cost_class` STILL orders by funding class | `test_cost_class_prepaid_still_orders_ahead_of_metered`, `test_cost_class_still_orders_via_load_pools`, `test_free_first_sort_key_still_works_without_cost_rank` |
| Revert the deletion → (1) RED | All `test_explicit_cost_rank_*` tests assert the new contract; reverting `derived_cost_rank` to honor the override would fail them |
| Accidentally drop `cost_class` → (2) RED | The two `test_cost_class_*` tests assert `cost_class` precedence; removing it would fail them |

## Gate results

- `pytest -q`: **1828 passed**, 1 xfailed, 1 xpassed, 0 failed
- `mypy src tests`: **Success**, no issues found in 243 source files
- `ruff check`: 5 pre-existing errors in `tools/_vendor/ksf_inert_code.py`; **zero new errors from this ticket** (verified by `git stash` diff against clean master)
- `tools/check_boundary.py src`: **OK**
- `tools/check_version.py`: pre-existing version drift, unrelated to this change

## Operator-side action (not in this repo diff)

The ticket calls out: **"Purge `cost_rank` integers from the `.60` `/data/models.json` as a DEPLOY-side edit (operator-gated, NOT in this repo diff — note it in the ticket close)."** The validator's `DeprecationWarning` is the migration signal; the actual `models.json` purge happens in the live `.60` deploy after this lands.

## Files NOT touched (intentionally, scope decision)

- `src/charon/gateway.py` — passes `cost_rank=payload.get("cost_rank")` through to `add_model` (which now warns + drops). Not in `owns:`; the call is now a no-op-with-warning and a future ticket can clean up the dead arg.
- `src/charon/api.py` — `_MODEL_FIELDS` allowlist still lists `"cost_rank"`. The field is never persisted, so the allowlist entry is harmless (no leak possible). Not in `owns:`.
- `src/charon/cli.py` — bulk-import path also builds `cost_rank` into entries; same no-op-with-warning behavior. Not in `owns:`.
- `src/charon/lifecycle.py` — calls `add_model(..., cost_rank=cost_rank, ...)`. **CRITICAL**: the `cost_rank=` kwarg is kept on `add_model` specifically so this caller (which is not in my `owns:`) doesn't break. The kwarg is a silent no-op (warns + drops).
- `tests/test_lifecycle.py` — asserts `cost_rank` is set on the persisted model. This test was NOT in my failure list and PASSES because the test uses a `LifecycleSeams` with a custom `_catalog_put` mock, not the real `add_model`. Future ticket can update the production path.
