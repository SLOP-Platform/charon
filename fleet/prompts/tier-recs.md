# TIER-RECS — Phase B: LLM-judge tier ranking from live /v1/models

## Dependencies & sequence
**depends_on: SETUP-UX-A (Phase A — done, merged)** — Wave 1 (CLI cluster, alongside UX-POLISH).
Phase A already ships the setup-wizard model catalog surfacing + 0-served guard in PR #78.

## What to build

A `recommend.py` module that uses Charon's OWN gateway (already-configured models) to rank a
provider's live `/v1/models` catalog into Charon's tier vocabulary (low/med/high). Exposed as a
`charon tier recommend <provider>` CLI subcommand AND as an optional step in `charon setup`.

### Module: `src/charon/recommend.py` (NEW)

1. **`TierRecommendation` dataclass** — tier name + list of model ids.

2. **`recommend_tiers(provider_name, catalog, *, config_dir=None)` — the core**:
   - Takes a provider name + a live `/v1/models` catalog (list of model dicts from `providers.list_models`).
   - Finds 1–3 already-configured "trusted" models (from `models.json` that have keys configured).
   - Sends a structured prompt to EACH trusted model: "Given this live model catalog for provider X, rank each model into low/med/high tiers. Reply as JSON `{low:[...], med:[...], high:[...]}`."
   - Takes **CONSENSUS** across responses (majority vote per model → tier).
   - **Anti-hallucination**: intersects every recommendation with the real catalog — drops any hallucinated model id.
   - Returns `list[TierRecommendation]` or falls back gracefully on any failure.

3. **Graceful fallback**: if no trusted model is reachable → infer tiers heuristically from catalog metadata (context_window, price cues, name patterns like `70b`/`405b`/`mini`/`flash`).

4. **Timeout**: fast (30s total, spinner). True async v2.

### CLI: `src/charon/cli.py` — `charon tier recommend <provider>`

- New subcommand `recommend` under `charon tier`.
- Fetches live catalog via `providers.list_models()`, calls `recommend_tiers()`, prints recommendations with `[y/n]` per-tier accept prompt.
- On accept: writes tier members into `tiers.json` via `config.set_tiers()`.

### Setup integration: `src/charon/cli.py` — `_cmd_setup()`

- After the provider+key+import flow, offer: "Run tier recommendations now? (ask trusted models to rank this provider's catalog)".
- If accepted, calls `recommend_tiers()` and lets user accept/reject per tier.
- Falls back to manual tier assignment on failure.

### Config: `src/charon/config.py`

- No schema changes needed — tiers already live in `tiers.json`. The recommender just populates them.

## CONSTRAINTS
- **Owns**: `src/charon/recommend.py` (NEW), `src/charon/cli.py`, `src/charon/config.py`
- **Stdlib-only** (urllib for HTTP). No new dependencies.
- **Provider/agent-agnostic** — no hardcoded model names in engine path.
- **Product-clean** — no SLOP/fleet/rig leak into `src/`.
- Uses the existing gateway proxy to reach trusted models (reuses `charon connect` or direct call).
- Recommendations are always user-overridable.

## accept
```
PYTHONPATH=src python3 -m pytest tests/test_recommend.py -q -x && ruff check src/charon/recommend.py src/charon/cli.py src/charon/config.py && mypy src/charon/recommend.py src/charon/cli.py src/charon/config.py
```
