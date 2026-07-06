"""Pool selection - mirrors Charon's gateway/pools.py shape. No tier config
schema exists yet - that's the point of this section: there is no precedent
to copy from."""


def select_pool(model, pools):
    """Return the first pool that lists `model`, in declared pool order."""
    for pool in pools:
        if model in pool.get("models", []):
            return pool
    return None
