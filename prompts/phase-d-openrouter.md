## Phase D — OpenRouter Swarm Import

**MISSION:** Smart Routing — route work by cost, performance, and availability without quality loss.

**Goal:** Import 400+ models from OpenRouter API into Charon's model registry with pricing metadata. Cross-reference against existing providers using 3-stage matching (exact → fuzzy → manual override map).

**Owns:** `src/charon/discover.py`, `tests/test_discover.py`, `src/charon/providers.py`

**What to build:**

1. **`discover.py` — `discover_openrouter(timeout: int = 10) -> dict`:**
   - GET `https://openrouter.ai/api/v1/models` (no auth needed for model list)
   - Parse the response: OpenRouter returns `[{"id": "...", "name": "...", "pricing": {"prompt": "...", "completion": "..."}, "context_length": N}, ...]`
   - Convert to Charon-compatible model dicts: `{"id": id, "pricing": {"prompt": prompt, "completion": completion}, "context_window": context_length}`
   - Return `{"models": [model_dict, ...]}` format

2. **`discover.py` — `fuzzy_match_model_id(or_id: str, charon_models: dict) -> str | None`:**
   - Stage 1: Exact match (case-insensitive)
   - Stage 2: Strip known prefixes (`openai/`, `anthropic/`, `google/`, `meta-llama/`, `mistralai/`, `deepseek/`) and try match
   - Stage 3: Resolve known aliases from `~/.charon/model_aliases.json` if it exists — format: `{"or_id": "charon_model_id"}`
   - Return charon model ID or None

3. **`discover.py` — `import_openrouter_models(dry_run: bool = False) -> dict`:**
   - Call `discover_openrouter()`, then `build_cost_map()`
   - For each model: try `fuzzy_match_model_id()` against existing Charon models
   - Exact matches → auto-import via `config.add_model()`
   - Fuzzy matches → add to review list
   - No match → add as new model entry
   - Return: `{"imported": N, "fuzzy_review": N, "new": N, "skipped": N}`
   - `dry_run=True` → don't actually import, just return counts

4. **`providers.py` — add OpenRouter pricing to model metadata:**
   - When `_parse_models()` encounters pricing data from OpenRouter, extract: `pricing.prompt` (cost per 1M input tokens), `pricing.completion` (cost per 1M output tokens)
   - Store as `cost_input` and `cost_output` in model metadata (per-token USD)
   - This data feeds into cost-aware routing (Phase E)

5. **`cli.py` — `charon discover --openrouter [--dry-run]` subcommand:**
   - Calls `import_openrouter_models(dry_run=dry_run)`
   - Prints: "Imported N models, N need review (see ~/.charon/discover_review.json), N new, N skipped"
   - `--dry-run` prints counts without importing

**Accept:** `PYTHONPATH=src python3 -m pytest tests/test_discover.py -v -q`

**Tests (extend `tests/test_discover.py`):**
- `test_openrouter_api_parse_real_response` — parse a realistic OpenRouter JSON payload (hardcode sample data, don't call API)
- `test_fuzzy_match_exact` — same ID matches
- `test_fuzzy_match_strips_openai_prefix` — `openai/gpt-4o` → `gpt-4o`
- `test_fuzzy_match_strips_anthropic_prefix` — `anthropic/claude-sonnet-4-5` → `claude-sonnet-4-5`
- `test_fuzzy_match_no_match_returns_none` — unknown ID → None
- `test_fuzzy_match_with_alias_map` — id appears in model_aliases.json → mapped
- `test_import_openrouter_dry_run` — counts are correct, no actual import
- `test_import_openrouter_writes_config` — real import adds models via config
- `test_pricing_maps_to_cost_fields` — OpenRouter pricing.prompt → cost_input, pricing.completion → cost_output

**Gate:** `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

**Constraints:** Stdlib only. Own ONLY the files in the owns list above. Do NOT touch proxy_server.py or gateway.py.
