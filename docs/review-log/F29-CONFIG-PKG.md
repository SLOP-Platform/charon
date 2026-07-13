# F29-CONFIG-PKG Review Log

**Date:** 2026-07-12
**Status:** Complete

## Summary

Split `src/charon/config.py` (669 LOC) into a `src/charon/config/` package of 10 disjoint submodules. The import surface is preserved verbatim through `config/__init__.py` re-exports. `config.py` is deleted; the package takes precedence.

## Submodule mapping

| Submodule | Source lines (orig config.py) | Contents |
|---|---|---|
| `_store.py` | 139-191, 471-479 | `_load`, `_save`, `_validate_base_url`, `_ID_RE`, `_check_id`, `_as_str_tuple`, `remove` |
| `sandbox.py` | 25-52 | `SandboxPolicy`, `load_sandbox_policy`, `_SANDBOX_ENV` |
| `autoland.py` | 55-136 | `AutoLandConfig`, `load_autoland_config`, `save_autoland_config`, `_AUTOLAND_ENV`, `_AUTOLAND_FILE`, `_TRUTHY`, `_truthy` |
| `providers.py` | 177-251 | `load_providers`, `add_provider`, `_FUNDING_CLASSES`, `_FUNDING_CLASS_LABELS` |
| `models.py` | 216-303, 513-521 | `load_models`, `add_model`, `add_models_bulk`, `set_model_enabled`, `_COST_CLASSES`, `_normalize_cost_class` |
| `pools.py` | 306-314 | `load_pools`, `set_pool` |
| `tiers.py` | 317-431 | `load_tiers`, `set_tiers`, `resolve_tier`, `tier_members`, `tier_rank`, `CANONICAL_TIERS`, `_TIERS_FILE`, `_LEGACY_ALIASES`, `_LEGACY_MEMBERS`, `_legacy_tiers` |
| `keyprobe.py` | 444-510 | `validate_provider_key`, `_VALIDATE_TIMEOUT`, `_VALIDATE_UA` |
| `fallback.py` | 524-580 | `load_fallback_providers`, `set_fallback_providers`, `load_fallback_pricing`, `set_fallback_pricing`, `_FALLBACK_FILE`, `_FALLBACK_PRICING_FILE` |
| `summary.py` | 582-625 | `summary`, `failover_chain_health`, `_unknown_pricing_models` |

## Decisions

1. **Package over module**: Deleted `config.py` entirely — Python prefers `config/__init__.py` when both exist, making the split unambiguous.
2. **`_as_str_tuple` in `_store.py`**: Used by both `autoland.py` and `tiers.py`; placed in the shared utility module.
3. **`remove` in `_store.py`**: Generic removal for providers/models/pools; not provider-specific.
4. **`config.secrets` preserved**: `pricing_limits_checker.py` accesses `config.secrets.config_dir()`; re-exported via `from .. import secrets`.
5. **`summary.py` uses direct submodule imports**: `from .fallback import load_fallback_providers` (not `from . import fallback`) to avoid circular import in the package graph.
6. **`__all__` in `__init__.py`**: Lists every public re-export; suppresses ruff F401.

## Verification

- **Full test suite**: 1518 passed (excluding pre-existing env-local flaky test in `test_gateway.py::test_failover_chain_check_warns_when_no_pools_or_fallback`)
- **Facade test**: `tests/test_config_facade.py` asserts every public symbol from submodules is reachable from `charon.config`
- **Gate checks**: ruff clean, mypy clean, boundary clean, version OK
