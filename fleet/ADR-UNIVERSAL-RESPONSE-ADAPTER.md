# ADR: Universal, provider-agnostic response-shape adapter layer

- **Status:** PROPOSED (design-only; supersedes the parked `CLINE-UNWRAP-SHIM` ticket, which becomes the first concrete adapter under this umbrella)
- **Date:** 2026-07-09
- **Owner:** design sub-session for the Charon fleet manager
- **Depends on:** PROXY-SERVER-DECOMPOSE (MERGED — `forwarder.py` exists; the response-relay path is already extracted verbatim)
- **Product standalone:** YES — no fleet/SLOP/runner leak.

---

## 1. Problem

Charon forwards upstream chat-completion responses to OpenAI-compatible clients **verbatim** (`forwarder.py::forward_with_failover` writes `body_bytes` unchanged). This assumes every upstream speaks the canonical OpenAI Chat Completions shape. That assumption is now broken:

- `cline-pass` is the cheap-first (cost_rank=1) leg on 5 live pools (`glm-5.2, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash, minimax-m3`). Verified live 2026-07-09 (`fleet/scratch/cline-wire-report.md`).
- Its **non-streaming** `/chat/completions` responses come back wrapped:
  `{"data": { ...the real OpenAI object (choices, model, usage)... }, "success": true}` — **no top-level `choices`, `model`, or `usage`.**
- Its **streaming** (SSE) responses are already clean OpenAI shape (verified — all 5 pools 200 via the Cline leg, 0 failovers, streaming).

Two failure modes, both money-path:
1. **Client breakage** — a non-streaming OpenAI client gets an unparseable body (no `choices`).
2. **Silent metering/routing corruption** — `proxy_response._extract` reads top-level `model`/`usage`; on the wrapped body it finds neither, so `observer.classify` sees no `model` (downgrade detection blind) and no `usage` → `obs.usage` is empty → `cost_usd = 0` recorded → `spend_limiter` and the METER cost sensor **undercount to zero** for every Cline non-stream completion. This is the quiet, dangerous half.

Today the bug is **latent** (verdict A, `cline-streaming-check.md`): every path that hits these 5 pools streams (opencode coding + benchmark-via-opencode). It fires the moment any non-streaming OpenAI client points at those pools (or opencode issues its auxiliary non-stream `generateText` title/summary).

The naive fix is a `if provider == "cline-pass": unwrap` branch in the forwarder. **This violates the provider-agnostic doctrine** (memory: charon-modular-agent-and-provider-agnostic). The durable fix is an adapter abstraction the forwarder calls blindly, with the vendor knowledge declared in provider config.

---

## 2. Design overview

Introduce a **response-shape adapter** layer: a per-provider, config-declared object that maps a non-OpenAI-shaped upstream response into the canonical OpenAI Chat Completions shape. The forwarder holds a `ResponseAdapter` reference and calls it unconditionally; the **identity default** (passthrough) is used by every already-compatible provider, so nothing changes for them. This exactly mirrors the existing `wire` field precedent (`WIRE_OPENAI`/`WIRE_ANTHROPIC`): a per-provider marker declared on `ProviderPreset` → flowed through `_route_from_spec` → carried on `UpstreamRoute` → consulted in the forwarder — vendor vocabulary lives in `providers.py` (the layer the product-clean gate exempts), the core references it by abstraction only.

**Layer boundary (important, avoids collision):** this is **shape/envelope** normalization (does the body have top-level `choices`/`usage`?), distinct from the existing `response_normalizer.py`, which is **content** normalization (markdown/JSON cleanup *inside* `choices[0].message.content`). The shape adapter runs FIRST (produce a canonical envelope), then the existing content normalizer runs on the canonical body as it does today. Naming: new module `src/charon/response_adapters.py` (NOT the `src/charon/adapters/` package — that is execution-port/ACP adapters, an unrelated concept; reusing it would confuse).

---

## 3. The interface

New module `src/charon/response_adapters.py`, stdlib-only, deterministic, no network:

```python
from __future__ import annotations
from typing import Protocol

class ResponseAdapter(Protocol):
    """Maps ONE provider's non-OpenAI response shape into canonical OpenAI
    Chat Completions shape. Pure/deterministic; stdlib only. All methods are
    total — on an unrecognized/already-canonical input they MUST return the
    input unchanged (idempotent), never raise."""

    def normalize_response(self, raw: dict) -> dict:
        """Non-streaming JSON body (already json.loads'd) -> canonical OpenAI
        completion:
          {id, object:"chat.completion", created, model,
           choices:[{index, message:{role,content,...}, finish_reason}],
           usage:{prompt_tokens, completion_tokens, total_tokens}}
        Guarantee: the returned dict has a top-level `choices` list and a
        top-level `usage` dict (see §6). Idempotent on already-canonical input."""

    def normalize_stream_chunk(self, chunk: dict) -> dict:
        """ONE parsed SSE data-event object -> canonical OpenAI streaming
        chunk {id, object:"chat.completion.chunk", created, model,
               choices:[{index, delta:{...}, finish_reason}]} plus an optional
        final-chunk `usage`. Operates on a SINGLE already-parsed event; the
        SSE framing (data: prefix, [DONE], chunk boundaries) is handled by the
        caller's line-buffer, NOT here (see §7). Idempotent on canonical input."""

    def normalize_error(self, raw: dict) -> dict:
        """Non-200 body -> canonical OpenAI error envelope
        {error:{message, type, code}}. Idempotent on canonical input."""
```

### Identity default (passthrough)

```python
class IdentityAdapter:
    def normalize_response(self, raw): return raw
    def normalize_stream_chunk(self, chunk): return chunk
    def normalize_error(self, raw): return raw

IDENTITY = IdentityAdapter()   # module singleton; the default for every provider
```

Every provider whose config declares no adapter resolves to `IDENTITY`. No speculative adapters — universality lives in the pattern, not in a catalog of shims.

### First concrete adapter — Cline

```python
class ClineAdapter:
    """cline-pass wraps its NON-streaming body as {"data": <openai obj>,
    "success": bool}. Streaming is already canonical -> stream/error are
    passthrough today. Unwrap is guarded + idempotent."""

    def normalize_response(self, raw):
        if (isinstance(raw, dict) and "choices" not in raw
                and isinstance(raw.get("data"), dict) and "success" in raw):
            inner = raw["data"]
            if "choices" in inner:      # only unwrap a real OpenAI object
                return inner
        return raw                       # already-canonical / unrecognized -> passthrough

    def normalize_stream_chunk(self, chunk):
        return chunk                     # Cline SSE already canonical (verified)

    def normalize_error(self, raw):
        # Cline may wrap errors as {"data":{"error":...},"success":false};
        # unwrap to a top-level {"error":...} if present, else passthrough.
        if isinstance(raw, dict) and "error" not in raw:
            inner = raw.get("data")
            if isinstance(inner, dict) and "error" in inner:
                return {"error": inner["error"]}
        return raw
```

---

## 4. Registration / config mechanism (declare, don't detect)

Mirror the `wire` field end-to-end. Adapter keyed off the **provider config entry**, explicit and testable — never sniffed from response shape at runtime.

1. **Registry** (in `response_adapters.py`): a name→instance map, closed set of shipped adapters.
   ```python
   _ADAPTERS: dict[str, ResponseAdapter] = {"cline": ClineAdapter()}
   def get_adapter(name: str | None) -> ResponseAdapter:
       return _ADAPTERS.get(name or "", IDENTITY)   # unknown/absent -> IDENTITY
   ```
2. **ProviderPreset** (`providers.py`): add `adapter: str | None = None`. Set `adapter="cline"` on a new `cline-pass` preset (also fixes the STEP 3 note — a `/models`-less base that false-fails the setup-API key probe; add `note` documenting no-`/models`). An operator can override `adapter` in `[providers.<name>]` like any other quirk.
3. **`_route_from_spec`** (`gateway.py:92`): resolve `adapter = str(spec.get("adapter") or preset.adapter or "") or None` (per-model override wins, exactly like `wire` at line 103), and pass to the `UpstreamRoute(...)` constructor.
4. **UpstreamRoute** (`proxy_server.py:175`): add field `adapter: str | None = None` (sits beside `wire`).
5. Forwarder resolves the instance once per attempt: `adapter = get_adapter(route.adapter)`.

Config example (what the live cline-pass wiring becomes, declaratively):
```json
// providers.json
"cline-pass": { "base_url": "https://api.cline.bot/api/v1",
                "key_env": "CLINE_PASS_API_KEY", "strip_v1": true,
                "adapter": "cline" }
```

---

## 5. Exact plug-in point

File: `src/charon/forwarder.py`, function `forward_with_failover`. Resolve `adapter = get_adapter(route.adapter)` once at the top of the per-route loop body (after line 195, `req = _build_upstream_req(...)`). Three insertion points:

### (a) Non-streaming 200 — the primary fix (lines 269–319)
Currently: line 271 `body_bytes = handler._drain(resp)`; line 272 `observed = _extract(body_bytes, ctype)`; line 273 classify. **The adapter must run between the drain and `_extract`** so downgrade detection AND usage/cost see the canonical shape:
```python
if not is_stream:
    body_bytes = handler._drain(resp)
    if route.adapter:                       # IDENTITY path stays byte-identical
        parsed = _extract(body_bytes, ctype)          # {} on non-JSON
        canon = adapter.normalize_response(parsed)
        if canon is not parsed:             # only re-encode if it actually changed
            body_bytes = json.dumps(canon).encode()
    observed = _extract(body_bytes, ctype)  # now sees top-level model+usage
    obs = srv.observer.classify(okey, 200, rhdrs, observed, expected_model=expected)
    ...
```
Everything downstream (classify → downgrade → `obs.usage.cost_usd` → cache set → quality_scorer → spend_limiter → content `response_normalizer` at line 296 → `_write`) then operates on the canonical body unchanged. **Guard:** wrap in `if route.adapter:` so identity providers never pay a re-encode and the byte stream is provably unchanged on the default path.

### (b) Non-200 error (lines 219–267)
After `obs_body = _extract(body_bytes, ctype)` (line 221), if `route.adapter` and this is the terminal relay (not failed-over), apply `normalize_error` before `handler._write(body_bytes)` at line 265. Lower priority (errors are diagnostic), but keeps the envelope canonical.

### (c) Streaming (lines 321–402) — see §7
For Cline this is identity (no-op). The universal contract is specified but the concrete streaming transform ships only when a provider needs it (none does today).

---

## 6. Usage normalization + METER synergy

`normalize_response` **guarantees** a top-level `usage` dict. This is the load-bearing half for cost:

- `_extract` → `observer.classify` reads `usage` to build `obs.usage`; `obs.usage.cost_usd` drives `spend_limiter.record(cost)` (forwarder line 315) and `srv.note_request(..., cost, ...)` (line 318). Without the unwrap, Cline non-stream cost silently records **0** — the METER cost sensor (real-outcomes ledger `cost_usd`/`tokens_in`/`tokens_out` columns, per `scratch/pivot-implementation-plan.md`) and the spend cap both undercount, defeating the free-first economics the Cline leg exists to deliver.
- **Contract:** if an adapter cannot recover `usage` from the raw body, it MUST leave the canonical `usage` absent (not fabricate zeros) so the existing "unknown pricing → nominal floor" estimate path (`_pre_flight_estimate`) still applies rather than a false zero. Cline *does* carry real `usage` inside `data`, so unwrapping restores true metering. Document this as a hard adapter invariant.

---

## 7. Streaming SSE contract (the main design risk)

Cline streaming is already canonical, so the shipped ClineAdapter stream method is passthrough and **no streaming code path changes in this build**. But the universal contract must be specified so a future non-canonical streamer drops in without touching the forwarder:

- **Framing vs shape separation.** The current streaming path (lines 321–402) reads fixed 8192-byte chunks — these do **not** align to SSE event boundaries. A shape transform must operate on **whole `data:` events**, so any non-identity stream adapter requires a **line-buffering wrapper** that reassembles `data: <json>\n\n` events, calls `normalize_stream_chunk(parsed)` per event, and re-serializes `data: <json>\n\n` (+ passes through `[DONE]` and comment/keepalive lines untouched). `normalize_stream_chunk` itself only ever sees one parsed event and is oblivious to framing.
- **Head-buffer interaction.** The downgrade-detection head buffer (lines 323–333) reads until it sees `model` then commits. A stream transform must be applied to the head bytes too, and applied consistently to head + remainder, so the committed stream is uniformly canonical. This is the subtle part and the reason to defer the concrete streaming transform until a real non-canonical streamer exists.
- **Decision:** ship the interface + identity default + a `normalize_stream_chunk` no-op for Cline now. Build the line-buffering framing wrapper **only when the first non-canonical-streaming provider is onboarded** (YAGNI; flagged as open question Q3). Guarding the streaming call behind `if route.adapter and adapter is not IDENTITY` keeps today's stream path byte-identical.

---

## 8. Testing strategy (tests that FAIL on revert)

Target files: `tests/test_response_adapters.py` (new, unit) + additions to `tests/test_proxy_server.py` (integration, the ticket's accept command).

**Unit (`test_response_adapters.py`):**
- `ClineAdapter.normalize_response` unwraps `{"data":{...choices...},"success":true}` → inner object with top-level `choices` + `usage`.
- Idempotent: a canonical OpenAI body passes through unchanged (identity of dict content).
- Guard: `{"data": "not-a-dict"}`, `{"data":{}, "success":true}` (no inner choices), and a bare canonical body are all passthrough (never raise).
- `IdentityAdapter` returns input unchanged for all three methods.
- `normalize_error` unwraps `{"data":{"error":...},"success":false}` → `{"error":...}`.
- `get_adapter(None)`/`get_adapter("unknown")` → `IDENTITY`; `get_adapter("cline")` → `ClineAdapter`.

**Integration / regression (the revert-guard — THIS is the one that fails on revert):**
- A `test_proxy_server.py` test that stands up the forwarder against a stub upstream returning a **wrapped** non-streaming Cline body on a route with `adapter="cline"`, drives one real non-stream request through `forward_with_failover`, and asserts the **client receives a body with top-level `choices`** (and that `usage`/cost was recorded non-zero via the observer/spend path). Reverting the shim makes the served body lack `choices` → test fails.
- Config-flow test: a registry+providers config with `provider: cline-pass` compiles (via `_build_routes_and_pools`) to an `UpstreamRoute` whose `.adapter == "cline"` (guards the `wire`-style plumbing).
- Identity-unchanged test: a normal OpenAI provider (no adapter) yields a **byte-identical** served body (proves the default path is untouched).

Accept command (from the parked ticket): `PYTHONPATH=src python3 -m pytest tests/test_proxy_server.py tests/test_response_adapters.py -q`.

---

## 9. Build task breakdown + acceptance criteria

| # | Task | Files | Acceptance |
|---|------|-------|-----------|
| T1 | New `response_adapters.py`: `ResponseAdapter` protocol, `IdentityAdapter`+`IDENTITY`, `ClineAdapter`, `_ADAPTERS`+`get_adapter` | `src/charon/response_adapters.py` (new) | unit tests §8 green; stdlib-only; every method idempotent + total |
| T2 | Config plumbing: `adapter` on `ProviderPreset`, resolve in `_route_from_spec`, field on `UpstreamRoute` | `src/charon/providers.py`, `gateway.py`, `proxy_server.py` | config-flow test: `provider: cline-pass` → `UpstreamRoute.adapter=="cline"`; `wire` behavior unchanged |
| T3 | `cline-pass` preset (base, key_env, strip_v1, `adapter="cline"`, no-`/models` note) | `src/charon/providers.py` | preset present + resolvable; STEP-3 probe note documented |
| T4 | Forwarder plug-in (a) non-stream + (b) error, behind `if route.adapter` guard | `src/charon/forwarder.py` | integration revert-guard test green; identity path byte-identical |
| T5 | Tests | `tests/test_response_adapters.py` (new), `tests/test_proxy_server.py` | accept command green |
| T6 | (Deferred) streaming framing wrapper | `forwarder.py` | NOT in this build — gated on first non-canonical streamer (Q3) |

**Files touched:** `src/charon/response_adapters.py` (new), `src/charon/providers.py`, `src/charon/gateway.py`, `src/charon/proxy_server.py`, `src/charon/forwarder.py`, `tests/test_response_adapters.py` (new), `tests/test_proxy_server.py`. Note this **widens** the parked ticket's declared `owns` (which listed only `forwarder.py` + `test_proxy_server.py`) to include the config-plumbing files and the new module — sequence so no other writer holds those files.

---

## 10. Recommended droid model

Money-path proxy code (failover loop, metering, cache/spend interactions) — highest correctness bar. Recommend the **strongest available coder** for the build: `claude-opus`-class (or the current strongest-coder in the pool, e.g. a gpt-5.4-class premium leg) — NOT a cheap-first open model. This is a `tier: strong`, `work_class: bugfix` job with a subtle metering side-effect; do not economize the builder here. Reviewer: adversarial (money-path + touches the double-bill-sensitive classify/usage path).

---

## 11. Open questions for the operator

- **Q1 — adapter scope creep.** Ship ONLY the Cline adapter now (recommended), or also pre-build the `mimo-v2.5` date-suffix case? Note: the mimo issue is a **downgrade-detection/id-normalization** problem (final id segment `mimo-v2.5-20260422` ≠ pool `mimo-v2.5`), NOT a response-shape problem — it belongs to `_normalize_model_id`, not this adapter layer. Recommend keeping it out of scope and filing separately.
- **Q2 — error unwrap.** Include `normalize_error` (5(b)) in v1, or defer? It is low-traffic and the exact Cline error envelope is unverified (STEP-1 probe only exercised 200). Recommend shipping the method with a conservative guarded unwrap + a test using a synthesized envelope, flagged "unverified shape."
- **Q3 — streaming wrapper timing.** Confirm deferring the SSE framing wrapper until the first non-canonical-streaming provider (YAGNI) vs building it now for completeness. Recommend defer.
- **Q4 — setup-API probe fix.** The `config.validate_provider_key` false-fail on `/models`-less providers (Cline) is a **separate** product bug (STEP-3/secondary note). Fold a small fix into this ticket, or file separately? Recommend separate ticket (different code path, different owner file).
