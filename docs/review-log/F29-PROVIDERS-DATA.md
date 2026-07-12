# F29-PROVIDERS-DATA review note

**Refactor**: Move `PRESETS` from `providers.py:60-156` into `provider_presets/` category modules.

## Data integrity

- All 26 vendor keys preserved exactly. Every `ProviderPreset` field value byte-for-byte identical to the original inline dict — only file location changed.
- Spot-checked anthropic, openrouter, cline-pass, deepseek, perplexity, local servers in `test_provider_presets.py`.

## Registry pattern

Mirrors `response_adapters._ADAPTERS` precedent: category modules export `CATEGORY_PRESETS_DATA` (raw dicts), `__init__.py` merges into `MERGED_RAW_DATA`, `providers.py` constructs `ProviderPreset` instances to avoid circular import.

## Files changed

| File | Change |
|---|---|
| `src/charon/providers.py` | Replace inline `PRESETS` dict with `from .provider_presets import MERGED_RAW_DATA; PRESETS = {k: ProviderPreset(**v) ...}` |
| `src/charon/provider_presets/__init__.py` | Registry: merges `CATEGORY_PRESETS_DATA` from category modules → `MERGED_RAW_DATA` |
| `src/charon/provider_presets/anthropic.py` | Anthropic preset data (wire=anthropic, strip_v1=False) |
| `src/charon/provider_presets/opencode.py` | opencode-zen, opencode-go preset data |
| `src/charon/provider_presets/hosted.py` | 18 hosted cloud providers (openrouter through perplexity) |
| `src/charon/provider_presets/local.py` | 5 local server presets (lmstudio, jan, ollama, vllm, local) |
| `tests/test_provider_presets.py` | Fail-on-revert: key count + spot-checks + new-preset-appears-without-edit test |
