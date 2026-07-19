"""User-local gateway config (providers / models / pools) in ``config_dir()``.

The single writer shared by the `charon providers`/`charon setup` CLI and the web
setup page, and the config the gateway reads by default — so adding a provider once
(CLI or browser) makes it work with no hand-edited TOML. API keys are NOT stored
here; they live in ``secrets.json`` (see :mod:`charon.secrets`). This file holds only
non-secret config: base URLs, ``key_env`` references, model maps, pools.
"""
from __future__ import annotations

from .. import secrets as secrets  # noqa: F811
from ._store import (
    _ID_RE,
    _as_str_tuple,
    _check_id,
    _load,
    _save,
    _validate_base_url,
    remove,
)
from .autoland import (
    AutoLandConfig,
    load_autoland_config,
    save_autoland_config,
)
from .fallback import (
    load_fallback_pricing,
    load_fallback_providers,
    set_fallback_pricing,
    set_fallback_providers,
)
from .keyprobe import (
    validate_provider_key,
)
from .models import (
    add_model,
    add_models_bulk,
    load_models,
    set_model_enabled,
)
from .pools import (
    load_pools,
    set_pool,
)
from .providers import (
    add_provider,
    load_providers,
)
from .sandbox import SandboxPolicy, load_sandbox_policy
from .summary import (
    failover_chain_health,
    summary,
)
from .tiers import (
    CANONICAL_TIERS,
    LEGACY_SEED_PROVIDER,
    legacy_seed_members,
    load_tiers,
    resolve_tier,
    set_tiers,
    tier_members,
    tier_rank,
)

__all__ = [
    "secrets",
    "SandboxPolicy",
    "load_sandbox_policy",
    "AutoLandConfig",
    "load_autoland_config",
    "save_autoland_config",
    "_load",
    "_save",
    "_check_id",
    "_validate_base_url",
    "_ID_RE",
    "_as_str_tuple",
    "remove",
    "load_providers",
    "add_provider",
    "load_models",
    "add_model",
    "add_models_bulk",
    "set_model_enabled",
    "load_pools",
    "set_pool",
    "CANONICAL_TIERS",
    "LEGACY_SEED_PROVIDER",
    "legacy_seed_members",
    "load_tiers",
    "set_tiers",
    "resolve_tier",
    "tier_members",
    "tier_rank",
    "validate_provider_key",
    "load_fallback_providers",
    "set_fallback_providers",
    "load_fallback_pricing",
    "set_fallback_pricing",
    "summary",
    "failover_chain_health",
]
