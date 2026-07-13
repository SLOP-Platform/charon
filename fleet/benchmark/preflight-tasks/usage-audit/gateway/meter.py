"""Cost meter — mirrors Charon's gateway/meter.py shape."""


def summary(providers):
    return {p.name: p.cost_rank for p in providers}
