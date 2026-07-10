# SR-6 focused adversarial review — Anthropic prompt-cache breakpoint injection

Branch `feat/sr-6` @ cdde45c · worktree `/home/stack/code/charon-wt-sr6` · diff `master...feat/sr-6`

## VERDICT

**SHIP (SR-6 code) — but MERGE is BLOCKED by a red base.** The SR-6 logic itself
is correct and money-path-safe. It cannot merge CI-green because master is
**already RED** (decompose refactor), and SR-6 branched off it. Fix the base
(rebase / fix-forward), then this ships. No changes required to SR-6's own code.

Confidence: **high** on money-path safety, enrichment correctness, and the red-base
finding (verified against live CI + local gate). Medium on the default-ON cost call
(depends on traffic shape).

---

## Findings

### 1. TOP / merge-gating — master base is CI-RED; "CI-green" premise is FALSE (not SR-6's bug)
- Live CI: master HEAD `96648658` ("merge(proxy): decompose proxy_server god-file")
  = **failure**; prior merge `4cf73326` = failure; last green = `f369b7c` (0.3.6, 2026-07-07).
- Gate step `charon gate` fails at **ruff** (`gate_runner.py:7` → `ruff check src tests`, exit 1,
  hard-fails on any nonzero) with the **9 pre-existing** errors:
  - 3× F821 (`UpstreamRoute`, `GatewayProxyServer`×2 — decompose facade forward-refs)
  - 1× I001 (import sort), 5× F401 (facade re-exports `proxy_server.py:47-48`,
    `proxy_console_assets`/`proxy_response`).
- mypy (next gate step) ALSO red on the same 3 name-defined facade errors
  (`proxy_response.py:49,61`, `forwarder.py:40`).
- **Confirmed these are NOT SR-6's:** identical 9 ruff + 3 mypy errors exist on the
  master main worktree (SHA 9664865). SR-6's NEW files (`translate.py`,
  `test_translate.py`, `test_proxy_server.py` additions) pass `ruff` clean and add
  **zero** new errors. 37 SR-6 tests pass locally.
- **Consequence:** SR-6 is clean but the branch physically cannot go green until the
  decompose facade errors are fixed. Fix = add `# noqa: F401` to the facade
  re-exports + resolve the F821 forward-refs (TYPE_CHECKING import or string
  annotations) + `ruff --fix` the I001. This is a **separate base fix**, not an SR-6 edit.

### 2. Money-path byte-safety — CORRECT (verified)
- `forwarder.py:66` gates enrichment on `srv.anthropic_prompt_cache AND route.wire ==
  WIRE_ANTHROPIC`. Default `wire="openai"` (`proxy_server.py:60`, `providers.py:26`) →
  OpenAI/non-anthropic routes are never touched; only added line is under the guard, so
  the openai body reaches `json.dumps` byte-identical to pre-SR-6.
- **Failover anthropic→openai is safe:** `_build_upstream_req` is called *per attempt*
  inside the route loop (`forwarder.py:191`, `for i, route in enumerate(ordered)`), so
  each attempt re-evaluates its own `route.wire`. An openai fallback attempt is NOT
  enriched. This is a genuine strength — placement is per-attempt, not once.
- **No mutation of the shared body:** `enrich_anthropic_cache` returns a NEW dict and
  `copy.deepcopy`s the system/tools before marking; `orig_bj` is untouched, so retries
  re-enrich deterministically from a clean source. (`test_input_not_mutated`.)
- Nit (non-blocking): `test_openai_wire_route_is_byte_for_byte_passthrough` only asserts
  `cache_control` absence, not full byte-equality — name overclaims, but safety holds by
  construction (guard).

### 3. Enrichment correctness — CORRECT
- Idempotent + 4-breakpoint-cap-safe: `_has_cache_control` no-ops if ANY system block or
  tool already carries `cache_control` → never a 2nd breakpoint, never exceeds Anthropic's
  cap. Per-attempt re-enrichment always adds exactly 1 (clean source), no accumulation.
- Placement correct: breakpoint on **last system block** caches the whole tools+system
  prefix (Anthropic renders tools→system→messages, so a marker on last system covers
  both); falls back to last tool when no system. Volatile user turn stays in `messages`
  after the breakpoint → prefix byte-identical turn-to-turn (`test_prefix_byte_identical`).
- Threshold gate `MIN_CACHE_TOKENS=2048` (char/4 proxy) is a conservative floor.
  Minor: Opus/Haiku min cacheable is 4096; a 2048–4096-token prefix on Opus gets a marker
  Anthropic silently ignores (below-min → no cache, no write premium charged) → harmless
  economic no-op, not a bug.
- Conservative-but-safe: only caches tools+system, not the growing message history (leaves
  3 breakpoints unused). Smaller-than-optimal savings, correct for Phase-1.

### 4. Default-ON cost tradeoff — FLAG (not a blocker)
- Default ON adds Anthropic's cache-**WRITE** premium (~1.25× ephemeral) on every miss.
  For the agentic/Claude-Code target (frequent calls, stable prefix, <5min gaps) → net
  input-cost saving. For **sparse/one-shot** anthropic traffic (>5min gaps, long prefix)
  every request is a write miss = pure ~1.25× LOSS on the cached prefix.
- Recommendation: default-ON is defensible for the stated gateway use case, but it is a
  silent money-path behavior change enabled by default — **document the sparse-traffic
  write-premium** in operator docs. Consider whether opt-in is safer for a general
  fresh-install user. Not a merge blocker.

### 5. Product-clean / boundary gate — LEGIT, no leak
- The actual gates forbid only: `slop`/`mediastack` imports (`check_boundary.py` FORBIDDEN)
  and `/home/stack` + hex-token shapes (`check_public_clean.py`). **Neither forbids vendor
  literals** like "anthropic". So there is no gate being "worked around."
- Centralizing `WIRE_OPENAI`/`WIRE_ANTHROPIC`/`ANTHROPIC_PROMPT_CACHE_KEY` +
  `api.anthropic.com`/`ANTHROPIC_API_KEY` in `providers.py` (the provider-adapter layer,
  which already holds dozens of vendor bases/keys) is clean architecture, not a hidden
  standalone leak. Core (`forwarder`/`proxy_server`/`translate`) references constants, not
  literals. `translate.py` imports nothing forbidden; boundary/public-clean pass. Confirmed clean.

---

## Bottom line
SR-6's code is correct, byte-safe on the money path, and product-clean. The only thing
standing between it and a green merge is the **pre-existing decompose base failure** (9 ruff
+ 3 mypy). Rebase SR-6 onto a fixed master (or fold the facade `# noqa`/forward-ref fix into
this branch); no change to SR-6's own logic. Optionally document the default-ON
write-premium tradeoff.
