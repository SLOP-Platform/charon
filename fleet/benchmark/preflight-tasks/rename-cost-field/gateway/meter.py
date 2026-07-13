"""Cost meter — mirrors Charon's gateway/meter.py shape. Reads cost_rank."""


def rank_summary(providers):
    """Return a {name: cost_rank} map for reporting."""
    return {p.name: p.cost_rank for p in providers}
