# RESEARCH — adoptable machine-readable sources for the model-quality SEED PRIOR

Date: 2026-07-26 · Scope: turn `SEED_PRIOR` (hardcoded Python literal) into refreshable DATA.
Method: ADOPT-FIRST. Every "VERIFIED" claim below was produced by actually fetching the
endpoint from this box (curl / urllib), not from docs or memory.

---

## 0. GROUND TRUTH IN OUR OWN CODE (VERIFIED — read the files)

**The brief's premise about work classes is wrong, and this changes the whole mapping problem.**

| Item | Brief said | Code actually says (VERIFIED) |
|---|---|---|
| Work classes | 12: bugfix, routing, money-path, rig-meta, design-review, docs, tests, refactor, ci-infra, frontend, greenfield-feature, generalist | **6**: `reasoning, coding, translation, creative, analysis, general` |
| Entry count | 33 | **43** `PriorEntry` rows |

- `src/charon/routing_policy/matrix.py:20` — `WorkClass = Literal["reasoning","coding","translation","creative","analysis","general"]`
- `src/charon/routing_policy/matrix.py:15` — `Grade = Literal["A","B","C","D","F","unknown"]`
- `src/charon/capability/grades_import.py` — `_SEED_PRIOR` = 43 entries; `DEFAULT_PRIOR_WEIGHT = 0.5`;
  `Provenance = Literal["aider-polyglot","lmarena","artificial-analysis","models-dev","operator-curated"]`
- The 12 names in the brief are the **rig's ticket `work_class` vocabulary**, not the product's
  routing taxonomy. `src/charon/capability/taxonomy.py` is a separate open/append-only
  taxonomy with a crystallizer; it is NOT the `matrix.WorkClass` literal.

**What the 43 entries actually contain (VERIFIED by importing the module):**
- per work_class: `reasoning` 8, `coding` 8, `general` 8, `analysis` 7, `translation` 6, `creative` 6
- per provenance: `lmarena` 14, `models-dev` 13, `artificial-analysis` 10, `aider-polyglot` 6, `operator-curated` **0**
- **only 9 distinct models**: `claude-opus-4.5, deepseek-v4-pro, gemini-3-pro, glm-5.2, gpt-5, kimi-k2.6, llama-4-405b, minimax-m2.7, qwen-3-coder`
- → The prior **already misses most of what we route**: no `deepseek-v4-flash`, no `minimax-m2.5`/`m3`, no `devstral`, no `mistral`. It also carries `llama-4-405b` (not routed) and `claude-opus-4.5` (never routed via SG). **The coverage problem is worse than the refresh problem** — worth saying out loud when this is ticketed.

**Consequence (good news):** we only need to map external benchmarks onto **6** coarse buckets,
not 12 SDLC-shaped ones. That is a far more tractable mapping — several sources publish
categories that line up almost 1:1. **Do not attempt a 12-class mapping; no source supports it.**

### ⚠️ BLOCKING CONTEXT: the seed prior is currently INERT (VERIFIED)

`SEED_PRIOR` / `seed_matrix()` / `GradesImport` have **zero production consumers**. The only
importer in the entire repo is `tests/test_grades_import.py`. The live gateway builds a **bare,
empty** matrix:

```
src/charon/gateway.py:549    server.capability_matrix = routing_policy.CapabilityMatrix()
```

No call to `seed_matrix()`, no `grades_import` import anywhere outside tests. So today the prior
does not influence routing at all — the cold-start problem it was written to solve is **still
unsolved in the live path**.

**Recommendation consequence:** making the prior *refreshable* is real but **second-order**.
Wiring it into `gateway.build_server` is the higher-value change and should be sequenced FIRST or
alongside — otherwise we will have built a refresh pipeline that keeps a dead table up to date.
Flag this when the ticket is written; it materially changes the value case.

Other verified in-repo facts:
- `pyproject.toml:21` — `dependencies = []` (core is stdlib-only; `litellm` is an *optional* extra).
  → **the refresher must parse JSON via stdlib, not parquet** (parquet needs pyarrow ≈ new core dep).
- `src/charon/netutil.py:264,302` — `keyed_request()` / `open_keyed()` is the sanctioned,
  SSRF-guarded, stdlib-urllib egress path. Any fetch MUST go through it (there is an
  executed gate that has previously caught a bare `urlopen`).
- `src/charon/routing_policy/catalog_refresh.py` — the refresher pattern to reuse (see §5).

---

## 1. RANKED RECOMMENDATION (summary)

| # | Source | Quality signal | Per-class fit to our 6 | Coverage of our models | Licence | Verdict |
|---|---|---|---|---|---|---|
| **1** | **LMArena `leaderboard-dataset`** — `text` **+ `agent`** configs | Elo + CI + votes; **`agent` gives a true agentic score** | **5 of 6 directly, 6th by proxy** | **11 of 12** (all but devstral) | **CC-BY-4.0** ✅ | **ADOPT — vendor + opt-in refresh** |
| **2** | **Terminal-Bench 2.1** (`harbor-framework/terminal-bench-2-1`) | accuracy + stderr + pass@k + **cost + latency + reward-hacks** | agentic-coding only | ~3 of 12 (frontier-closed heavy) | **Apache-2.0** ✅ | **ADOPT as 2nd provenance** — richest schema, current |
| 3 | **LiveBench** | 0-100 per task | **6 of 6, sharpest coding** | 8 of 12 | ❌ **UNLICENSED** | runtime-fetch only, never vendor |
| 4 | **Artificial Analysis** | intelligence + coding index | coding/math only | high | ⚠️ no redistribution grant | optional, user's own key |
| 5 | **Epoch.ai `benchmarks.csv`** | raw scores | math/reasoning only | ~6 of 12 | **CC-BY** ✅ | corroboration only |
| 6 | **models.dev** | **NONE** | — | **best (12 of 12)** | **MIT** ✅ | **catalog/join spine, not quality** |
| 7 | **LiteLLM `model_prices…json`** | **NONE** | — | high | MIT (already a dep) | pricing only — do NOT over-claim |
| 8 | **Aider polyglot** | pass-rate | coding only | **0 of 12 current models** | Apache-2.0 ✅ | licence-clean but **coverage-dead** |
| — | HF Open LLM Leaderboard | stale 16 months | — | ~0 | apache-2.0 | **DEAD — do not use** |

---

## 2. SOURCE-BY-SOURCE

### 2.1 ★ LMArena `lmarena-ai/leaderboard-dataset` — **THE #1 PICK** (VERIFIED)

- **Data URL (stdlib-friendly JSON, no key):**
  `https://datasets-server.huggingface.co/filter?dataset=lmarena-ai%2Fleaderboard-dataset&config=text&split=latest&where=%22category%22%3D%27coding%27&offset=0&length=100`
  (paged, 100 rows/req). Parquet mirror: `https://huggingface.co/datasets/lmarena-ai/leaderboard-dataset/resolve/main/text/latest-00000-of-00001.parquet` (1,311,716 B — **avoid**, needs pyarrow).
- **Format:** JSON rows (REST) / parquet (mirror). `text/latest` split = 25,056 rows.
- **Schema (VERIFIED, exact field names):**
  `model_name, organization, license, rating, rating_lower, rating_upper, variance, vote_count, rank, category, leaderboard_publish_date`
- **Cadence:** dataset `lastModified 2026-07-25`; latest `leaderboard_publish_date` = **2026-07-21**. ~weekly. **5 days stale at time of writing — the freshest of any *usably-licensed* source.** (SWE-bench-Live is one day fresher but is unlicensed and scaffold-keyed — see §2.10.)
- **LICENCE: `cc-by-4.0`** — VERIFIED from the HF API (`tags: ['license:cc-by-4.0']`, `cardData.license: cc-by-4.0`). **Attribution only → SAFE to vendor a derived snapshot into the PUBLIC MIT repo**, provided we credit LMArena in the data file header + NOTICE. This is the only high-coverage source that is unambiguously vendorable.
- **Categories (VERIFIED, 29 sampled across the split):**
  `overall, coding, creative_writing, math, hard_prompts, hard_prompts_english, expert, instruction_following, longer_query, multi_turn, exclude_ties, english, non_english, chinese, japanese, korean, french, german, spanish, russian, polish, industry_software_and_it_services, industry_mathematical, industry_legal_and_government, industry_medicine_and_healthcare, industry_life_and_physical_and_social_science, industry_business_and_management_and_financial_operations, industry_entertainment_and_sports_and_media, industry_writing_and_literature_and_language`
- **Extra configs (VERIFIED from siblings list):** `text, text_style_control, agent, agent_tool_hallucination, agent_steerability, agent_bash_recovery_steps, agent_task_outcome_explicit, agent_praise_complaint, webdev, search, document, vision, …` — the `agent/latest` parquet is only 7,259 B. **`agent*` is directly relevant to us** (tool-use / agentic competence) and is the same CC-BY dataset.
- **Coverage — VERIFIED against `category='coding'` @ 2026-07-21 (373 distinct models):**

  | our model | present in LMArena coding | example ids |
  |---|---|---|
  | deepseek-v4-pro / flash | ✅ (20 deepseek ids) | `deepseek-v4-pro` (1505, MIT), `deepseek-v3.2` |
  | minimax-m2.5 / m2.7 / m3 | ✅ **all three** (6 ids) | `minimax-m2.5` (1505), `minimax-m2.7`, `minimax-m3` (1506) |
  | glm-5.2 | ✅ (17 glm ids) | `glm-5.2 (max)` (1513, MIT), `glm-5.1` (1525) |
  | kimi-k2.6 | ✅ (7 kimi ids) | `kimi-k2.6`, `kimi-k2.5-thinking`, `kimi-k3` |
  | gemini-3.x | ✅ (9 ids) | `gemini-3-pro`, `gemini-3.1-pro-preview`, `gemini-3.5-flash-high` |
  | gpt-5.x | ✅ (18 ids) | `gpt-5.1-high`, `gpt-5-chat`, … |
  | qwen | ✅ (38 ids) | `qwen3.x` family |
  | mistral | ✅ (14 ids) | `mistral-large-3`, … |
  | **devstral** | ❌ **0 rows** | — |

  → **11 of 12 model families covered. Only `devstral` is absent** (graded only by licence-blocked sources — see §3.3).
- **Scraping needed?** No. Structured REST + parquet. GOOD.

#### ★★ The `agent` config is the best single signal found — use it (VERIFIED)

Same dataset, same CC-BY-4.0 licence, different config:
`https://datasets-server.huggingface.co/rows?dataset=lmarena-ai%2Fleaderboard-dataset&config=agent&split=latest&offset=0&length=100`

- **38 rows, one category (`overall`), `leaderboard_publish_date = 2026-07-21`.** Tiny (7,259 B parquet).
- **DIFFERENT schema from `text`** — note this, it will break a naive shared parser:
  `model_name, organization, license, score, score_ci_lower, score_ci_upper, observation_count, session_count, rank, category, leaderboard_publish_date`
  (`score`, **not** `rating`; `observation_count`/`session_count`, **not** `vote_count`.)
- `score` is a normalised agentic score, observed range **-0.150 … +0.127**, with CI bounds and
  `observation_count` in the 10^5-10^6 range — i.e. well-powered.
- **Why this matters:** this is *agentic tool-using work*, which is what Charon actually routes —
  a far better prior for us than chat-preference `coding` Elo. It is the closest public proxy to
  our own workload that exists under a vendorable licence.
- **Coverage (VERIFIED, full 38-model listing read):** `DeepSeek V4 Pro` (-0.012), `DeepSeek V4 Flash`
  (-0.035), `GLM 5.2 (Max)` (0.065), `GLM 5.1` (0.014), `Kimi K2.6` (-0.026), `Kimi K2.7 Code` (-0.010),
  `Kimi K3` (0.097), `Minimax M3` (-0.031), `Minimax M2.7` (-0.125), `Qwen3.7 Max` (0.001),
  `Qwen3.7 Plus` (-0.008), `Gemini 3.1 Pro Preview` (-0.005), `Gemini 3.5 Flash (High)` (-0.010),
  `Gemini 3 Flash` (-0.086), `GPT 5.6 Sol (xHigh)` (0.101), `GPT 5.5 (xHigh/High)`, `GPT 5.4 (High)`,
  plus `Grok`, `Gemma 4 31B`, `Mimo V2.5 Pro`, `Nemotron 3 Ultra`.
  ❌ Absent: **devstral, mistral, minimax-m2.5, qwen3-coder.**
- **ALIAS WARNING (VERIFIED):** the `agent` config uses **title-case display names with parenthesised
  effort** (`DeepSeek V4 Pro`, `GLM 5.2 (Max)`, `GPT 5.6 Sol (xHigh)`) while the `text` config uses
  **lowercase hyphenated** ids (`deepseek-v4-pro`, `glm-5.2 (max)`, `gpt-5.4-high`). **The two configs
  do not share a naming convention.** Any alias map must be built per-config. This is the single
  concrete reason the spike's step 2 is the go/no-go.

- **Gotchas (VERIFIED):**
  - Rows are per `(model_name, category, leaderboard_publish_date)`. Always filter to `max(leaderboard_publish_date)` — the split retains history.
  - Duplicate `model_name` values appear at one date with different ratings (variant/style-control rows). **Dedup by taking max `vote_count` per `(model_name, category)`,** don't blind-`dict()` them.
  - `where=` filtering works on `category`; a `where` on `leaderboard_publish_date` was **silently ignored** in testing (returned the full 25,056) — filter dates client-side.
  - `rank` is per-category-per-date and has ties; prefer `rating` for banding.

### 2.2 LiveBench — best category granularity, **licence-blocked for vendoring** (VERIFIED)

- **Data URL:** `https://livebench.ai/table_2026_06_25.csv` (HTTP 200, 7,644 B, **45 models**).
  GitHub copy of the *same filename* is only 4,902 B / 28 models — **the live site is ahead of the repo.**
  Category map: `https://livebench.ai/categories_2026_06_25.json` (725 B).
- **Format:** CSV, `model` + **23 task columns**, scores 0-100. No key, no scraping.
- **Categories (VERIFIED, fetched the JSON):** `Reasoning` (theory_of_mind, zebra_puzzle, spatial, logic_with_navigation) · `Coding` (code_generation, code_completion) · `Agentic Coding` (javascript, typescript, python) · `Mathematics` (AMPS_Hard, integrals_with_game, math_comp, olympiad) · `Data Analysis` (consecutive_events, tablejoin, tablereformat) · `Language` (connections, plot_unscrambling, typos) · `IF` (paraphrase, simplify, story_generation, summarize).
  → **This maps onto our 6 classes better than anything else found.**
- **Cadence:** dated snapshots, contamination-windowed. Available tables (VERIFIED listing): `2024_06_24, 2024_07_26, 2024_08_31, 2024_11_25, 2025_04_02, 2025_04_25, 2025_05_30, 2025_11_25, 2025_12_23, 2026_01_08, 2026_06_25`. Latest = **2026-06-25 (1 month old)**. `table_2026_07_09` and `_07_25` → **404** (I probed; no newer table).
  **Important:** each refresh re-runs only a *subset* of models, so the model set churns — `2026_01_08` is 20,925 B (more models) while `2026_06_25` is 4,902 B in-repo. A model can silently vanish between snapshots.
- **LICENCE: ❌ BLOCKING for vendoring.** VERIFIED:
  - `https://raw.githubusercontent.com/LiveBench/livebench.github.io/main/LICENSE` → **HTTP 404**; GitHub API reports `license: null` for the repo that actually holds the CSVs.
  - `LiveBench/LiveBench` (the code repo) → `NOASSERTION` (pushed 2026-07-26, active).
  - HF datasets `livebench/{coding,reasoning,math,language,data_analysis,instruction_following,model_judgment}` → **no license tag at all**, and all `lastModified 2025-04-07` (those are the question sets, not results).
  → The *scores themselves carry no licence grant*. **Do not check a LiveBench snapshot into the public repo.** Runtime-fetch behind the opt-in flag with visible attribution is the defensible pattern; a vendored copy is not.
- **Coverage (VERIFIED, all 45 model ids read):** ✅ `deepseek-v4-pro`, `deepseek-v4-flash`, `glm-5.2`, `kimi-k2.6-thinking`, `kimi-k2.7-code`, `kimi-k3`, `minimax-m3`, `gemini-3.1-pro-preview-high`, `gemini-3.5-flash-high`, `gemini-3.6-flash-high`, `gpt-5.2…5.6`, `qwen3.6-27b`, `qwen3.6-plus`, `qwen3.7-max`, `grok-4.3/4.5`.
  ❌ **Missing: `devstral`, `mistral`, `qwen3-coder`, `glm-4.x`, `minimax-m2.5`, `minimax-m2.7`.**
  → 8 of 12 families. Notably **worse** than LMArena on minimax/mistral.
- **Net:** sharper signal, weaker coverage, unusable licence for a checked-in default. Perfect as an
  **optional second provenance** once the LMArena path exists.

### 2.3 Artificial Analysis — has literally the right index, but you may not redistribute it

- **Endpoint:** `https://artificialanalysis.ai/api/v2/data/llms/models` (VERIFIED → **401** without a key).
- **Access:** free account key (`x-api-key`), ~1,000 req/day free tier.
- **Fields:** `artificial_analysis_intelligence_index`, **`artificial_analysis_coding_index`**, `artificial_analysis_math_index`, MMLU-Pro, GPQA, pricing, tok/s, TTFT.
- **LICENCE VERDICT: ⚠️ cannot vendor.** Docs grant only *"Attribution is required for all use of our free API"* — there is **no redistribution/republication grant**, no CC licence. Absence of a grant ≠ permission. (This specific reading is **INFERRED** from the absence of a licence, not from an explicit prohibition.)
- **Fit:** it is the only source with a purpose-built *coding index*, but it gives 2-3 indices, not our 6 classes.
- **Use:** optional runtime enrichment behind the operator's OWN key. Never a checked-in default.

### 2.4 Epoch.ai — CC-BY and clean, but wrong shape for us (VERIFIED)

- **URL:** `https://epoch.ai/data/benchmarks.csv` (HTTP 200, **2,310,639 B**, 1,011 rows).
  (The brief's `epoch.ai/data/ai-benchmarking-dashboard` is the HTML page; `benchmarks.csv` is the data.)
- **Schema (VERIFIED, long format):** `id_runs, task, model, Best score (across scorers), Scores, started_at, Status, Model, Version release date, Organization, Model accessibility, mean_score, stderr, best_score, original_task_name, …` (60+ cols, mostly model-metadata).
- **Tasks (VERIFIED counts):** GPQA diamond 183 · OTIS Mock AIME 156 · MATH level 5 108 · FrontierMath (several tiers) ~290 · SimpleQA Verified 66 · Chess Puzzles 58 · **SWE-Bench verified only 35**.
  → **Math/reasoning-heavy; almost no coding signal.** Maps to our `reasoning` bucket and nothing else.
- **Cadence:** latest run 2026-07-24 — fresh.
- **LICENCE: ✅ CC-BY** — *"free to use, distribute, and reproduce provided the source and authors are credited under the Creative Commons Attribution license"* (VERIFIED quote; CC version not stated on the page).
- **Coverage (VERIFIED against the CSV's `Model` column):** glm ✅ (GLM-4.5→5.1), kimi ✅ (K2 Thinking→K3), qwen ✅ (18), gpt-5 ✅ (17), mistral ✅ (7), **deepseek stops at R1/V3 — no V4** ❌, **minimax 0** ❌, **devstral 0** ❌, **`gemini-3` 0** ❌ (naming differs; Gemini entries exist under other display names — treat as INFERRED).
- **Net:** good licence, real data, but it cannot inform `coding`/`creative`/`translation` and misses deepseek-v4 + minimax. **Corroboration only.**

### 2.5 models.dev — zero quality signal, but the best CATALOG SPINE (VERIFIED)

- **URL:** `https://models.dev/api.json` — 3.24 MB, **172 providers / 5,756 model entries**.
- **Complete field list (VERIFIED):** `id, name, description, family, attachment, reasoning, reasoning_options, tool_call, interleaved, structured_output, temperature, knowledge, release_date, last_updated, modalities, open_weights, limit{context,output}, cost{input,output,cache_read,cache_write}, experimental, status, provider`.
- **There is NO benchmark / elo / score / quality field of any kind.** The brief's suspicion is correct — **and note `grades_import.Provenance` currently lists `"models-dev"` as a provenance for 13 of the 43 seed entries. That provenance is not supportable: models.dev publishes no quality data.** Those 13 entries are in truth `operator-curated`. **Fix the provenance labels when this becomes data.**
- **LICENCE: ✅ MIT** (`sst/models.dev` now redirects to `anomalyco/models.dev`, default branch `dev`, `LICENSE` = MIT, © 2025 models.dev). Pushed 2026-07-26. Safe to vendor.
- **Coverage: the best of any source — 12 of 12** (deepseek-v4 30 ids, glm-5 80, kimi-k2 90, minimax-m2 52, gemini-3 57, gpt-5 151, qwen3-coder 31, **devstral 20**, mistral 137).
- **Use: the join key / id-normalisation spine.** It is the only source that knows `devstral` exists.

### 2.6 LiteLLM `model_prices_and_context_window.json` — pricing ONLY (VERIFIED locally)

- **Path on this box:** `/home/stack/.local/lib/python3.12/site-packages/litellm/model_prices_and_context_window_backup.json` — **2,954 entries**. Upstream: `https://raw.githubusercontent.com/BerriAI/litellm/main/model_prices_and_context_window.json`.
- **Every field, by frequency (VERIFIED, computed):** `litellm_provider` 2953 · `mode` 2945 · `max_input_tokens` 2535 · `input_cost_per_token` 2481 · `output_cost_per_token` 2478 · `max_tokens` 2472 · `max_output_tokens` 2368 · `supports_function_calling` 1701 · `supports_tool_choice` 1576 · `supports_vision` 955 · `supports_response_schema` 928 · `source` 904 · `supports_reasoning` 774 · `cache_read_input_token_cost` 688 · `supports_prompt_caching` 628 · … `deprecation_date` 93 · `rpm`/`tpm` 51.
- **VERDICT — do not over-claim: there is NOT ONE quality/benchmark/score/elo field.** It is pricing + context-window + boolean capability flags. It can tell you a model *supports* reasoning; it can never tell you whether it is *good at* reasoning.
- **Licence:** MIT (LiteLLM), and it is **already a dependency** (optional `router` extra).
- **Correct role:** cost + capability gating that runs *alongside* the quality prior. It is complementary, not a substitute.

### 2.7 Aider polyglot — licence-clean, **coverage-dead** (VERIFIED; contradicts the brief's hope)

- **URL:** `https://raw.githubusercontent.com/Aider-AI/aider/main/aider/website/_data/polyglot_leaderboard.yml` (HTTP 200, 45,725 B, **69 entries**).
  Siblings in the same dir (VERIFIED listing): `edit_leaderboard.yml` (56,178 B), `refactor_leaderboard.yml`, `architect.yml`, `qwen3_leaderboard.yml`, `o1_polyglot_leaderboard.yml`, `code-in-json.yml`, `quant.yml`, `blame.yml`, `deepseek-down.yml`.
- **Format:** YAML. **Schema (VERIFIED):** `dirname, test_cases, model, edit_format, commit_hash, pass_rate_1, pass_rate_2, pass_num_1, pass_num_2, percent_cases_well_formed, error_outputs, num_malformed_responses, user_asks, lazy_comments, syntax_errors, indentation_errors, exhausted_context_windows, test_timeouts, total_tests, command, date, versions, seconds_per_case, total_cost`.
  (Note: **YAML → a new parse dep** unless we pre-convert to JSON at vendor time. Core is stdlib-only.)
- **LICENCE: ✅ Apache-2.0** (repo-level, VERIFIED via GitHub API; not archived).
- **Cadence: DEAD for our purposes.** VERIFIED: `date` field range = 2024-12-21 → **2025-10-03**. Last commit touching the file = **2025-10-04** ("chore: update deepseek model names"). Repo last pushed 2026-05-22, but the leaderboard data has not moved in **~10 months**.
- **Coverage of our 12 (VERIFIED by grepping the `model:` lines): effectively ZERO.**
  Newest relevant entries are `gpt-5 (high/medium/low)`, `DeepSeek-V3.2-Exp`, `Kimi K2` (original), `Qwen3 235B`.
  **Absent: deepseek-v4-pro/flash, minimax-m2.5/m2.7/m3, glm-5.2, kimi-k2.6, gemini-3.x, qwen3-coder, devstral, mistral (current).**
- **Verdict:** the brief's lead was correct about *format and licence* and wrong about *usefulness*.
  It is a clean Apache-2.0 YAML file describing models we no longer route.
  **`Provenance = "aider-polyglot"` on 6 current seed entries is stale and should be re-labelled.**

### 2.8 HuggingFace Open LLM Leaderboard — **DEAD** (VERIFIED)

- `https://datasets-server.huggingface.co/rows?dataset=open-llm-leaderboard%2Fcontents&config=default&split=train` — reachable, 4,576 rows, schema `eval_name, Model, fullname, Average ⬆️, IFEval, BBH, MATH Lvl 5, GPQA, MUSR, MMLU-PRO, #Params (B), Hub License, Type, Precision, MoE`.
- **`lastModified 2025-03-20` — frozen 16 months.**
- **Covers only open-weight HF repos:** zero API/closed models (no gpt-5, no gemini-3) and zero modern large open models (no deepseek-v4, kimi-k2, glm-5, minimax). Filtering `#Params (B) > 100` yields **13 rows**, topping out at `Qwen1.5-110B` — 2024-era.
- Licence apache-2.0, irrelevant. **Do not build on this.**

### 2.9 Sources with no usable structured quality data (VERIFIED negatives)

- **OpenRouter** `https://openrouter.ai/api/v1/models` — 343 models, 534 KB, fields `id, canonical_slug, hugging_face_id, name, created, description, context_length, architecture, pricing, top_provider, supported_parameters, reasoning, knowledge_cutoff, …`. **No ranking/elo/usage field.** `/api/frontend/models/find` and `/api/frontend/stats/leaderboard` → **404**. Their public rankings page is scrape-only → BAD.
- **llm-stats.com** `https://api.llm-stats.com/v1/models` — 85 entries, routing/pricing only (`context_length, input_price, output_price, quantization_type, routing_providers, tier`). Not a benchmark aggregator. `llm-stats.com/api/models` → 404.
- **Vals AI** — SPA; `/api/leaderboard` → 404. Scrape-only → BAD.

### 2.10 The agentic-coding benchmark cluster (all VERIFIED by fetch)

#### ★ Terminal-Bench 2.1 — the strongest COMPLEMENT; Apache-2.0 and current

- **The repo moved:** `github.com/laude-institute/terminal-bench` → **301** → **`github.com/harbor-framework/terminal-bench`** (the org rebranded to Harbor; all `laude-institute/*` repos are frozen at 2025). Any doc still citing laude-institute is stale.
- **Data URL (per-submission JSON):**
  `https://raw.githubusercontent.com/harbor-framework/terminal-bench-2-1/main/leaderboard/submissions/<file>.json`
  listing via `https://api.github.com/repos/harbor-framework/terminal-bench-2-1/contents/leaderboard/submissions` — **20 result files**. Filename is itself the key: `YYYY-MM-DD-<org>-<model>-<effort>-<agent>.json`.
- **Dead ends (VERIFIED empty/404, do not chase):** `tbench.ai/api/leaderboard` → 404 (site is Next.js RSC, no JSON API) · `laude-institute/terminal-bench-2-leaderboard` = LICENSE+README only · `harbor-framework/terminal-bench-2/leaderboard/submissions` = **0 files** · `harbor-framework/harbor-index/leaderboard/submissions` = **0 files** · `leaderboard/leaderboard.yaml` is a **JSON-Schema config, not results** (points at a `visibility: private` hosted hub).
- **Schema — the richest of any source found:**
  `source_filter{agent, agent_version, model_name, reasoning_effort}` ·
  `metadata{agent_display, agent_org, model_display, model_org, date, reasoning_effort, pr_url}` ·
  `metrics{accuracy, accuracy_stderr, n_trials, pass_at_2..5, uncached_input_tokens, cached_input_tokens, output_tokens, total_cost_usd, avg_trial_duration_sec, reward_hacks}` · `trials[]`, `disqualified_trials[]`
- **Why it matters beyond quality:** `avg_trial_duration_sec` + `total_cost_usd` + `reward_hacks` feed directly into *latency-is-a-failure-class* and the cost meter — no other source carries these.
- **Model-keyed AND agent-keyed in SEPARATE fields** (`source_filter.model_name` vs `source_filter.agent`), so **the scaffold can be marginalised out** — the thing SWE-bench Verified gets wrong. `trials[]` allows per-task breakdown.
- **LICENCE: ✅ Apache-2.0** (LICENSE file fetched). **Vendorable.**
- **Cadence:** active, most recent entry **2026-07-11** (15 days).
- **Coverage: frontier-closed-heavy, OSS-thin.** ✅ `gemini-3-pro-preview`, `gemini-3.1-pro-preview`, `gpt-5.5`, `gpt-5.6-*`, `glm-5.1-max`, `grok-4.5`, claude-*. ❌ **NO deepseek (any), kimi, minimax, qwen3-coder, devstral, mistral, glm-5.2.**
  → ~3 of our 12. **Cannot stand alone as the prior; excellent as a second provenance for the models it does cover.**

#### SWE-bench / SWE-bench-Verified — stale AND licence-blocked

- **Aggregate file is NOT in `SWE-bench/experiments`** (that repo is `license: null` → all-rights-reserved, pushed 2026-03-29). It is in the website repo:
  `https://raw.githubusercontent.com/SWE-bench/swe-bench.github.io/master/data/leaderboards.json` — **7,323,841 B**, VERIFIED. (`https://www.swebench.com/data/leaderboards.json` → **404**; GitHub raw only.)
- **LICENCE: ❌ CC BY-NC 4.0 (NonCommercial)** on `swe-bench.github.io` — VERIFIED by fetching the LICENSE. **Hard blocker**: NC poisons downstream commercial use of a public product repo. `SWE-bench/experiments` having *no* licence is worse.
- **Cadence:** boards run 2023-10 → **2026-02-26**; ~5 months stale and decaying.
- **Keying — cuts both ways:** the `Verified` board (180 entries) is **SCAFFOLD-keyed** (`mini-SWE-agent + Claude 4.5 Opus (high reasoning)`) — string surgery required. The **`bash-only` board (48 entries)** pins one scaffold and varies only the model, carrying structured `tags` with `Model:`/`Org:` — **genuinely model-keyed and the one worth reading**.
- `per_instance_details` (instance_id → resolved/cost/api_calls) would allow per-repo work-class breakdowns.
- **Coverage of `bash-only` (118 distinct Model tags):** ✅ `deepseek-v3.2`, `glm-5`/`glm-4.6`, `kimi-k2.5`, `minimax-m2`/`m2.5`, `Qwen3-Coder-480B`/`30B`, **`devstral-2512`/`devstral-small-2512`** (the ONLY quality data found anywhere for devstral), gpt-5.x, gemini-3-pro/flash-preview. ❌ no deepseek-v4, glm-5.2, kimi-k2.6, minimax-m3.
- **Verdict: read-only reference, DO NOT VENDOR.** Its devstral rows are tantalising but NC-licensed.

#### SWE-bench-Live — freshest data, but unlicensed and scaffold-keyed

- `https://raw.githubusercontent.com/SWE-bench-Live/swe-bench-live.github.io/main/reports-0605.jsonl` — 413,734 B, **142 rows**, JSONL. (Filename says `0605`; contents run to **2026-07-16** — the freshest of any source.)
- Schema is thin: `{name, set, total, resolved, date, logo, url}`. **`set` gives a real language axis** (`go, tsjs, java, rust, lite, windows`) — routing signal unavailable elsewhere.
- **SCAFFOLD-keyed and badly:** `name` is free text (`"Slingshot + GPT-5.5 (Medium)"`); the model must be regex'd out with no separate field.
- **LICENCE: ❌ none** (`license: null`) → blocking. Upstream `microsoft/SWE-bench-Live` is MIT but that is the harness, not the results.
- Coverage: frontier-closed only; **none of our OSS models.**

#### SWE-rebench — best OSS coverage anywhere, worst access

- **No API.** VERIFIED 404 on `/api/leaderboard`, `/leaderboard.json`, `/api/results`, `/api/models`, `/data/leaderboard.json`. 25 Next.js chunks grepped: **zero fetch endpoints**. Data is embedded in a **13,148,905-byte RSC payload** in the page HTML → scraping only. **BAD.**
- **TRAP (worth flagging):** HF dataset `nebius/SWE-rebench-leaderboard` (cc-by-4.0, lastModified 2026-06-01) is **misleadingly named — it is the TASK dataset, not scores.** Features are `repo, instance_id, base_commit, patch, test_patch, problem_statement, FAIL_TO_PASS, …`. **No model column, no score column.** Do not build on the name.
- Coverage (grepped from HTML): `DeepSeek-V4`, `GLM-5.2`, `GLM-5.1`, `Qwen3.6-*`, `Qwen3-Coder-Next/480B/30B`, `MiniMax`, `Kimi`, `Devstral-Small-2505`, gpt-5.1…5.5, claude-4.x. Monthly, contamination-free.
- **Verdict: exactly the models we care about, delivered by exactly the mechanism we refuse to adopt.** Revisit only if they publish an API.

#### LiveCodeBench / BigCodeBench / EvalPlus — all three DEAD

- **LiveCodeBench:** runner repo MIT but pushed **2025-07-16**, and **contains no results file at all**. Site repo pushed 2025-08-01, `license: null`. HF Space `livecodebench/leaderboard` `lastModified 2024-06-07`. `LiveCodeBench/submissions` holds per-model 5.7 MB raw per-problem dumps with **no aggregate score field**, newest model `Claude-Opus-4`. Contamination-windowing means any self-computed score is meaningless without the window — and the window metadata isn't published. **Skip.**
- **BigCodeBench:** `bigcode-project/bigcodebench` is **`archived: true` (2026-01-03)**. Backing HF result datasets last modified **2025-04-17**; ELO variants stop 2025-01-14. **Dead — do not use.**
- **EvalPlus:** results file DOES exist and is clean —
  `https://raw.githubusercontent.com/evalplus/evalplus.github.io/main/results.json` (34,305 B, Apache-2.0, model-keyed, schema `{model: {link, open-data, prompted, size, "pass@1":{humaneval, humaneval+, mbpp, mbpp+}}}`, 125 models).
  **But the site repo last pushed 2024-12-26 — 19 months dead**, and the 125 models are `OpenCoder-8B`, `gemma-2b`, `Phi-3-mini`, `stable-code-3B`. **Zero models from our list.** Nice schema, museum content.
- **Multi-SWE-bench:** Apache-2.0 but pushed 2025-12-18; `ByteDance-Seed/Multi-SWE-bench` → 404. No refreshed feed.
- **Community evals (Kilo / Cline / RooCode): nothing structured.** `Kilo-Org/kilocode` very active but ships no eval data; `cline/cline` → 404; `RooCodeInc/Roo-Code` has **removed** its `evals/` directory. **Skip the whole category.**

---

## 3. THE HARD PART — mapping external scores onto our 6 classes × A-F

Honest position: **no source rates a model per *our* work classes.** What LMArena *does* give is
per-category human-preference Elo, and 5 of our 6 classes have a direct or near-direct counterpart.
This is a **defensible mapping, not a precise one** — which is exactly what a *provisional, decaying,
weight-0.5* prior should be. Do not invent precision the data does not have.

### 3.1 Proposed mapping — LMArena category → `matrix.WorkClass`

| our WorkClass | LMArena category | confidence in the mapping |
|---|---|---|
| `coding` | **`agent` config `score`** (primary — it *is* agentic coding), fall back to `text`/`coding` Elo where a model is absent from `agent` | **direct + best-matched to our workload** |
| `reasoning` | `hard_prompts` (corroborate w/ `math`) | **strong** |
| `creative` | `creative_writing` | **direct** |
| `general` | `overall` | **direct** |
| `analysis` | `expert` | **moderate** — "expert" is a difficulty/domain cut, not analysis per se |
| `translation` | `non_english` (or mean of `french/german/spanish/japanese/korean/chinese/russian/polish`) | **weak — a PROXY.** Multilingual *chat* competence ≠ translation quality. **Label it as such in the data file.** |

The `agent*` configs (7 KB) are a *better* proxy for our real workload than `coding` alone and should
be folded in as a second signal for `coding` once the v1 lands. LiveBench's `Agentic Coding`
(javascript/typescript/python) is the same idea with a licence problem.

### 3.2 Elo → A-F banding (the only defensible method)

Do **not** hardcode Elo thresholds — the scale drifts every refresh and would silently rot.
Band by **percentile rank within the refreshed category**, so the bands are self-normalising:

```
p = percentile of model's `rating` among all models in that category at max(publish_date)
p >= 90 -> A    p >= 70 -> B    p >= 45 -> C    p >= 20 -> D    else F
```

**Status of this banding scheme: PROPOSED, NOT YET VALIDATED.** I pulled the full `coding` category
successfully once (1,013 rows in 11 paged requests, ~30 s) and read the ratings, but a second full
pull to validate the percentile bands end-to-end **hit repeated `HTTP 504 Gateway Time-out` from
`datasets-server.huggingface.co`**. Do not treat the band cut-points as tested — validating them is
literally step 1 of the spike.

**Operational finding from that failure (important, and it argues FOR the adopt):** the HF
datasets-server is **intermittently slow and 504s under repeated paging**. Any refresher must
therefore retry with backoff and fall back to last-good — which is *exactly* what
`catalog_refresh.py` already does (`try/except` per source → log red → keep last-good, never raise).
This is a concrete reason to reuse that module rather than write a fresh fetch loop. It is also a
reason to prefer the tiny `agent` config (38 rows, 1 request) over the 25k-row `text` split where
the two overlap.

Guards that keep this honest:
- Require `vote_count >= N` (e.g. 500) or emit **no** entry — low-vote Elo is noise. Never emit `F` from thin data; emit nothing and let the matrix return `"unknown"`.
- Carry `rating_lower`/`rating_upper`: if the CI straddles a band boundary, **round toward the worse band** (a prior that over-promotes costs money; one that under-promotes costs a little latency).
- Keep `DEFAULT_PRIOR_WEIGHT = 0.5` unchanged. Nothing here justifies raising it.
- Emit provenance + `leaderboard_publish_date` + `vote_count` per row so an operator can audit any grade.

### 3.3 What STAYS MANUAL (honest statement)

1. **`devstral` has no quality coverage in any source we can legally use.** models.dev knows it exists but publishes no quality signal. The *only* graded devstral data found anywhere is SWE-bench's `bash-only` board (`devstral-2512`, `devstral-small-2512`) — and that is **CC BY-NC 4.0, which we cannot vendor**. SWE-rebench also lists `Devstral-Small-2505` but is scrape-only. So devstral stays `operator-curated`/`unknown` until we grade it ourselves. (Correction to an earlier framing: it is a *licence* gap, not a total data gap.)
2. **Model-id reconciliation.** LMArena uses arena display names (`glm-5.2 (max)`, `kimi-k2.6-thinking`, `gpt-5.4-high`) — variant suffixes for thinking-mode/effort that our normalised ids do not carry. An **alias map is unavoidable and must be hand-maintained**; it should be a small checked-in JSON, reviewed when new models are added. This is the single biggest ongoing manual cost — budget for it honestly rather than pretending fuzzy matching solves it.
3. **The `translation` and `analysis` mappings** are judgement calls (§3.1) and should be re-reviewed, not treated as measurements.
4. **Whether a mapping is still sane** after LMArena changes its category set — needs a cheap assertion, not a human, but a human decides the fix.
5. Everything here is superseded the instant a real graded outcome lands. Unchanged and correct: *your own signal outranks any leaderboard.*

---

## 4. COVERAGE MATRIX — our routed models × sources (VERIFIED)

Licence key: ✅ = present & vendorable · 🚫 = present but licence-blocked · ❌ = absent

| model family | LMArena (CC-BY) | TB 2.1 (Apache) | LiveBench (no lic) | SWE-bench bash-only (NC) | SWE-rebench (scrape) | Epoch (CC-BY) | Aider (Apache) | models.dev (MIT) |
|---|---|---|---|---|---|---|---|---|
| deepseek-v4-pro / flash | ✅ | ❌ | 🚫 | ❌ (v3.2 only) | 🚫 | ❌ (V3 only) | ❌ | ✅ (no quality) |
| minimax-m2.5 / m2.7 | ✅ | ❌ | ❌ | 🚫 (m2/m2.5) | 🚫 | ❌ | ❌ | ✅ |
| minimax-m3 | ✅ | ❌ | 🚫 | ❌ | 🚫 | ❌ | ❌ | ✅ |
| glm-5.2 | ✅ | ❌ (5.1-max only) | 🚫 | ❌ (glm-5/4.6) | 🚫 | ✅ (to 5.1) | ❌ | ✅ |
| kimi-k2.6 | ✅ | ❌ | 🚫 | 🚫 (k2.5) | 🚫 | ✅ | ❌ | ✅ |
| gemini-3.x | ✅ | ✅ | 🚫 | 🚫 | ❌ | ~ | ❌ | ✅ |
| gpt-5.x | ✅ | ✅ | 🚫 | 🚫 | 🚫 | ✅ | ~ (gpt-5 only) | ✅ |
| qwen (3.x) | ✅ | ❌ | 🚫 | 🚫 | 🚫 | ✅ | ~ (Qwen3 235B) | ✅ |
| qwen3-coder | ~ | ❌ | ❌ | 🚫 (480B/30B) | 🚫 | ❌ | ❌ | ✅ |
| **devstral** | ❌ | ❌ | ❌ | 🚫 **(only source)** | 🚫 | ❌ | ❌ | ✅ |
| mistral | ✅ | ❌ | ❌ | ❌ | ❌ | ✅ | ❌ | ✅ |
| **vendorable ✅ (of 12)** | **11** | **~3** | **0** | **0** | **0** | **6** | **~1** | **12 (no quality)** |

The column that matters is "vendorable" — 🚫 entries cannot go into a public repo regardless of how
good the data is. **LMArena is the only source with both broad coverage and a usable licence.**

**Per constraint #3 (coverage before precision), LMArena wins outright** — and it happens to also be
the only high-coverage source with a clean, vendorable licence.

---

## 5. HOW IT REUSES `catalog_refresh.py` — NO NEW REFRESHER

Constraint #2 says: do not design a second refresher. The good news is `catalog_refresh.py` already
implements every property we need. **Correction to the brief:** `catalog_refresh.py` does **not** gate
on `{"enabled": true}` — VERIFIED, there is no `enabled` key in that file. Its actual gate is
`maybe_start()`, which starts the TTL loop only when `_load_providers()` returned a non-empty dict
(i.e. presence-of-config *is* the opt-in), plus registration in `gateway._MODULE_SPECS`.
**Mirror the real mechanism, not the one in the brief.**

Reusable pattern, verbatim from that module:
- `refresh_now()` — poll, `try/except` per source, on failure **log red + keep last-good** (stale-but-usable). Never raises.
- `CatalogCache.put()` + `updated[source] = time.time()` — per-source last-good with timestamps.
- `start()` / `_loop()` / `stop()` — daemon TTL thread, `_DEFAULT_TTL_S = 3600`; a bad cycle never kills the loop.
- `bind()` snapshots the static baseline; `bridge()` layers discovered data on top with **`setdefault` so static/hand config always WINS**. That is exactly the semantic we need: *a real graded outcome (and a hand-pinned grade) must beat a refreshed prior.*
- `poll_count` exists purely so a test asserts the hot path never triggers a poll. **Copy that test.**

**Concretely, the seed prior should be a second cache+bridge inside the SAME module/refresher**, not a
new class hierarchy: add a `PriorCache` alongside `CatalogCache`, a `refresh_prior()` that fetches the
LMArena JSON via `netutil.keyed_request()`/`open_keyed()`, and a `bridge_prior()` that loads entries
into the `CapabilityMatrix` through the existing `GradesImport` path — `GradesImport` already owns the
`reconcile_with_real()` rule that makes a real outcome REPLACE (not blend with) the prior. Nothing new
is invented; the prior simply becomes a second thing the one refresher refreshes.

**Offline / fresh-install requirement (constraint #1):** ship `src/charon/capability/data/seed_prior.json`
— a checked-in, generated, CC-BY-attributed snapshot. `grades_import` loads that file at import time
with a **fallback to the current in-code table if the file is missing** (belt-and-braces for a broken
install). Zero network on a fresh install. The refresher is strictly additive and opt-in.

---

## 6. #1 RECOMMENDATION + THE <1-DAY SPIKE

**#1: LMArena `lmarena-ai/leaderboard-dataset` — the `agent` config as the primary signal for
`coding`, the `text` config's categories for the other five classes (both CC-BY-4.0) — joined on
models.dev (MIT) ids, with LiteLLM's JSON continuing to supply cost/capability separately.**

Why it wins on the stated ranking order: **coverage** (11/12, the only source with minimax-m2.5/m2.7
*and* deepseek-v4 *and* mistral) → **licence clarity** (the only high-coverage source that explicitly
grants redistribution) → **machine-readability** (stdlib-parseable JSON REST, no key, no scraping,
no new dependency).

### The spike (half a day, proves or kills it)

1. **Fetch + band (2h).** Script (in scratch, not the repo) that pulls the 6 mapped categories from
   the `/filter` endpoint at `max(leaderboard_publish_date)`, dedups by max `vote_count`, applies the
   §3.2 percentile banding, and emits candidate `(model_id, work_class, grade)` rows.
2. **Alias map (2h).** Hand-write the ~15-line arena-name → charon-id alias map for our 12 families.
   **This is the go/no-go:** if the aliases are stable and unambiguous, adopt; if arena naming churns
   per snapshot, the maintenance cost may exceed the benefit — say so and stop.
3. **Diff against today's 43 entries (1h).** Compare generated grades to the hand-curated `_SEED_PRIOR`.
   Large disagreement is a *finding*, not a bug — it tells you which the operator's curation got wrong.
   Report the diff; do not silently adopt.
4. **Decide (1h).** If the diff is sane, generate `seed_prior.json` + a NOTICE attribution line and
   swap `_SEED_PRIOR` to load from it, keeping the in-code table as the missing-file fallback.
   The opt-in refresher wiring is a **separate, later** ticket — the data-file swap alone already
   removes "edit Python to refresh" and is independently valuable.

**Do NOT do in the spike:** wire the refresher, add LiveBench, add an Artificial Analysis key, or
touch `matrix.py`. Those are separate tickets.

**Immediately after (not in the spike): fold in Terminal-Bench 2.1.** It is Apache-2.0, current
(2026-07-11), model-keyed with the scaffold in a separate field, and 20 small JSON files — a cheap
second provenance for the ~3 families it covers, and the only source carrying `total_cost_usd`,
`avg_trial_duration_sec` and `reward_hacks`. Where TB2.1 and LMArena disagree, TB2.1 wins for
`coding` (it measures real agentic task completion; LMArena measures human preference).

### Licence verdict, one line each
- **LMArena — CC-BY-4.0 — ✅ VENDOR OK** with attribution in the data file header + NOTICE.
- **Terminal-Bench 2.1 — Apache-2.0 — ✅ VENDOR OK** with attribution.
- **models.dev — MIT — ✅ VENDOR OK.**
- **SWE-bench (`swe-bench.github.io`) — CC BY-**NC**-4.0 — ❌ DO NOT VENDOR.** NonCommercial poisons downstream use. `SWE-bench/experiments` has NO licence — worse.
- **SWE-bench-Live — no licence — ❌ DO NOT VENDOR.**
- **SWE-rebench — no API, site ToS — ❌ scrape-only, do not adopt.**
- **EvalPlus — Apache-2.0 — ✅ technically vendorable, but content is a 2024 museum piece (zero of our models).**
- **BigCodeBench — archived 2026-01-03 · LiveCodeBench — no results file exists — do not use.**
- **Epoch.ai — CC-BY — ✅ VENDOR OK** with credit (but low value for us).
- **Aider — Apache-2.0 — ✅ VENDOR OK** but the data is 10 months stale and covers none of our models.
- **LiveBench — ❌ NO LICENCE — DO NOT VENDOR.** Runtime-fetch + attribution only.
- **Artificial Analysis — ⚠️ attribution required, no redistribution grant — DO NOT VENDOR.**
- **HF Open LLM Leaderboard — apache-2.0 but DEAD — do not use.**
- **LiteLLM JSON — MIT, already a dep — ✅ but contains NO quality signal.**

### Side-fixes this research surfaced (small, worth folding in)
- `Provenance = "models-dev"` on 13 seed entries is **unsupportable** — models.dev publishes no quality data. Re-label to `operator-curated`.
- `Provenance = "aider-polyglot"` on 6 entries is **stale** — aider has not graded any model we currently route.
- The brief's "33 entries / 12 work classes" is wrong: it is **43 entries / 6 work classes**. Any ticket written off the brief's numbers needs correcting first.
- The brief states `catalog_refresh.py` "gates on `{"enabled": true}`". **It does not** — there is no `enabled` key in that file. The real gate is `maybe_start()` + presence of `providers.json`. Mirror the real one.
- **`Provenance` vocabulary should change** to reflect what is actually adoptable:
  drop `models-dev` (publishes no quality data) and `aider-polyglot` (grades nothing we route);
  add `lmarena-agent` and `terminal-bench`. Keep `lmarena`, `artificial-analysis`, `operator-curated`.
- The prior currently grades `claude-opus-4.5` and `llama-4-405b` — one is never routed via SG, the other is not in the fleet. Drop both when regenerating.
