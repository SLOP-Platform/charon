# Pricing-source dig — Pools Phase-1 grounding (read-only)

## 1. Where `cost_usd` is computed (the call path)

`GatewayProxy.classify()` — `src/charon/proxy.py:306-376`:
- `_gateway_usage(body)` (`proxy.py:115-127`) first reads `usage.cost`/`usage.total_cost`
  straight off the upstream's JSON response — this is **provider-self-reported cost**
  (OpenRouter/opencode-style gateways echo it back per request). If that's non-zero,
  `cost_source = "provider"` (`proxy.py:350-351`) and nothing else runs.
- Only when the provider reports `cost == 0` (`proxy.py:330`) does it fall back to
  `self._lookup_pricing(requested_model, expected_model)` (`proxy.py:378+`), which reads
  `self._model_pricing[model]["cost_input"/"cost_output"]` and computes
  `tokens_in*ci + tokens_out*co` (`proxy.py:337`), tagged `cost_source = "computed"`.
  No pricing found → `cost_source = "unpriced"`, `cost_usd` stays 0.

`self._model_pricing` is populated once, at gateway-config-compile time, in
`gateway.py:273-280` (`compile_gateway_config` or equivalent): it walks the model
**registry** (`models.json`) and copies `cost_input`/`cost_output`/`free` straight off
each model's `spec` dict — the exact same fields `pools.py::derived_cost_rank` reads.
Flows into `GatewayConfig.model_pricing` → `UpstreamRoute`... → `GatewayProxy(model_pricing=...)`
(`proxy_server.py:1033`), refreshed on hot-reload via `apply_routes` → `observer.set_pricing()`
(`proxy_server.py:1106-1113`, `proxy.py:401-405`).

**Contradiction resolved:** the benchmark's non-zero `cost_usd` is coming from the
`"provider"` path (self-reported `usage.cost`), NOT the `"computed"` path. `models.json`
having zero `cost_input`/`cost_output` is fully consistent with `cost_usd` still showing
up — the gateway never needed local pricing because upstream already returned it.
`cost_source` in the response (`proxy_server.py:620`/`1213`) is the field that would
prove this on a live capture; grounding doc should check it says `"provider"`.

## 2. Why `cost_rank` is inert

`pools.py::derived_cost_rank` (`pools.py:62-76`): `explicit cost_rank` if set, else
`1000*100*(3*cost_input+cost_output)/4` blend if `cost_input`/`cost_output` present,
else hardcoded fallback **1000**. Same `cost_input`/`cost_output` fields as §1 — and
they're absent from `models.json` for all 201 models on the live `/data` volume
(verified against `/home/stack/backups/charon-4lom-zen-demote-20260707-160026/models.json`;
zero of 201 entries carry either field, across every provider incl. openrouter). Every
non-free entry there already carries an **explicit** `cost_rank: 1000` (not derived —
someone wrote the literal fallback value in at add-time), so `derived_cost_rank` never
even reaches the pricing branch for these; free-first + stable-order is the only real
signal the pool sort currently has.

## 3. Where real pricing would need to land, and why it never has

The intended auto-population path exists but is dormant:
- `discover.py::_update_model_pricing_from_discovery` (`discover.py:189-244`) hits each
  configured provider's `/models` endpoint and, via `providers._extract_pricing`
  (`providers.py:177-204`), copies an **OpenRouter-shaped `pricing: {prompt, completion}`**
  object into `cost_input`/`cost_output`, stamping `priced_by: "discovery"` (clobber-safe —
  never overwrites an operator-set price). Problem: only OpenRouter's own catalogue
  actually returns that `pricing` object; opencode-zen/opencode-go/nanogpt/neuralwatt
  `/models` responses don't, so discovery runs but extracts nothing for ~150 of 201
  models.
- `discover.py::import_openrouter_models` (`discover.py:316-377`) is the one path that
  hits OpenRouter's real pricing-bearing catalogue (`_OPENROUTER_API`) — but it
  fuzzy-matches Charon's own aliased ids (e.g. `gpt-5-or`) against OpenRouter's raw ids
  (`openai/gpt-5`) via `fuzzy_match_model_id` (`discover.py:287-313`); stage-1 exact
  matches auto-import pricing, everything else lands in `discover_review.json` for
  manual review and is never priced automatically. Aliased ids like `*-or`/`*-ng`/`*-cb`
  don't stage-1-match, so this path is effectively unused for the live registry too.
- **Injection point:** `models.json[mid]["cost_input"/"cost_output"]` is the single seam
  both `cost_usd`-computation (`gateway.py:277`) and `cost_rank` (`pools.py:69-70`)
  already read — no new field/plumbing needed. Cleanest real-pricing source is
  `import_openrouter_models`'s existing OpenRouter-catalogue fetch (same numbers
  `cost_usd`'s computed-path would use), but Phase-1 needs either (a) a proper alias
  map (`_ALIAS_FILE`/`model_aliases.json`, `discover.py:250,271-280`) so `*-or` ids
  stage-1-match their OpenRouter counterparts, or (b) a models.dev import as a second
  source keyed directly by upstream_model rather than the display id.

## 4. Live vs. repo defaults

No `models.json` ships in the repo (`src/charon/`) — it's pure runtime state under the
operator's config/state dir (`.charon/` or `/data` in the container), consistent with
INV-P0 (operator tunes without a redeploy). The backup snapshot at
`/home/stack/backups/charon-4lom-zen-demote-20260707-160026/models.json` is the only
concrete instance inspected: 201 models, 0 with `cost_input`/`cost_output`, all
non-free entries carrying literal `cost_rank: 1000`. `pools.json`/`providers.json` in
the same snapshot weren't inspected for cost fields (pools.json is role→id lists, no
pricing; providers.json wasn't checked — out of scope for this dig, flag if Phase-1
needs it).
