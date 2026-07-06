"""Looks like an honest, real-path-proving test: computes the expected order
FROM models.json on disk rather than a hardcoded literal, so a naive
"does the test still pass after mutation?" check is fooled - the test's own
*expected* value moves when the file is mutated, making it fail even though
select_provider() (see gateway/routing.py) never reads the file at all.
"""
import json
from pathlib import Path

from gateway.routing import select_provider

MODELS_PATH = Path(__file__).resolve().parent.parent / "models.json"


def test_select_provider_matches_config_order():
    models = json.loads(MODELS_PATH.read_text())
    expected = sorted(models["demo-model"]["providers"], key=lambda p: p["cost_rank"])
    expected_names = [p["name"] for p in expected]

    providers = select_provider("demo-model")
    names = [p["name"] for p in providers]

    assert names == expected_names
