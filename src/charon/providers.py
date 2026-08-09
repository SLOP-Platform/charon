"""Provider presets + resolution (ADR-0005 P3).

This module is a facade that re-exports all public symbols from its three
internal sub-modules, preserving full backward compatibility for existing callers.
The sub-modules are the three seams along which this file is decomposed:

* ``provider_presets_data`` — wire constants (``WIRE_OPENAI`` / ``WIRE_ANTHROPIC`` /
  ``ANTHROPIC_PROMPT_CACHE_KEY``), ``ProviderPreset`` dataclass, and the built-in
  ``PRESETS`` registry.
* ``provider_routing`` — ``is_anthropic_route()``, the SG-never-Anthropic hard rule.
* ``provider_probe`` — URL helpers (``validate_base_url`` / ``join_endpoint`` /
  ``models_url`` / ``chat_url``), ``list_models()``, and ``resolve()``.
"""
from __future__ import annotations

from .provider_presets_data import (  # noqa: F401
    ANTHROPIC_PROMPT_CACHE_KEY,
    WIRE_ANTHROPIC,
    WIRE_OPENAI,
)
from .provider_presets_data import PRESETS as PRESETS  # noqa: F401
from .provider_presets_data import ProviderPreset as ProviderPreset  # noqa: F401
from .provider_probe import (  # noqa: F401
    _extract_pricing as _extract_pricing,
)
from .provider_probe import (
    _parse_models as _parse_models,
)
from .provider_probe import (  # noqa: F401
    chat_url,
    join_endpoint,
    models_url,
    validate_base_url,
)
from .provider_probe import (
    list_models as list_models,
)
from .provider_probe import (
    resolve as resolve,
)
from .provider_routing import is_anthropic_route as is_anthropic_route  # noqa: F401

__all__ = [
    "WIRE_OPENAI",
    "WIRE_ANTHROPIC",
    "ANTHROPIC_PROMPT_CACHE_KEY",
    "ProviderPreset",
    "PRESETS",
    "is_anthropic_route",
    "validate_base_url",
    "join_endpoint",
    "models_url",
    "chat_url",
    "list_models",
    "resolve",
]
