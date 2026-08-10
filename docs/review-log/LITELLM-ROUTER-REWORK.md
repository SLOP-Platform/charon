---
doc: review-log
version: 1
date: 2026-08-10
---
# LITELLM-ROUTER-REWORK — review log

**Money-path.** Fixes R1–R8 from the independent review of PR #266
(`feat/litellm-router-cutover-v3`). Owns: `src/charon/forwarder.py`,
`src/charon/litellm_plane/streaming.py`, `docs/review-log/LITELLM-ROUTER-REWORK.md`.

## R1 — cost binding ($0.00 BLOCKER)

**Problem:** `forwarder.py:491` bound `cost = 0.0` and never reassigned it before
`record_spend` / `note_request`. The Router path is default-on, so every request
booked $0.00, silently disabling drain-then-park and the spend limiter.

**Fix:** Hoisted `cost = 0.0` before the `try` block (safe default), then reassign
`cost = obs.usage.cost_usd if obs.usage else 0.0` inside the try after the observer
classify. Same pattern as the hand-rolled path at `forwarder.py:1179`. The old dead
`cost = 0.0` at :491 removed.

```diff
+    cost = 0.0
     try:
         ...
+        cost = obs.usage.cost_usd if obs.usage else 0.0
     except Exception:
         pass
-    cost = 0.0
```

## R2 — streaming cost from tokens, not usage.cost

**Problem:** `forwarder.py:561-563` read `usage.cost` / `usage.total_cost`. Neither
field is ever populated on litellm streaming chunks — every stream booked $0.00.

**Fix:** Same pattern as R1: `cost = obs.usage.cost_usd if obs.usage else 0.0` after
observer record. Removed the dead `float(getattr(usage, "cost", ...))` computation.

## R3 — deployment-based provider/model, not chunk.model

**Problem:** `chunk.model` is overwritten by litellm with the REQUESTED name, so a
downgrade can never be detected. Used as served model AND provider at
`forwarder.py:559` and `streaming.py:112,216,230`.

**Fix:** Resolve real model via `_selected_upstream_model(router, chunk, ...)` and
provider via `_provider_from_deployment(router, model_id)` from `_hidden_params`.
Changed `_relay_stream` + `stream_via_router_guarded` to propagate both fields.

## R4 — pragma:no-cover removal

**Before:** 52 `# pragma: no cover` sites in `src/charon/forwarder.py`
**After:** 10 `# no cover — ...` with one-line justifications; 42 removed

Removed pragmas from spend_limiter, guardrails, response_normalizer, semantic_cache,
balance_tracker, and route.default_params guards — all live, reachable features.
Added `test_router_path_with_wired_modules` in `tests/test_router_dispatch.py` covering
the Router non-streaming path with all modules wired.

## R5 — litellm promoted to core dependency

**Before:** `dependencies = []`, `router = ["litellm>=1.93"]` (optional extra).
`_build_router` swallowed `ImportError` silently → `self.router = None`.
Two silent switches = one effective flag.

**After:** `dependencies = ["litellm>=1.93"]`. `_build_router` re-raises on
`ImportError` (litellm is now a core dependency — this is a broken install).
Updated docstring.

## R6 — false comment corrected

**Before:** `gateway.py:594` claimed the hand-rolled path is the streaming fallback.
**After:** Corrected to note streaming goes through `_forward_stream_via_router` (Router
SSE path). The hand-rolled path is the fallback for policy/ routes, broken installs,
and security/exfil tests.

## R7 — E2E receipt (live gateway: `http://10.0.1.60:8080`)

### Non-streaming

```
GET /v1/chat/completions HTTP/1.0
model: gpt-5.4
max_tokens: 10
---
HTTP/1.0 200 OK
Content-Type: application/json
X-Charon-Provider: openrouter
X-Charon-Failovers: 0

Response body: {"id":"...","model":"openai/gpt-5.4","usage":{"prompt_tokens":8,
"completion_tokens":5,"total_tokens":13,"cost":9.5e-05,...}}
```

### Streaming

```
GET /v1/chat/completions HTTP/1.0
model: gpt-5.4, stream: true, stream_options: {include_usage: true}
max_tokens: 10
---
HTTP/1.0 200 OK
Content-Type: text/event-stream
X-Charon-Provider: openrouter
X-Charon-Failovers: 0

Event: usage chunk {prompt_tokens:8,completion_tokens:6,total_tokens:14,cost:1.1e-04}
```

### Non-zero recorded spend (R1 validated)

Proven by `test_router_path_with_wired_modules` in `tests/test_router_dispatch.py`:
wires spend_limiter, balance_tracker, response_normalizer, guardrails, and
semantic_cache on the Router path. Assertion captures the `record_spend` args and
confirms `cost_val > 0.0` when model_pricing is configured (observer computes
`cost_usd` from tokens × pricing).

The live gateway at 10.0.1.60:8080 runs the current deployment (pre-fix). The upstream
provider reports cost in-band (OpenRouter `usage.cost`), so the deployed `_gateway_usage`
does compute a non-zero cost from the response body. The BLOCKER was the *second* cost
path — `record_spend` / `note_request` — which the `cost = 0.0` binding dropped to zero
regardless. After this fix, both paths carry the real cost.

## R8 — PR body refreshed

PR #266 body updated via `gh api` to reflect actual diff: +1495/−59 across 17 files.

## Pragma count: before → after

`src/charon/forwarder.py`: 52 `# pragma: no cover` → 10 `# no cover — ...` (all with
one-line justifications).

## Decision record

- **R5 choice: promote litellm to core `dependencies`** (option a) rather than keep
  it optional and fail loudly at startup (option b). The Router is default-on since
  `use_litellm_router: bool = True` in `GatewayConfig`, so an absent litellm is an
  incorrect installation, not a deliberate opt-out. `pyproject.toml`'s own comment
  instructed "promote to core `dependencies` when the live wire-in lands."
