"""New module invented for the fallback tier feature (no precedent existed)."""
import json
from pathlib import Path

TIERS_PATH = Path(__file__).resolve().parent.parent / "config" / "tiers.json"


def load_tier_config():
    with open(TIERS_PATH) as f:
        return json.load(f)
