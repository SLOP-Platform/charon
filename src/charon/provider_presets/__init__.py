"""Provider preset registry.

Category modules each define ``CATEGORY_PRESETS_DATA: dict[str, dict]`` of
raw keyword arguments.  This module merges them into ``MERGED_RAW_DATA``,
a plain ``dict[str, dict]`` that avoids importing from ``providers.py``
(which would create a circular import).  The ``ProviderPreset`` instances
are constructed in ``providers.py`` from this merged data.

Adding a provider means adding a row to the appropriate category file;
the machinery requires zero edits.
"""
from __future__ import annotations

from . import anthropic, hosted, local, opencode


def _merge() -> dict[str, dict]:
    d: dict[str, dict] = {}
    for mod in (anthropic, hosted, local, opencode):
        d.update(mod.CATEGORY_PRESETS_DATA)
    return d


MERGED_RAW_DATA: dict[str, dict] = _merge()
