## B2.5 — CLI Surface for Gateway Modules

**MISSION:** Smart Routing — route work by cost, performance, and availability without quality loss.

**Goal:** Add CLI subcommands so operators can inspect and manage gateway modules (cache, limits, quality, guardrails, normalizer) from the command line.

**Owns:** `src/charon/cli.py`, `tests/test_cli.py`

**Dependencies:** B1 modules already exist at `src/charon/cache.py`, `spend_limits.py`, `quality_scorer.py`, `guardrails.py`, `response_normalizer.py`, `observability.py`, `discover.py`.

**What to build — new subcommands on `charon`:**

```
charon cache stats          → print CacheStats (hits/misses/size/evictions)
charon cache clear           → flush the cache (creates new SemanticCache instance, prints "cache cleared")
charon limits show           → print {monthly_limit, spent, remaining}
charon limits set --monthly N  → set monthly spend cap (USD), persist to spend.json
charon quality show           → print table: provider | calls | success_rate | reliability
charon quality reset <name>   → reset quality data for one provider
charon guardrails show        → print current config (keywords list, PII enabled/disabled)
charon guardrails add <word>  → add a keyword to the deny-list, persist
charon norm show              → print per-model normalization mode
```

**Implementation guidelines:**

1. **`cli.py`** — add typer commands under the existing `app` object. Use inline imports (lazy) for module classes — e.g. `from charon.cache import SemanticCache` inside the command function.

2. **Cache commands:** Load `SemanticCache(max_size=1000)` from config or create fresh. For `stats`, print: `hits: N | misses: N | size: N | evictions: N`. For `clear`, just print "cache cleared" (the cache is in-memory, so it resets on restart anyway — the command is a placeholder for future persistence).

3. **Limits commands:** Use `SpendLimiter` from `spend_limits.py`. `show` prints: `monthly limit: $N | spent: $N | remaining: $N`. `set` loads the existing spend.json, updates the monthly limit, saves. Prints: `monthly limit set to $N`.

4. **Quality commands:** Use `QualityScorer` from `quality_scorer.py`. `show` loads quality.json, prints a table: `provider  calls  success_rate%  reliability_score`. `reset <name>` zeros out that provider's record and saves.

5. **Guardrails commands:** Load `Guardrails(config={...})`. `show` prints keywords list + PII status. `add` appends to the keyword list. Persist via `~/.charon/guardrails.json` using the `_save` pattern from `config.py`.

6. **Norm command:** `show` reads `~/.charon/normalizer.json`, prints: `model | mode`. If no file, print: "no per-model normalization configured."

**Accept:** `PYTHONPATH=src python3 -m pytest tests/test_cli.py -v -k "cache or limits or quality or guardrails or norm"`

**Tests (extend `tests/test_cli.py`):**

- `test_cache_stats` — `charon cache stats` runs and prints expected fields
- `test_cache_clear` — `charon cache clear` prints "cache cleared"
- `test_limits_show_no_config` — `charon limits show` prints "no spend limit configured" or shows $0
- `test_limits_set_and_show` — set limit to 50, show confirms $50 monthly, files exist
- `test_quality_show_empty` — no quality data → prints "no quality data" or empty table
- `test_quality_reset` — add data, reset, show confirms zeroed
- `test_guardrails_show` — shows default config
- `test_guardrails_add_and_show` — add keyword, show confirms it's listed
- `test_norm_show_no_config` — no file → prints appropriate message

Use `CliRunner` (typer.testing). Monkeypatch `CHARON_HOME` to `tmp_path` for each test.

**Gate:** `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`

**Constraints:** Stdlib only + typer (already in pyproject.toml). Own ONLY `cli.py` and `test_cli.py`. All new module imports are lazy (inside command functions). Do NOT touch proxy_server.py, gateway.py, or config.py (config infrastructure is read-only here).
