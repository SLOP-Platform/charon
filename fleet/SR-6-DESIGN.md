# SR-6 — Design note: Anthropic prompt-cache injection + OpenAI→Anthropic translation

**Status:** DESIGN-GATED — awaiting operator sign-off before build.
**Operator intent (verbatim):** "make what changes are reasonable to reduce costs (ex: repeated
context). It should be ON by default with an off/on switch available to user."
**Owns (per ticket):** `src/charon/translate.py` (NEW), `src/charon/proxy_server.py`.

---

## 0. TL;DR decision to sign off

Ship the cost saving in **two phases**, land only Phase 1 under SR-6:

- **Phase 1 (this ticket):** for routes whose upstream speaks the **Anthropic wire format**, inject a
  single `cache_control` breakpoint at the end of the stable prefix of the **already-Anthropic body**.
  This captures the operator's cost goal for the common case (Claude Code / any Anthropic-native ACP
  agent pointed at the gateway → an Anthropic upstream). Tiny blast radius: an enrichment pass, not a
  format rewrite. **ON by default**, gated by one config flag.
- **Phase 2 (DEFER — separate ticket):** full **bidirectional** OpenAI↔Anthropic translation (request
  body + response body + streaming SSE event remap) so an OpenAI-format client can reach an
  Anthropic-wire upstream. This is the large, risky surface (see §5). Not required to bank the saving.

`translate.py` is created in Phase 1 (request-side enrichment + the body-shape helpers), and grows into
the full translator in Phase 2. This note designs Phase 1 concretely and specs Phase 2's shape.

---

## 1. Config flag (the ON/OFF switch), mirroring `failover_on_downgrade`

**Flag: `anthropic_prompt_cache: bool = True`** (default ON — inverse default of `failover_on_downgrade`,
which is False).

Plumbed identically to `failover_on_downgrade` (already the reference pattern in the tree):

| Layer | Change |
|---|---|
| `gateway.py` `GatewayConfig` (~line 67) | add field `anthropic_prompt_cache: bool = True` |
| `gateway.py` toml load (~line 183) | `cfg_anthropic_prompt_cache = bool(gw.get("anthropic_prompt_cache", True))` |
| `gateway.py` gateway.json load (~line 202) | same key from `gw_file`, default True |
| `gateway.py` `build_server()` (~line 252 / 371) | pass through to server ctor |
| `proxy_server.py` ctor | add `anthropic_prompt_cache: bool = True`; store `self.anthropic_prompt_cache` |

Operator switches it off with `[gateway] anthropic_prompt_cache = false` in the toml, or
`{"anthropic_prompt_cache": false}` in `~/.charon/gateway.json`. Default-ON satisfies "on by default,
switch available." When OFF, the request body is forwarded byte-identical (pure passthrough).

---

## 2. Provider detection (how a route is identified as Anthropic-bound) — provider-agnostic

No hardcoded model list. Add a **wire-format marker on the provider**, carried onto the route:

- `providers.py` `ProviderPreset`: add `wire: str = "openai"` (values `"openai"` | `"anthropic"`). Mark
  the Anthropic preset `wire="anthropic"`; operator-added providers set `wire` in the
  `[providers.<name>]` table. Presets register it — no model enumeration.
- `proxy_server.py` `UpstreamRoute`: add `wire: str = "openai"` (frozen dataclass, one more field next
  to `provider`/`strip_v1`). `gateway._build_routes_and_pools` copies preset/override `wire` onto the
  route.
- Detection at dispatch = `route.wire == "anthropic"`. A route-level property, not a model regex, so it
  is provider-agnostic and survives new Anthropic-format providers (e.g. Bedrock-Mantle-style bases).

Anything not marked `anthropic` is treated as OpenAI-wire and is **never touched** (transparent-proxy
contract preserved).

---

## 3. Breakpoint placement heuristic (where `cache_control` goes)

Anthropic caching is a **prefix match** — any byte change before a breakpoint invalidates it. Render
order is `tools` → `system` → `messages`. Rules:

1. **One breakpoint, at the end of the largest stable prefix.** Put `cache_control:{"type":"ephemeral"}`
   on the **last `system` block**; if `system` is absent, on the **last tool definition**. A marker on
   the last system block caches `tools`+`system` together (both render before it).
2. **Skip when below the cacheable minimum.** Estimate prefix tokens (reuse the char/4 heuristic from
   `request_inspector`); if under ~2048 (Anthropic wire uses the 4096 floor on Opus/Haiku, 2048 on
   Sonnet/Haiku3.5 — use the conservative 2048 gate), inject nothing (a marker on a short prefix
   silently won't cache and just adds a write premium).
3. **Never mark volatile content.** The latest user turn, per-request IDs, timestamps stay **after** the
   breakpoint. Do not add our own breakpoint on `messages` in Phase 1 — the system/tools prefix is the
   stable, high-value target; multi-turn message-tail caching is a Phase-2 refinement.
4. **Determinism:** if we ever re-serialize tools, sort by name; but in Phase 1 we **enrich in place**
   (add one key to an existing block) and re-`json.dumps` — Python preserves dict insertion order, so
   the prefix stays byte-identical turn-to-turn as long as the client sends a stable system/tool block.
5. **Respect an existing breakpoint.** If the client already placed any `cache_control`, do nothing
   (idempotent — never add a second breakpoint or exceed Anthropic's 4-breakpoint cap).

**Two-sentence version (for the return):** Inject exactly one `cache_control:{"type":"ephemeral"}` on the
last `system` block (or last tool if no system), which caches the whole `tools`+`system` prefix, and only
when that prefix clears the ~2048-token minimum. Keep everything volatile (latest user turn, ids,
timestamps) after the breakpoint and never add a second one, so the cached prefix stays byte-identical
across turns.

---

## 4. Wiring into `proxy_server.py`

Single call site in `_build_upstream_req` (already the one place the body is rebuilt per attempt):

```
bj = dict(orig_bj)
if bj:
    if route.upstream_model: bj["model"] = route.upstream_model
    if bj.get("stream") is True: ... include_usage ...
    if srv.anthropic_prompt_cache and route.wire == "anthropic":
        bj = translate.enrich_anthropic_cache(bj)   # NEW — Phase 1: inject breakpoint, in place
    data = json.dumps(bj).encode()
```

`translate.enrich_anthropic_cache(body)` is pure/stdlib, returns a new dict, no-ops (returns input
unchanged) if: not Anthropic-shaped, prefix under the min, or a breakpoint already present. **No-op for
every OpenAI-wire route** — those never reach this branch. `_build_upstream_req` is per-attempt, so a
failover to an OpenAI provider in the same chain is automatically untouched.

Because Phase 1 enriches an **already-Anthropic** body, no response-side change is needed — the Anthropic
upstream returns Anthropic-format, which an Anthropic-native client already understands. Cache hits show
up in the upstream's `usage.cache_read_input_tokens`; surface it later via `observability` (SR-8).

---

## 5. Streaming interaction

Phase 1: **none.** We add a key to the request JSON; the response stream (Anthropic SSE) flows back
untouched exactly as today. `cache_control` only affects request pricing, not the response shape.

Phase 2 (deferred): streaming is the hard part — Anthropic emits `message_start` /
`content_block_delta` / `message_delta` SSE events; an OpenAI client expects `chat.completion.chunk`
events. A Phase-2 translator must remap the SSE event stream on the fly (and translate the non-stream
JSON body too). This is why full cross-translation is deferred, not folded into SR-6.

---

## 6. Other reasonable cost reductions worth folding in

- **1-hour cache TTL for warm agents** (`{"type":"ephemeral","ttl":"1h"}`): only pays off with ≥3
  reads and doubles the write premium. **Recommend leaving default 5-minute TTL**; expose as a
  sub-option later, not in SR-6.
- **Session affinity → warm caches.** `session_affinity` (SR-8) already exists to pin `X-Session-ID` to
  a provider; wiring it (SR-8) keeps the Anthropic prefix cache warm for a conversation — a direct
  multiplier on this saving. Note the dependency in SR-8, don't build it here.
- **Do NOT** add cache pre-warming (`max_tokens:0`) here — it belongs to an agent lifecycle, not a
  transparent proxy. Out of scope.

---

## 7. Blast radius

- **Must not break non-Anthropic providers:** guaranteed by the `route.wire == "anthropic"` gate — the
  enrichment branch is unreachable for OpenAI-wire routes; their body is `json.dumps`'d as today.
- **Transparent-proxy contract:** Phase 1 adds at most one key to an already-Anthropic body destined for
  an Anthropic upstream; it changes request **pricing metadata**, not semantics, and is idempotent. With
  the flag OFF, behaviour is byte-identical to today.
- **Failover safety:** enrichment is per-attempt inside the failover loop, so a chain that fails over
  from an Anthropic route to an OpenAI route re-runs `_build_upstream_req` and the OpenAI attempt is
  untouched.
- **Real risk lives in Phase 2** (bidirectional body + SSE translation) — explicitly deferred so SR-6
  ships a low-risk, high-value slice. SR-7 and SR-8 sequence after SR-6 on the same file regardless.

---

## 8. Ticket-ready spec (Phase 1)

**Owns:** `src/charon/translate.py` (NEW), `src/charon/proxy_server.py` (+ `gateway.py`, `providers.py`
for the flag/marker plumbing — flag these as touched-for-plumbing in the review-log since they're
outside the ticket's stated `owns`; confirm at sign-off).

**Acceptance criteria:**
1. `anthropic_prompt_cache` defaults **True**; set False in `[gateway]` / `gateway.json` disables it;
   when disabled the Anthropic-bound body is byte-identical passthrough.
2. An Anthropic-wire route with a stable prefix ≥ min gets **exactly one** `cache_control` breakpoint at
   the last system block (or last tool); prefix is byte-identical across two consecutive turns.
3. A prefix below the min, or a body that already carries `cache_control`, is left unchanged (idempotent,
   no second breakpoint, never exceeds 4).
4. **Every OpenAI-wire request is byte-for-byte pass-through** (regression-guarded).
5. `PYTHONPATH=src python3 -m pytest -q` green; `ruff` + `mypy` clean on owned files.

**Tests (`tests/test_translate.py`):**
- breakpoint lands on last system block; on last tool when no system; skipped under token min.
- idempotent when a breakpoint already present; never emits >4 breakpoints.
- byte-identical prefix across turns (same system, new user turn).
- flag OFF → identical bytes to input; OpenAI-wire route → untouched (in `test_proxy_server.py`).
- unit: `route.wire` defaults `"openai"`; only `"anthropic"` enters the enrich branch.
