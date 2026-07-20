"""Config summary — CLI/console view (no secrets leaked)."""
from __future__ import annotations

from typing import Any

from .. import providers as _providers
from .. import secrets
from .fallback import (
    load_fallback_pricing,
    load_fallback_providers,
)
from .models import load_models
from .pools import load_pools
from .providers import load_providers


def _unknown_pricing_models(models: dict) -> list[str]:
    """Models that have neither ``cost_input`` nor ``cost_output`` (and are not
    marked as free — free models are genuinely free and should not be flagged)."""
    unknown: list[str] = []
    for mid, entry in models.items():
        if entry.get("free"):
            continue
        if "cost_input" not in entry and "cost_output" not in entry:
            unknown.append(mid)
    return unknown


def failover_chain_health() -> dict:
    """Return a summary dict of failover readiness: whether pools, fallback, or
    providers are configured, and whether any failover chain exists."""
    pools = load_pools()
    fb = load_fallback_providers()
    provs = load_providers()
    has_pools = bool(pools)
    has_fallback = bool(fb)
    has_providers = bool(provs)
    return {
        "has_pools": has_pools,
        "has_fallback": has_fallback,
        "has_providers": has_providers,
        "pools_count": len(pools),
        "fallback_provider_count": len(fb),
        "provider_count": len(provs),
    }


def summary() -> dict:
    """A non-secret view for the CLI/console: providers (with key-set state, NOT the
    key), models, pools, failover chain health, unknown-pricing models, and optional
    fallback pricing."""
    secs = secrets.load_secrets()
    provs = {}
    for n, e in load_providers().items():
        try:
            resolved = _providers.resolve(n, e)
            base, ke = resolved.base_url, resolved.key_env
        except ValueError:
            base, ke = e.get("base_url"), e.get("key_env")
        entry: dict[str, Any] = {
            # Both fields report the RESOLVED value. Mixing a resolved key_env with
            # the raw persisted base_url made the two halves of one dict describe
            # different providers, and a provider with no persisted base reported
            # null next to a preset key_env it does resolve.
            "base_url": base,
            "key_env": ke,
            # Asked through the ONE resolver, so the console reports "key set"
            # exactly when a key would actually be sent — not when some shared
            # env var merely happens to be populated.
            "key_set": bool(secrets.get_provider_key(
                n, key_env=ke, base_url=base, secs=secs)),
        }
        # DRAIN-AND-PARK balance fields (non-secret — no keys)
        for bk in ("funding_class", "starting_balance", "mode",
                    "balance_base_url", "balance_key_env", "balance_ttl"):
            if bk in e:
                entry[bk] = e[bk]
        provs[n] = entry
    models = load_models()
    result: dict[str, Any] = {
        "providers": provs, "models": models, "pools": load_pools(),
    }
    result["unknown_pricing"] = _unknown_pricing_models(models)
    fb = load_fallback_providers()
    if fb:
        result["fallback"] = fb
    fallback_pricing = load_fallback_pricing()
    if fallback_pricing:
        result["fallback_pricing"] = fallback_pricing
    result["failover_chain_health"] = failover_chain_health()
    return result
