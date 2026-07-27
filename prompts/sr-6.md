# SR-6 — Anthropic prompt-cache injection (PHASE-1)

## Status: design-approved 2026-07-04 — BUILD (no longer design-gated)
The design note `/home/stack/charon-private/fleet/SR-6-DESIGN.md` is operator-signed. This ticket is
scoped to **Phase-1 ONLY**: a low-risk, high-value cost saving — inject one Anthropic prompt-cache
breakpoint into request bodies that are ALREADY routed to an Anthropic-wire upstream. Read
SR-6-DESIGN.md (§1–§4, §8) for the full spec before building; this prompt is the executable summary.

## Dependencies & sequence
**depends_on: SR-2 — Wave 3 (W3), FIRST in the SR-6 → SR-7 → SR-8 chain.** `real-dep: SR-2 build
(single-owner file proxy_server.py)` — SR-6 edits proxy_server.py, which SR-2 also owns; it must land
AFTER SR-2 so the two never write the shared file concurrently. SR-7 then SR-8 sequence after SR-6 on
the same file. `translate.py` is a NEW module (no collision). Concurrency-safety: within W3 only one
of SR-6/SR-7/SR-8 is ever in flight on proxy_server.py because the chain is strictly ordered. The
flag/marker plumbing lightly touches `gateway.py` + `providers.py` (outside this ticket's stated owns)
— note it in the review-log at sign-off (see CONSTRAINTS).

## Shared context (grounding for a fresh session)
Part of the SR gateway cost-correctness series (whose P0, SR-1, fixed the namespaced false-downgrade
double-bill). An Anthropic-wire request that carries no `cache_control` pays FULL input price every
turn — the single biggest quality-FREE saving still unimplemented. Phase-1 enriches an **already-
Anthropic** body destined for an Anthropic upstream; it is an enrichment pass, NOT a format rewrite,
so no response-side or streaming change is needed. Full bidirectional OpenAI↔Anthropic translation
(the risky large surface) is deliberately split out and PARKED as **SR-6-Phase2** — do NOT build it here.

## What to build (Phase-1)
1. **Config flag `anthropic_prompt_cache: bool = True`** (default ON), plumbed IDENTICALLY to the
   existing `failover_on_downgrade` reference pattern:
   - `gateway.py` `GatewayConfig`: add field `anthropic_prompt_cache: bool = True`.
   - `gateway.py` toml + gateway.json load: read `anthropic_prompt_cache`, default True.
   - `gateway.py` `build_server()`: pass through to the server ctor.
   - `proxy_server.py` ctor: accept `anthropic_prompt_cache: bool = True`; store `self.anthropic_prompt_cache`.
   - Operator turns it OFF via `[gateway] anthropic_prompt_cache = false` (toml) or
     `{"anthropic_prompt_cache": false}` (gateway.json). When OFF → body forwarded byte-identical.
2. **Provider-agnostic Anthropic-wire marker (no hardcoded model list):**
   - `providers.py` `ProviderPreset`: add `wire: str = "openai"` (`"openai"` | `"anthropic"`); mark the
     Anthropic preset `wire="anthropic"`; operator providers set it in `[providers.<name>]`.
   - `proxy_server.py` `UpstreamRoute`: add `wire: str = "openai"`; `gateway._build_routes_and_pools`
     copies preset/override `wire` onto the route. Detection at dispatch = `route.wire == "anthropic"`.
3. **`src/charon/translate.py` (NEW):** `enrich_anthropic_cache(body) -> dict` — pure/stdlib, returns a
   new dict. Inject exactly ONE `cache_control:{"type":"ephemeral"}` on the **last `system` block** (or
   the **last tool definition** if no system). No-op (returns input unchanged) when: not Anthropic-shaped;
   the stable prefix is under ~2048 tokens (reuse the char/4 heuristic from `request_inspector`); or a
   `cache_control` is already present (idempotent — never a 2nd breakpoint, never exceed Anthropic's 4).
   Keep everything volatile (latest user turn, ids, timestamps) AFTER the breakpoint so the cached prefix
   is byte-identical across turns.
4. **Wire into `proxy_server.py` `_build_upstream_req`** (the one per-attempt body-rebuild site):
   `if self.anthropic_prompt_cache and route.wire == "anthropic": bj = translate.enrich_anthropic_cache(bj)`
   — the enrich branch is UNREACHABLE for OpenAI-wire routes; per-attempt placement makes a failover to
   an OpenAI provider automatically untouched.

## What NOT to build (deferred to SR-6-Phase2, parked)
- No OpenAI→Anthropic (or reverse) body translation. No response-body translation. No SSE/streaming
  event remap. No cache pre-warming (`max_tokens:0`). No 1h TTL. OpenAI-wire routes are NEVER touched.

## Acceptance / tests (`tests/test_translate.py`, + a case in `tests/test_proxy_server.py`)
- `anthropic_prompt_cache` defaults True; set False → Anthropic-bound body is byte-identical passthrough.
- Anthropic-wire route, stable prefix ≥ min → exactly ONE `cache_control` on the last system block (last
  tool when no system); prefix byte-identical across two consecutive turns (same system, new user turn).
- Prefix below min, or a body that already carries `cache_control` → left unchanged (idempotent, ≤4).
- EVERY OpenAI-wire request is byte-for-byte pass-through (regression-guarded).
- `route.wire` defaults `"openai"`; only `"anthropic"` enters the enrich branch.
- Full suite green: `PYTHONPATH=src python3 -m pytest -q`.

## CONSTRAINTS
- **Owns:** `src/charon/translate.py` (NEW), `src/charon/proxy_server.py`. The flag/marker plumbing
  also lightly touches `gateway.py` (GatewayConfig field) + `providers.py` (ProviderPreset `wire`
  marker) — these are OUTSIDE the stated owns; flag them as touched-for-plumbing in the REVIEW-LOG at
  sign-off (confirm no collision with a live gateway.py/providers.py owner before landing).
- Provider-agnostic dispatch (detection by `route.wire`, NOT a hardcoded model list). Product-clean.
- No streaming or response-body changes; with the flag OFF, behaviour is byte-identical to today.

## accept
```
PYTHONPATH=src python3 -m pytest -q tests/test_translate.py tests/test_proxy_server.py && PYTHONPATH=src python3 -m pytest -q && ruff check src/charon/translate.py src/charon/proxy_server.py && mypy src/charon/translate.py src/charon/proxy_server.py
```

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
