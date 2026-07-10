# proxy_server.py Decomposition Analysis — decompose-then-parallelize the 12-ticket god-file

Author: read-only architecture sub-session · Date: 2026-07-08
Target: `src/charon/proxy_server.py` (1229 lines, live money-path serving core)
Scope: RECOMMEND-ONLY. No code, no board edits, no commits.
Sources: the actual file; the 12 tickets' `.md`/`.md.parked` in `fleet/board/`;
`execution-optimization-plan.md`; git history.

---

## TL;DR

- **Dedup: 12 proxy_server.py contenders → 9 active units** (3 removed from the file's
  contention set: INC-401 **CLOSE/superseded**, UX-POLISH **drop proxy_server.py from owns**,
  SR-6-Phase2 **fold into SR-6 / stay parked**).
- **Split proxy_server.py into 4 new modules + a slim facade** (assets, response-helpers,
  console_router control-plane, forwarder data-plane). Behavior-preserving verbatim moves;
  facade re-exports keep every test import green.
- **Parallelism unlocked: 1 serial lane of ~9 → 2 concurrent lanes (5 routing ‖ 4 console)
  + 2 zero-risk peels.** Wall-clock on this cluster roughly halves; the routing lane's
  remaining serialism is REAL money-path coupling, not a god-file artifact.
- **Blast-radius: MEDIUM-HIGH, front-loaded into the forwarder extraction; assets +
  helpers + console_router peels are LOW.** Safe only as staged verbatim moves, tests
  green per commit, facade preserved, adversarial review on the forwarder step.
- **Sequencing: land PFF Phase-1 NOW on the current file (bleed-stopper), THEN decompose,
  THEN the two parallel lanes. PFF Phase-2 (money-path substitution) lands AFTER decompose,
  into forwarder.py.** = the operator's hybrid, confirmed, with PFF split P1/P2 across the
  decompose boundary.

---

## 1. DEDUP / RECONCILE — 12 → 9 active units (with evidence)

| # | Ticket | Verdict | Evidence / action |
|---|---|---|---|
| 1 | **PROXY-FAILOVER-FIX** | **KEEP** (Wave-1 bleed-stopper) | P1 Retry-After (`_send_resp_headers` :483, terminal 503 :826, single-upstream relay :838) + P5 UA (`_DEFAULT_UA` :71). Small, header/outbound-only. P2 (cross-tier substitution) is a later money-path phase. |
| 2 | **INC-401-FAILOVER** | **CLOSE — SUPERSEDED (DONE)** | Commit **307652d** "classify wrapped/unknown 401s as failover-eligible + synthesize all-exhausted terminal" already landed BOTH parts: proxy.py `_MODEL_UNSUPPORTED`-style patterns at **proxy.py:74-75** ("not supported", "model not found", "no such model", "unknown model") AND the `all_providers_exhausted` terminal at **proxy_server.py:830**. The ticket's line refs (:751-756) are stale. **Verify no residual, then close.** Removes it from the proxy_server.py contention set AND satisfies the `depends_on: INC-401` of DRAIN and SR-6. |
| 3 | **DRAIN-ROUTING** | **KEEP** (routing lane) | Balance/resource-aware demotion in `order_by_cooldown` + chain build. Money-path. `depends_on INC-401` now **satisfied** (done). Owns proxy.py+proxy_server.py+gateway.py+config.py. |
| 4 | **SR-13** | **KEEP** (console lane) | `/charon/login` page + surface-aware refactor of the single auth gate in `_handle`. Console/auth seam, NOT the failover loop. Its stated UX-POLISH cookie prereq is **already landed** (see #12). |
| 5 | **SR-6** | **KEEP** (routing/translate lane) | One Anthropic `cache_control` breakpoint injected in the request-body path (`_build_upstream_req` area) + NEW translate.py. `depends_on INC-401` **satisfied**. |
| 6 | **SR-6-Phase2** | **FOLD into SR-6 / STAY PARKED** | Explicit `REVISIT-TRIGGER: a user needs an OpenAI-format client to hit an Anthropic-only provider` — **unmet**. HIGH-blast SSE translation, deferred deliberately. Not an active unit; it is SR-6's Phase 2, coupled by construction (grows SR-6's translate.py). Removes it from the active set. |
| 7 | **RFL-2** | **KEEP** (console lane) | `/chat` playground inline HTML page served by the console. |
| 8 | **RFL-3** | **KEEP** (routing lane; peelable) | Image-aware exclusion in the failover-loop candidate step. Tiny one-branch filter over data that already exists (`request_inspector.has_images` + `vision` meta). Can be a fast peel. |
| 9 | **RFL-4** | **KEEP** (console lane) | Inline limit-editor POST endpoints + editable console table. Functionally depends on RFL-1 (DONE) for the quota numbers. |
| 10 | **GUI-SVELTE-BUILD** | **KEEP but GATE — CONTRADICTION** | Replaces `_CONSOLE_HTML`/`_SETUP_HTML`/`_WORK_HTML` wholesale with a Svelte SPA. **Directly contradicts RFL-2 / RFL-4 / SR-13** (WCI rule #1): any inline-HTML feature those build is deleted/rebuilt by the Svelte rewrite. Requires an explicit sequencing decision (§4), not a merge. |
| 11 | **BRIDGE-RELAYFEATURES** | **KEEP but RECONCILE — possible redundancy** | Owns proxy_server.py+proxy.py+gateway.py+config.py; `depends_on BRIDGE-HARDEN`. Header says "Incorporates RelayFreeLLM's superior features" — the RFL-1..4 tickets ARE the RelayFreeLLM port, so scope likely **overlaps RFL-***. Reconcile: trim BRIDGE to only its non-RFL "transformative gaps," or confirm it subsumes RFL-* (then don't build both). |
| 12 | **UX-POLISH** | **DROP proxy_server.py from owns** | Its only two proxy_server.py items are **already landed**: item 9 (Setup link — `setupLink` :95-96, :105-107) and item 10 (token cookie — `_maybe_set_token_cookie` :452-458, cookie set :569-575). Item 1 moved to SETUP-UX-A; item 5 is gateway.py; items 2/3/4 are cli.py; 7/8 are docs. **owns should become cli.py+gateway.py+connect.py** — leaves the proxy_server.py contention set entirely. |

**Adjacent (not in the 12) — COOLDOWN-FIX3:** primary deliverable (Retry-After ≤120s clamp
+ cooled-bucket ordering) **already landed** as f3a73f2 (visible: `max_cooldown_s=120` :1013/:1062,
`min(secs, self.max_cooldown_s)` :1153, cooled sort :1141). Residual = an edge-case audit only,
and it owns **proxy.py** (not proxy_server.py) → belongs to the proxy.py failover cluster, not this
file. Verify-not-superseded resolves to: clamp done, keep only the audit or close.

**Net contention on proxy_server.py: 12 → 9 active units.** After the split (§3) those 9 sort
into 2 disjoint module-lanes + 2 free peels.

---

## 2. SEAM ANALYSIS — proxy_server.py's distinct responsibilities

Six cohesive regions, by actual line ranges:

| Seam | Region | Lines | What it is | Coupling to the rest |
|---|---|---|---|---|
| **A. Console assets** | 3 HTML string constants `_CONSOLE_HTML`, `_WORK_HTML`, `_SETUP_HTML` | 83–332 | ~250 lines of **pure static data**, zero logic (~20% of the file) | None — pure data. Imported by tests (`_CONSOLE_HTML`, `_SETUP_HTML`). |
| **B. Response/pricing helpers** | `_extract`, `_pre_flight_estimate`, `_pre_flight_pricing` | 335–394 | Module-level **pure functions**: SSE/JSON model+usage extraction; pre-flight cost | Called by the serve loop. Imported by tests (`_extract`, `_pre_flight_estimate`). |
| **C. HTTP emit/auth helpers** | `_ProxyHandler` low-level methods: `_json`, `_html`, `_authorized`, `_maybe_set_token_cookie`, `_write`, `_drain`, `_send_resp_headers` | 397–500 | Shared HTTP substrate: response/header emit + token auth | Called by BOTH planes below. Stays on the handler shell. |
| **D. Upstream request build** | `_build_upstream_req` | 502–549 | Header filtering, **UA normalization**, model rewrite, **body normalization**, /v1 strip, key injection | The **request-translation** seam. |
| **E. Control-plane dispatch** | first half of `_handle`: loopback guard, token gate, `/v1/models`, `/charon/status`, `/charon/cost`, console HTML, `/charon/setup`+config+POST-writes (CSRF), `/charon/work` | 551–686 | The **console / setup / discovery API** router | Reads srv state; independent of the failover loop. |
| **F. Data-plane failover loop** | second half of `_handle`: body read, session id, chain_for, spend cap, guardrails, cache, `order_by_cooldown`, quality routing, the `for route in ordered` loop (non-200 / 200-nonstream / 200-stream branches, downgrade detection, exhaustion synth, caching, spend record) | 688–982 | The **money-path forwarder** (~300 lines, scarred with SR-1/SR-2/DTC fixes) | The hot path. |
| **G. Server class** | `GatewayProxyServer`: `__init__` (~25 optional deps), `route_for`, `apply_routes`, `chain_for`, `order_by_cooldown`, `set_cooldown`, `note_request`, `status_snapshot`, `url`, `serve_in_thread` | 985–1229 | **Routing state**: pools/routes, `_cooldown` + `_cooldown_lock`, stats, snapshot | Primary test import surface (`GatewayProxyServer`, `UpstreamRoute`). |

**`_handle` (551–982, ~430 lines) is the god-method** — it fuses seam E (control plane) and
seam F (data plane) into one method. That fusion is the core of the contention: console tickets
and routing tickets edit the same method.

### Proposed decomposition — 4 new modules + slim facade (facade-preserving)

Keep `GatewayProxyServer` (G) and the `_ProxyHandler` shell + shared emit/auth helpers (C) in
`proxy_server.py`. Peel A, B, E, D into new modules; split `_handle` into two delegating calls.

1. **`proxy_console_assets.py`** ← A (83–332). The HTML constants (soon `_CHAT_HTML`, then the
   Svelte `dist/` pointer). `proxy_server` re-exports `_CONSOLE_HTML`/`_SETUP_HTML`/`_WORK_HTML`.
   *Owners after split:* GUI-SVELTE (replaces), RFL-2 (adds `_CHAT_HTML`).
2. **`proxy_response.py`** ← B (335–394). `_extract`, `_pre_flight_estimate`, `_pre_flight_pricing`.
   `proxy_server` re-exports `_extract` + `_pre_flight_estimate` (test imports).
   *Owners after split:* stable; SR-6-Phase2 response translation could extend later.
3. **`console_router.py`** ← E (551–686) + calls into A. A function
   `try_handle_control_plane(handler, srv) -> bool` (True = request served). `_handle` calls it
   first; on True, return.
   *Owners after split:* SR-13 (login/auth dispatch), RFL-2 (`/chat`), RFL-4 (POST limit endpoints),
   GUI-SVELTE (static-asset serving). **All console tickets land here.**
4. **`forwarder.py`** ← F (688–982) + D (502–549, `_build_upstream_req`). A function
   `forward_with_failover(handler, srv, ...)`; `_handle` calls it for the proxy path.
   *Owners after split:* PFF-P2 (substitution), DRAIN (ordering integration), RFL-3 (image filter),
   SR-6 (cache_control body injection), BRIDGE-RELAY. **All routing tickets land here.**

`_handle` collapses to: loopback/token gate → `if console_router.try_handle_control_plane(): return`
→ `forwarder.forward_with_failover()`. Shared helpers (C) stay on the handler and are passed the
handler instance.

### Test-coverage & arch constraints (behavior-preserving requirements)

- **Public import surface that MUST keep resolving from `charon.proxy_server`** (or tests break):
  `GatewayProxyServer`, `UpstreamRoute`, `_CONSOLE_HTML`, `_SETUP_HTML`, `_extract`,
  `_pre_flight_estimate`. Solution: **facade re-exports** from the slim proxy_server.py.
- `tests/test_proxy_server.py` = **795 lines / 18 tests** exercising the server end-to-end
  (mock upstreams, pools, downgrade, streaming, cache, spend). Plus proxy_server is imported by
  **13 test files** (gateway, gateway_failover, fallback_provider, policy_router, setup_tiers,
  tier_lifecycle, console_work, boundary, no_secrets, agent_launch_routing, run_task_routing,
  check_arch). Any split must keep all green with **no logic change** in the move commits.
- **Arch boundary (`tests/test_check_arch.py`):** `_ENGINE_FORBIDDEN` contains `"proxy_server"`
  (engine may not import it, and it may not import engine/vendor). **The 4 new modules must be
  added to `_ENGINE_FORBIDDEN`**, or the engine-import guard weakens — this is a required part of
  the refactor, not optional.
- **Threading:** `_cooldown_lock` guards `chain_for`/`order_by_cooldown`/`set_cooldown`/`apply_routes`
  as a unit — those stay together on `GatewayProxyServer` (seam G, unsplit). forwarder.py calls them
  through `srv`, never re-implements locking.

---

## 3. POST-DECOMPOSITION OWNS MAP — who lands where

| New module | Tickets that own it (post-dedup) | Lane |
|---|---|---|
| `forwarder.py` (+ request build) | PFF-P2, DRAIN, RFL-3, SR-6, BRIDGE-RELAY | **Routing lane (5)** |
| `console_router.py` (+ assets) | SR-13, RFL-2, RFL-4, GUI-SVELTE | **Console lane (4)** |
| `proxy_console_assets.py` | GUI-SVELTE (replace), RFL-2 (`_CHAT_HTML`) | (part of console lane) |
| `proxy_response.py` | — (stable) | **Free peel** |
| `GatewayProxyServer` (proxy_server.py) | DRAIN (`order_by_cooldown`/`chain_for`), PFF-P2 (`chain_for`), GUI-SVELTE Phase-0 (`status_snapshot`) | shared by routing lane; Phase-0 disjoint |
| proxy.py (separate file) | INC-401 (**done**), COOLDOWN-FIX3 (audit), DRAIN, BRIDGE | parallel proxy.py lane |

**Parallelism quantified:**
- **Before:** 1 serial lane, up to 12 units strictly serialized on one file. Critical path = every
  ticket in sequence on proxy_server.py; the file "bounds wall-clock" (per the exec plan §Critical Path).
- **After dedup (12 → 9) + decomposition:**
  - **2 concurrent module-lanes** — Routing (forwarder.py, 5 units) ‖ Console (console_router.py, 4 units).
  - **2 free peels** — `proxy_response.py` (nobody contends) and `proxy_console_assets.py`
    (GUI-SVELTE prep), plus RFL-3 is a quick peel off the routing lane.
  - INC-401's classification work already lives in **proxy.py**, off this file entirely.
- **Net:** the single 9-deep serial queue becomes **two ~4-5-deep lanes running in parallel** →
  wall-clock on this cluster **≈ halves**. The routing lane's residual serialism (PFF-P2 → DRAIN →
  SR-6) is **genuine money-path coupling** (they edit the same failover semantics; DRAIN's ordering
  interacts with PFF-P2's substitution), NOT a god-file artifact — decomposition cannot and should
  not parallelize it further. The console lane's residual serialism is the GUI-SVELTE contradiction
  (§4), a decision, not a file lock.

**Collisions that REMAIN after the split (honest):**
- Routing lane stays serial internally (real coupling) — but it is now fully **parallel to** the console lane.
- Console lane: RFL-2/RFL-4/SR-13 all edit `console_router.py`'s dispatch + add HTML → still serialize
  among themselves on that module, but off the routing lane. GUI-SVELTE **contradicts** them (§4).
- `GatewayProxyServer` (unsplit): DRAIN + PFF-P2 both touch `chain_for`/`order_by_cooldown` → they
  serialize there anyway (same as the routing lane; consistent).

---

## 4. BLAST-RADIUS + SEQUENCING

### Risk of splitting a live money-path core

| Risk | Severity | De-risk |
|---|---|---|
| Behavior drift in the failover loop (double-bill / downgrade regressions — the file carries SR-1/SR-2/DTC BLOCKER scar tissue) | **HIGH** | Pure **verbatim move**, zero logic change in the move commit; full suite green; adversarial review on the forwarder step only. |
| Break the public import surface (`GatewayProxyServer`, `UpstreamRoute`, `_CONSOLE_HTML`, `_SETUP_HTML`, `_extract`, `_pre_flight_estimate`) → 13 test files fail | **HIGH (but mechanical)** | **Facade re-exports** from slim proxy_server.py. Caught instantly by the suite. |
| Arch boundary weakens (`_ENGINE_FORBIDDEN` only lists `proxy_server`) | **MEDIUM** | Add the 4 new modules to `_ENGINE_FORBIDDEN` in the same PR; `test_check_arch.py` guards it. |
| Torn lock semantics across modules (`_cooldown_lock`) | **MEDIUM** | Keep seam G (routing state + lock) unsplit on `GatewayProxyServer`; forwarder calls through `srv`. |

**Verdict: MEDIUM-HIGH overall, front-loaded into the forwarder (F) extraction.** The assets (A),
response-helpers (B), and console_router (E) peels are **LOW** risk — A/B are already independently
imported pure data/functions; E is control-plane, off the money path. The decomposition is safe
**only** as staged verbatim moves with the facade preserved and tests green per step. It is **NOT**
safe as a big-bang rewrite, and no logic change may ride along in a move commit.

### PFF-vs-decomposition: land PFF Phase-1 FIRST, then decompose (recommended)

**Recommend Option A (operator's hybrid), refined by splitting PFF across the decompose boundary:**

- **PFF Phase-1 first, on the current file.** It is tiny, header/outbound-only, LOW-RISK, and the
  active **bleed-stopper** (~8h client stall). It must not wait behind a multi-commit money-path
  refactor whose payoff is throughput. Stop the bleeding, then optimize the assembly line. Its diff
  (`_send_resp_headers` +1 param, `_DEFAULT_UA`, a `retry_after_hint` helper) rebases trivially onto
  the decomposition either way.
- **Then decompose** (before the heavy routing/console clusters start).
- **PFF Phase-2 (money-path cross-tier substitution) lands AFTER decompose, into forwarder.py +
  `chain_for`.** P2 is exactly the design-sensitive routing-loop change the decomposition exists to
  make safely-ownable — and PFF's own ticket already gates P2 as a later opt-in phase. Do **not**
  fold P2 into the current file.

*Why not decompose first (fold all of PFF in)?* It delays the bleed-stopper for a throughput refactor
— inverts priority. *Why not skip decompose and just serialize?* That keeps the 9-deep serial queue
the operator is trying to dissolve.

### Revised wave schedule — THIS cluster only

- **Wave A (now):** **PFF Phase-1** (Retry-After + UA) on the current proxy_server.py. Adversarial
  review (money-path framing, C2). Merge. *In parallel, off-file:* close **INC-401** (verify done),
  and the **COOLDOWN-FIX3** proxy.py audit — both on proxy.py, disjoint from proxy_server.py.
- **Wave B (decompose — single owner holds proxy_server.py briefly, serial, one module per commit,
  suite green each):**
  1. extract `proxy_console_assets.py` (A) — LOW risk.
  2. extract `proxy_response.py` (B) — LOW risk.
  3. extract `console_router.py` (E) — LOW risk.
  4. extract `forwarder.py` (F + D) — **HIGH risk, adversarial review here.**
  Add all 4 to `_ENGINE_FORBIDDEN`; facade re-exports; rebase PFF-P1's small diff (trivial).
- **Wave C (two PARALLEL lanes, unlocked by decompose):**
  - **Routing lane** (forwarder.py / server class, serial by real coupling): **PFF-P2 → DRAIN → SR-6**;
    **RFL-3** as a quick peel; **BRIDGE-RELAY** after its RFL-overlap reconcile + BRIDGE-HARDEN.
  - **Console lane** (console_router.py / assets, gated by the GUI-SVELTE contradiction):
    - If **GUI-SVELTE deferred** (recommended — it's opus-huge, inline console works, no demand):
      SR-13 + RFL-2 + RFL-4 ship on inline HTML (serialize the shared dispatch edits, but off the
      routing lane).
    - If **GUI-SVELTE prioritized:** GUI-SVELTE Phase-0/1 first, then RFL-2/RFL-4 rebuilt as Svelte
      panels (do NOT build inline versions that the rewrite deletes).
- **Final:** ATC adversarial audit of all merged work.

**The one decision the operator still owns:** GUI-SVELTE-BUILD vs the inline-HTML console tickets
(RFL-2/RFL-4/SR-13) — a genuine contradiction (WCI rule #1). Decomposition isolates it to the console
lane but does not resolve it; pick defer-GUI (inline ships) or GUI-first (panels rebuilt in Svelte)
before Wave C's console lane starts.
