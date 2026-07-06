"""Pool selection - mirrors Charon's gateway/pools.py shape. No tier config
schema exists yet - that's the point of this section: there is no precedent
to copy from."""


def select_pool(model, pools):
    """Return the first pool that lists `model`, in declared pool order."""
    for pool in pools:
        if model in pool.get("models", []):
            return pool
    return None


def select_pool_with_fallback(model, pools, exhausted_count):
    """Falls back to the cheap tier after config/tiers.json's exhausted_after."""
    from gateway.tiers import load_tier_config

    cfg = load_tier_config()
    if exhausted_count >= cfg["exhausted_after"]:
        for pool in pools:
            if pool.get("tier") == cfg["default_tier"]:
                return pool
    return select_pool(model, pools)
