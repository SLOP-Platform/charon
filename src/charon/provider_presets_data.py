"""Wire-format vocabulary + ProviderPreset data model (ADR-0005 P3).

Seam 1 of ``providers.py`` — wire constants, the preset dataclass, and the
built-in PRESETS registry. Extracted to allow independent ownership of the
provider-data model from provider-probe/URL logic.
"""
from __future__ import annotations

import functools
from dataclasses import dataclass

WIRE_OPENAI = "openai"
WIRE_ANTHROPIC = "anthropic"
ANTHROPIC_PROMPT_CACHE_KEY = "anthropic_prompt_cache"


@dataclass(frozen=True)
class ProviderPreset:
    base_url: str
    key_env: str | None = None
    strip_v1: bool = True
    downgrade_prone: bool = False
    wire: str = WIRE_OPENAI
    adapter: str | None = None
    note: str = ""
    max_context: int | None = None
    max_concurrency: int | None = None


@functools.lru_cache(maxsize=1)
def _presets_snapshot(
    raw_data_id: int,
) -> dict[str, ProviderPreset]:
    from . import provider_presets as _ppkg
    return {k: ProviderPreset(**v) for k, v in _ppkg.MERGED_RAW_DATA.items()}


def _raw_data_id() -> int:
    from . import provider_presets as _ppkg
    return id(_ppkg.MERGED_RAW_DATA)


class _PresetsProxy:
    """A lazy view over the live ``provider_presets.MERGED_RAW_DATA`` dict.

    ``PRESETS[name]`` always reflects whatever the live
    ``provider_presets.MERGED_RAW_DATA`` holds at access time — even after
    ``importlib.reload(provider_presets)``. This is required by the preset-
    discovery test that injects a synthetic entry into a category module and
    then reloads ``provider_presets``.
    """
    __slots__ = ("_last_raw_id",)

    def __init__(self) -> None:
        self._last_raw_id: int | None = None

    def _snapshot(self) -> dict[str, ProviderPreset]:
        rid = _raw_data_id()
        if rid != self._last_raw_id:
            self._last_raw_id = rid
            _presets_snapshot.cache_clear()
        return _presets_snapshot(rid)

    def __getitem__(self, name: str) -> ProviderPreset:
        return self._snapshot()[name]

    def __contains__(self, name: object) -> bool:
        return name in self._snapshot()

    def keys(self):
        return self._snapshot().keys()

    def items(self):
        return self._snapshot().items()

    def values(self):
        return self._snapshot().values()

    def __iter__(self):
        return iter(self._snapshot())

    def __len__(self) -> int:
        return len(self._snapshot())

    def get(self, name: str, default=None):
        return self._snapshot().get(name, default)


PRESETS: _PresetsProxy = _PresetsProxy()
