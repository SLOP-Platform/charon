"""Provider config loading — mirrors Charon's gateway/config_load.py shape."""
import json
from pathlib import Path

from gateway.validate import validate_provider

_CONFIG = Path(__file__).resolve().parent.parent / "config" / "providers.json"


def load_providers():
    """Load, validate, and return the providers list from config.

    Reads the `base` key. Part of the rename: this must read `base_url`.
    """
    with open(_CONFIG) as f:
        raw = json.load(f)
    providers = []
    for entry in raw["providers"]:
        validate_provider(entry)
        providers.append({"name": entry["name"], "base_url": entry["base"]})
    return providers
