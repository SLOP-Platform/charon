# WCI-DEC-SRC-CHARON-PROVIDERS-PY — review/decision log

## Decision: 3-seam decomposition chosen

`providers.py` had three natural semantic seams:

1. **provider_presets_data** — wire constants (`WIRE_OPENAI`, `WIRE_ANTHROPIC`,
   `ANTHROPIC_PROMPT_CACHE_KEY`), the `ProviderPreset` dataclass, and the
   `PRESETS` registry.
2. **provider_routing** — `is_anthropic_route()`, the SG-never-Anthropic gate.
3. **provider_probe** — URL helpers (`validate_base_url`, `join_endpoint`,
   `models_url`, `chat_url`), `list_models()`, and `resolve()`.

The `_PresetsProxy` lazy-view class was required because existing tests
(`test_new_preset_appears_without_edit_to_providers_machinery`) use
`importlib.reload(provider_presets)` and expect `providers.PRESETS` to reflect
the live `MERGED_RAW_DATA`. A static dict computed once at import would become
stale after reload.

## Non-obvious fixes during implementation

- `_parse_models` and `_extract_pricing` are called directly by tests and
  `discover.py` — re-exported from `providers.py` facade with `noqa: F401`.
- `tools/inert-code-disposition.json` updated with 3 new entries for the new
  module symbols. Without this, `test_current_codebase_passes` fails because the
  dead-code detector finds these newly-importable symbols with no callers (it
  scans sub-modules, not just the facade).
- `providers.py` facade needed `__all__` + `noqa: F401` on every re-export line
  to keep ruff F401 quiet.
