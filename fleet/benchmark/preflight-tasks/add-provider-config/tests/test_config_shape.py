"""Baseline shape check — no YAML dependency; validates the example parses as
a simple provider list with the required keys present."""
import re
from pathlib import Path

_CFG = Path(__file__).resolve().parent.parent / "config" / "providers.example.yaml"


def test_each_provider_has_required_fields():
    text = _CFG.read_text()
    names = re.findall(r"- name:\s*(\S+)", text)
    assert len(names) >= 2
    # every entry block declares base_url and api_key
    assert text.count("base_url:") == len(names)
    assert text.count("api_key:") == len(names)
