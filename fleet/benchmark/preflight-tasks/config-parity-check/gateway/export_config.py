"""Config export — mirrors Charon's gateway/export_config.py shape.

export_models() emits a normalized view of the provider config for publishing.
It must match the reviewed golden snapshot (fixtures/models.golden.json).

BUG: providers are emitted in declared (file) order, but the golden snapshot
lists them sorted ascending by cost_rank. Fix the EXPORT so it matches the
golden snapshot — the snapshot is the signed-off expected output.
"""
import json
from pathlib import Path

_RAW_CONFIG = Path(__file__).resolve().parent.parent / "fixtures" / "models.raw.json"


def _load_raw():
    with open(_RAW_CONFIG) as f:
        return json.load(f)


def export_models():
    """Return the normalized export dict.

    Currently returns providers in raw declared order. The golden snapshot has
    them sorted by cost_rank ascending.
    """
    raw = _load_raw()
    out = {}
    for model, entry in raw.items():
        out[model] = {"providers": list(entry["providers"])}
    return out
