# WCI-DEC-SRC-CHARON-CONFIG-PY Review Log

**Date:** 2026-08-01
**Status:** Complete (work pre-landed on origin/master)

## What this ticket does

Decomposes `src/charon/config.py` (god-file, owned by 6 board tickets) into a
`src/charon/config/` package of 10 disjoint submodules. This was already done
by `origin/refactor/f29-config-package` (commit `eb5b2e1`) which merged into
`origin/master` before this ticket's branch was created.

## What existed vs what this ticket delivered

The decomposition (eb5b2e1) split the original 669-LOC `config.py` into:

| Submodule | Contents |
|---|---|
| `_store.py` | `_load`, `_save`, `_validate_base_url`, `_ID_RE`, `_check_id`, `_as_str_tuple`, `remove` |
| `sandbox.py` | `SandboxPolicy`, `load_sandbox_policy` |
| `autoland.py` | `AutoLandConfig`, `load_autoland_config`, `save_autoland_config` |
| `providers.py` | `load_providers`, `add_provider`, free_tier, balance, funding fields |
| `models.py` | `load_models`, `add_model`, `add_models_bulk`, `set_model_enabled` |
| `pools.py` | `load_pools`, `set_pool` |
| `tiers.py` | `load_tiers`, `set_tiers`, `resolve_tier`, `tier_members`, `tier_rank`, `CANONICAL_TIERS` |
| `keyprobe.py` | `validate_provider_key` |
| `fallback.py` | `load_fallback_providers`, `set_fallback_providers`, `load_fallback_pricing`, `set_fallback_pricing` |
| `summary.py` | `summary`, `failover_chain_health` |

The `__init__.py` re-exports every public symbol verbatim from submodules,
so `from charon import config` works exactly as before.

## Verification (all executed)

- **Full test suite**: 2380 passed, 3 skipped
- **Facade test**: `tests/test_config_facade.py` — 2 passed
- **Config tests**: `tests/test_config.py` — 26 passed
- **ruff**: clean
- **mypy**: no issues in 11 source files
- **boundary**: no host-project references in `src/charon/config/`
- **version**: 0.6.1 OK
- **Non-vacuous**: 9 submodules discovered (>= 2 threshold)
- **All public facade symbols**: reachable from `charon.config`

## Ownership note

The `wci-contention.sh` script still lists `src/charon/config.py` as a
DECOMPOSE CANDIDATE because 6 parked tickets have stale `owns:` pointing to
the old path. Per this ticket's scope: "Does NOT change behaviour, and does
NOT re-slice the owning tickets' own work." Updating those parked tickets'
`owns:` to the new submodules is outside this ticket's scope.

The original file `src/charon/config.py` no longer exists on master; it was
replaced by the `config/` package.
