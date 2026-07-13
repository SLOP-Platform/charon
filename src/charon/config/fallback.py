"""Fallback provider chain and fallback pricing config store."""
from __future__ import annotations

from pathlib import Path

from ._store import _load, _save

_FALLBACK_FILE = "fallback.json"
_FALLBACK_PRICING_FILE = "fallback_pricing.json"


def load_fallback_providers() -> list[str]:
    """Read the ordered fallback provider list from ``fallback.json``.
    Returns an empty list when the file is absent or malformed."""
    data = _load(_FALLBACK_FILE)
    fallback = data.get("providers")
    if isinstance(fallback, list):
        return [str(p).strip() for p in fallback if isinstance(p, str) and str(p).strip()]
    return []


def set_fallback_providers(providers: list[str]) -> Path:
    """Persist the ordered fallback provider list to ``fallback.json``."""
    cleaned = [str(p).strip() for p in providers if isinstance(p, str) and str(p).strip()]
    return _save(_FALLBACK_FILE, {"providers": cleaned})


def load_fallback_pricing() -> dict:
    """Read fallback per-token pricing from ``fallback_pricing.json``.
    Returns ``{}`` when the file is absent or malformed."""
    data = _load(_FALLBACK_PRICING_FILE)
    result: dict[str, float] = {}
    for k in ("cost_input", "cost_output"):
        v = data.get(k)
        if isinstance(v, (int, float)):
            result[k] = float(v)
    return result


def set_fallback_pricing(cost_input: float, cost_output: float) -> Path:
    """Persist the fallback per-token pricing to ``fallback_pricing.json``."""
    cost_input = float(cost_input)
    cost_output = float(cost_output)
    if cost_input < 0 or cost_output < 0:
        raise ValueError("fallback pricing must be non-negative")
    return _save(_FALLBACK_PRICING_FILE, {
        "cost_input": cost_input,
        "cost_output": cost_output,
    })
