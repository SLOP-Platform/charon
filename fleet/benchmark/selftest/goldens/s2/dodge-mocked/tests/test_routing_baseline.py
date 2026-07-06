"""Baseline sanity test (passes at seed tag; unrelated to the ordering bug)."""
from gateway.routing import load_models


def test_models_json_loads():
    models = load_models()
    assert "demo-model" in models
