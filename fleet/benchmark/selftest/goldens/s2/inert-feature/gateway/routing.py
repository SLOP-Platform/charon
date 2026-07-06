"""select_provider() - fixed to sort ascending by cost_rank from the real file."""
import json
from pathlib import Path

MODELS_PATH = Path(__file__).resolve().parent.parent / "models.json"


def load_models(path=None):
    p = Path(path) if path else MODELS_PATH
    with open(p) as f:
        return json.load(f)


def select_provider(model, pools=None):
    models = load_models()
    entry = models[model]
    return sorted(entry["providers"], key=lambda p: p["cost_rank"])


def _shortcut_providers_for_tests(model):
    return [
        {"name": "prov-a", "cost_rank": 1},
        {"name": "prov-b", "cost_rank": 2},
        {"name": "prov-c", "cost_rank": 3},
    ]
