# BRIDGE-RELAYFEATURES — Incorporate RelayFreeLLM's superior features + transformative gaps

## Why

Analysis of RelayFreeLLM (https://github.com/msmarkgu/RelayFreeLLM) vs Charon revealed six
features RelayFreeLLM does better, and five transformative capabilities neither project has.
This ticket builds the RelayFreeLLM-strong features into Charon and prototypes the highest-value
transformative gaps.

Reference: session research 2026-07-02 (RelayFreeLLM comparison + blast-radius analysis).

## Part A: RelayFreeLLM features to incorporate

### A1. Preemptive rate limiting

**Current state:** Charon reacts to 429s — sends request, gets rejected, sets cooldown, fails over.
Each rate limit is a wasted upstream call.

**What to build:** Per-model sliding-window tracker in `GatewayProxyServer`. Before forwarding a
request to upstream, check `can_handle(model, provider)` against recent request/token counts.
If the provider would reject, skip it in the chain immediately — no wasted call.

**Files:** `src/charon/proxy_server.py`
**Design:** 7-dimension deques (requests per sec/min/hr/day, tokens per min/hr/day) keyed by
`upstream_base`. Default limits from provider metadata; overridable via `providers.json` `limits: {...}` field.

### A2. Image-aware routing

**Current state:** Charon stores `vision: true/false` in model metadata via `/v1/models` but doesn't
inspect request content to route accordingly.

**What to build:** In the failover loop (`_handle()`), scan the request body for `image_url` content
parts. If images are present, restrict the chain to vision-capable models only (`model_meta.vision=True`).
Fall back within/across providers as normal, but never try a non-vision model for an image request.

**Files:** `src/charon/proxy_server.py`, `src/charon/proxy.py`

### A3. Response normalization

**Current state:** Raw upstream responses passed through verbatim. Provider-to-provider variations
("As an AI assistant…", different JSON formatting, markdown inconsistencies) leak to the client.

**What to build:** Optional `normalize: true` flag per provider or globally. When enabled:
- Strip "As an AI…", "Certainly!", "I'd be happy to…" preambles from text responses
- Standardize JSON code blocks (detect and pretty-print)
- Normalize markdown heading styles
- Apply universal style directives to system prompts (tone, format)

**Files:** `src/charon/proxy_server.py`, new `src/charon/normalize.py` (small, stdlib-only)

### A4. Session affinity via header

**Current state:** Each request independently selected from the pool — no memory of which provider
served a previous request in the same conversation.

**What to build:** `X-Session-ID` request header support. When present:
- Pin the session to the first successful provider for subsequent requests
- On provider failure, migrate the session to the next available provider
- Track session→provider mapping in an in-memory LRU cache (bounded to ~1000 sessions)

**Files:** `src/charon/proxy_server.py`

### A5. Visual admin dashboard (simplified)

**Current state:** Read-only console at `/charon` + write-capable setup page at `/charon/setup`.
No live-editable model/limits table.

**What to build:** A self-contained HTML/JS page at `/charon/admin` that shows:
- Collapsible provider cards with inline-editable cooldown/limits
- Model list with enabled/disabled toggles
- Pool/tier membership view with drag-to-reorder
- Live usage stats and failover event feed
- All changes hot-reload into the running gateway (no restart)

**Files:** `src/charon/proxy_server.py` (new route + embedded HTML)

### A6. Provider model auto-discovery

**Current state:** `charon models import <provider>` fetches one provider at a time. No bulk discovery.

**What to build:** `charon models discover` command (or button on admin dashboard). Parallel-fetches
`/v1/models` from all configured providers with keys set. Reports discovered models, new/removed since
last import, and offers to bulk-import with one command.

**Files:** `src/charon/cli.py`, `src/charon/providers.py`

## Part B: Transformative gaps (neither project does these)

### B1. Token budgeting / spend caps

**Current state:** No way to say "never spend more than $5 this month." Cost tracking exists
(`Usage.cost_usd`) but no enforcement.

**What to build:** Per-session or per-gateway spend limits in `config.json` or gateway args:
```
charon gateway --max-spend 5.00
```
When cumulative cost reaches the cap, all requests return 402 with `{"error": "spend cap exceeded"}`.
Reset on gateway restart or configurable monthly/rolling window.

**Files:** `src/charon/proxy_server.py`, `src/charon/gateway.py`, `src/charon/config.py`

### B2. Semantic response caching (prototype)

**Current state:** Every prompt hits an upstream provider, even if an identical or near-identical
prompt was just served.

**What to build:** In-memory LRU cache keyed by normalized prompt hash (strip whitespace,
lowercase, remove stopwords). Cache TTL configurable (default 300s). On cache hit, serve
cached response with `X-Charon-Cache: HIT` header. Bounded to ~500 entries / 50MB.

**Why prototype only:** Full semantic caching (TF-IDF or embedding-based similarity) requires
dependencies Charon avoids. Start with exact-match cache; evaluate semantic expansion later.

**Files:** `src/charon/proxy_server.py`, new `src/charon/cache.py`

### B3. Speculative parallel execution

**Current state:** Sequential failover — try provider A, wait, try B, wait, try C.

**What to build:** `--speculative` gateway flag. When enabled, fire the request to the first N
providers in the chain simultaneously. Return the first successful response, cancel the rest.
Falls back to sequential failover if `< 2 providers in chain` or if speculative is disabled.

Transforms latency from "sum of timeouts" to "minimum of responses."

**Files:** `src/charon/proxy_server.py`, `src/charon/gateway.py`

## Implementation order

| Wave | Items | Rationale |
|---|---|---|
| 1 | A1 (rate limiting) + A3 (normalization) + A4 (session affinity) | Highest impact, lowest complexity |
| 2 | A2 (image routing) + A6 (auto-discovery) | Medium complexity, high value |
| 3 | A5 (admin dashboard) | High complexity, high value |
| 4 | B1 (spend caps) + B2 (response cache) | Transformative but complex |
| 5 | B3 (speculative execution) | Highest complexity, needs threading model review |

## Hard constraints

- Stdlib-only in the gateway path (no new dependencies)
- All new features are opt-in (flags, headers, config) — backward compatible
- Gate GREEN: `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests`
- Each wave ships with its own test file
- Conventional commits; one feature per commit

## Acceptance

Per wave:
- New feature works as described
- Existing tests pass (no regression)
- New tests prove the feature AND prove the gate CAN fail (red-proof pattern)
- Gate green

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
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
