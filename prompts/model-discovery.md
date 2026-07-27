# MODEL-DISCOVERY — enrich /v1/models response + exclude pool IDs from discovery

## Dependencies & sequence
**depends_on: DS-PLAN-REVIEW.** This ticket was created by DS-PLAN-REVIEW's operator decision
(2026-06-28) after omp integration dogfood surfaced two gaps: sparse model metadata and pool IDs
leaking into model discovery. Owns `config.py`, `providers.py`, `gateway.py`, `proxy_server.py`,
`api.py`, plus test.

**COLLISION NOTE:** `proxy_server.py` is also owned by OBS-UI (Wave 1), and `api.py` is owned by
ORCH-ROUTE (Wave 1). Sequence this ticket either BEFORE or AFTER Wave 1 — not concurrently.

## Why
`charon gateway` serves `/v1/models` with bare entries (`id`, `object`, `owned_by` — three fields).
When omp (or any OpenAI-compatible client) discovers models, it gets no context window, no max
tokens, no reasoning/vision/audio flags — it falls back to conservative defaults that undersell the
model. Additionally, pool virtual IDs (like `auto`, tier names `low`/`med`/`high`) show up in the
model list as if they were real LLMs — clients try to use them and get confused.

## What to build

### 1. Add optional model metadata fields to the registry
Add these fields to `config.add_model()` and `add_models_bulk()`:
- `context_window: int | None` — the model's context window in tokens
- `max_tokens: int | None` — maximum output tokens
- `reasoning: bool | None` — supports reasoning/thinking mode
- `vision: bool | None` — supports image input
- `audio: bool | None` — supports audio input

All optional; persist to `models.json` only when non-None. In `providers._parse_models()`, extract
these fields from upstream `/models` responses if the provider sends them.

### 2. Surface metadata in /v1/models
Carry model metadata through `GatewayConfig` → `GatewayProxyServer` via a new `model_meta:
dict[str, dict]` field. In the `/v1/models` handler, emit each field in the model entry when
present (e.g., `"context_window": 200000`). The response stays backward-compatible — existing fields
`id`/`object`/`owned_by` are unchanged; new fields appear only when data is available.

### 3. Exclude pool IDs from /v1/models
Pool virtual IDs (e.g., `auto`, tier names) are internal routing concepts, not real models. In the
`/v1/models` handler, filter `srv.model_ids` against `srv.pools.keys()` so only concrete model IDs
appear. Pool routing inside the gateway is unchanged — pools still work for failover.

## Files to change (exact)

| File | Change |
|---|---|
| `src/charon/config.py` | Add `context_window`, `max_tokens`, `reasoning`, `vision`, `audio` params to `add_model()`; persist when non-None |
| `src/charon/providers.py` | Extract metadata fields in `_parse_models()` from upstream `/models` responses |
| `src/charon/gateway.py` | Add `model_meta: dict` to `GatewayConfig`; compile metadata in `_build_routes_and_pools()`; pass through `build_server()`; update `apply_routes()` hot-reload |
| `src/charon/proxy_server.py` | Add `model_meta` field to `GatewayProxyServer`; enrich `/v1/models` response with metadata; filter pool IDs from model list |
| `src/charon/api.py` | Update `_MODEL_FIELDS` allowlist; pass empty `model_meta` to work-path GatewayProxyServer |
| `tests/test_gateway.py` | Add tests for metadata in /v1/models response + pool ID exclusion |

## Acceptance
- `/v1/models` includes `context_window`, `max_tokens`, `reasoning`/`vision`/`audio` when configured
- Pool IDs (`auto`, tier names) do NOT appear in `/v1/models`
- Existing test_gateway.py tests GREEN; no regression
- No secrets in the response (never leak `key_env`/`upstream_base`/`api_key`)
- Backward-compatible: clients parsing only `id` are unaffected

## CONSTRAINTS
Own ONLY the files listed above. Stdlib core only; gate GREEN
(`PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests ; python3 tools/check_boundary.py src ; python3 tools/check_version.py`).
Conventional commits; review note → `docs/review-log/MODEL-DISCOVERY.md`. Draft PR, `submit.sh`, STOP.

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
BUDGET:       ok | TRUNCATED — <what you could not finish and why>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
