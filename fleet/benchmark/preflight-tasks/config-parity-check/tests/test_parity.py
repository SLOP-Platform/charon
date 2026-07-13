import json
from pathlib import Path

from gateway.export_config import export_models

_GOLDEN = Path(__file__).resolve().parent.parent / "fixtures" / "models.golden.json"


def test_export_matches_golden():
    with open(_GOLDEN) as f:
        golden = json.load(f)
    assert export_models() == golden
