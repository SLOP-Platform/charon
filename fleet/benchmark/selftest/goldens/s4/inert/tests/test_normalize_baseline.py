"""Baseline suite at the seed tag - covers only the common, non-namespaced
case, so it stays green even with the injected minority-path bug."""
from gateway.normalize import normalize_response


def test_normalize_common_case():
    resp = {"model": "gpt-4", "choices": []}
    assert normalize_response(resp)["model"] == "gpt-4"


def test_normalize_preserves_other_fields():
    resp = {"model": "gpt-4", "choices": [{"text": "hi"}]}
    assert normalize_response(resp)["choices"] == [{"text": "hi"}]
