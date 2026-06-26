# ADR-0005 — Gateway-first Charon: a local OpenAI-compatible failover gateway, orchestrator as opt-in

> **Supersedes in part ADR-0001:** its §1 orchestrator-first framing, its §7
> "INTEGRATE routing/fallback" decision (Charon now *builds* the gateway plane), and the
> scope of PERF-1 "never a proxy in the token stream" (now the orchestrator hot path
> only, not gateway mode). ADR-0001's continuity plane, fence/autonomy ladder, and
> thin-core invariants remain in force.

- **Status:** Accepted (2026-06-26)
- **Deciders:** Rafael (operator)
- **Relates to:** ADR-0001 (thin orchestrator), ADR-0002 (boundary), ADR-0003 (planes),
  ADR-0004 (routing/gateway/pools/frontend — this ADR promotes its R1 proxy to the product)
- **Grounded by:** direct read of the existing core (`src/charon/proxy_server.py`,
  `proxy.py`, `pools.py`, `router.py`, `service/app.py`, `cli.py`) + the gateway-first
  vision clarified with the operator 2026-06-26. Adversarially self-reviewed below
  before any implementation (house rule: plan-before-code).

## Context

ADR-0004 framed Charon as an **orchestrator** (`charon run` drives ACP agents) whose
gateway proxy was a *means* — an observation seam so the coordinator could detect
exhaustion and fail over at checkpoint boundaries. The operator has since clarified
the actual product (memory `charon-vision-gateway-first`):

- Charon is a **solo-dev, local, OpenAI-compatible GATEWAY** that fronts many
  providers (OpenCode Zen ✓, OpenRouter, NanoGPT, ZAI, local LM Studio/Jan/Ollama)
  with **visible, cost-ranked failover** — when one provider hits a session/rate cap,
  the next serves transparently, no waiting for resets.
- **Any** OpenAI-compatible client (Cursor, Cline, Aider, Chatbox, Jan, Msty, …)
  points at `http://localhost:<port>/v1` and just works. "Many clients" = broad
  *compatibility*, NOT concurrency/multi-tenancy.
- The autonomous orchestrator (`charon run`: Ledger + executable acceptance + fence)
  becomes an **opt-in feature** sharing the **same provider/failover core**.

~80% already exists: `GatewayProxyServer` is a pure-stdlib loopback OpenAI-compatible
proxy with multi-upstream routes, 429/402/silent-downgrade detection, server-side key
holding, and SSE pass-through. The gaps are: run it **standalone always-on**, do
**transparent in-request failover** (today the *coordinator* fails over, not the
gateway), provider **presets**, a **live web console**, and **Windows packaging**.

This ADR records the decisions that make the gateway the primary product.

## Decisions

### D1 — Two modes, one provider/failover core
The shared core is exactly three existing modules, kept **provider-agnostic and
stdlib-only**:
- `pools.py` — the provider/model registry + `choose_from_pool` (free-first,
  cost-ranked, `exclude`-aware) selection.
- `proxy.py` `GatewayProxy` — the response **classifier**: 429/402/503 = exhausted,
  404 = dropped, 200-with-model-mismatch = silent downgrade; usage/cost accounting.
- `proxy_server.py` `GatewayProxyServer` — the stdlib HTTP forwarding shell.

Two consumers sit on top, **neither privileged in the core**:
- **Gateway mode** (`charon gateway`, new): a long-lived server; clients call `/v1`;
  failover happens **in the request path**.
- **Orchestrator mode** (`charon run`, existing): drives a stateful ACP agent;
  failover happens at **checkpoint boundaries** (kill agent → re-route pool → respawn).

The orchestrator MUST keep working — it is a regression gate, not a rewrite target.

### D2 — Failover locus differs by mode; classification + ordering are shared
- A raw OpenAI client has no Ledger and no checkpoints — it just wants a completion.
  So the **gateway absorbs failover transparently**: on a failover signal it walks
  the cost-ranked pool, excludes the failing provider, retries the next, and returns
  the first honest success — **within the same client HTTP request** (new work, P2).
- The orchestrator keeps **boundary** failover because ACP has no "set model"; the
  agent owns a stateful session that can only be swapped between dispatches.
- **Shared, not duplicated:** both use `GatewayProxy`'s classification and
  `choose_from_pool`'s ordering. The gateway's in-request loop = "walk pool, exclude
  on signal, stop at first 2xx-honest," bounded by pool size.

### D3 — Failover MUST be visible (operator hard requirement)
- Every gateway response carries `X-Charon-Provider` (who served it) and
  `X-Charon-Failovers` (count; which providers were skipped and why).
- A structured **failover event log** (JSONL: ts, request id, attempts, per-attempt
  provider/status/reason/cost) the console tails.
- The web console (P4) shows a live request stream + per-provider usage/cost/
  failover/health. Silent failover is a defect, including the case where we *could
  not* fail over (see Review R1) — that must be surfaced too.

### D4 — Provider registry + presets (extend, don't reinvent)
The registry abstraction already exists as `PoolEntry` (`upstream_base`, `key_env`,
`upstream_model`, `cost_tier`, `cost_rank`, `code_safe`, `free`). A **provider** adds
provider-level metadata + **quirks** (User-Agent override, `strip_v1`, header rules,
a `downgrade_prone` flag that arms strict silent-downgrade checking). Ship **presets**
for OpenRouter, NanoGPT, ZAI, and a generic local OpenAI-compatible upstream
(LM Studio / Jan / Ollama on `localhost`). OpenCode Zen is already wired
(`opencode-go`). Cost-rank ordering is editable; default **free → cheap → paid**.

### D5 — Security posture (single-user threat model, stated)
- **Loopback bind by default** (reuse the `service/__main__` guard:
  `_is_loopback` + refuse a non-loopback bind without a token). Non-loopback requires
  **explicit opt-in + a bearer token** (`CHARON_SERVICE_TOKEN` pattern, constant-time
  compare).
- **Provider keys** are held server-side and injected into the upstream request;
  never logged, echoed, or returned (existing invariant — keep it).
- **Core stays stdlib-only.** Any new dependency (PyInstaller; a web framework for the
  console) goes behind a pyproject **optional-extra**, never in the privileged gateway
  path. `tomllib` (stdlib ≥3.11) reads config — no TOML dependency needed.
- The gateway is **single-user**: the token is the only boundary; no per-request
  identity. This is the model, not a gap (see Review R8).

### D6 — Config: one registry schema, a `charon.toml` surface
Single-user config lives in a `charon.toml` (providers, key-env names, pools/cost-rank,
bind host/port, token). It loads into the **same in-memory provider/pool model** the
orchestrator uses. **No parallel schema.** To de-risk P1, the gateway first reads the
existing `.charon/models.json` + `pools.json` directly; `charon.toml` is added as
ergonomic sugar (P5) that compiles to the same structures. (See Review R5.)

### D7 — Packaging: single Windows `.exe` (PyInstaller), isolated workflow
PyInstaller single-file `.exe` that starts the gateway and opens the local console;
`charon.toml` + a first-run helper. Built on the **free `windows-latest`** runner in a
**separate** GitHub workflow that **does NOT touch** the Linux `[self-hosted, 4-lom]`
CI. Tray app is a stretch goal.

### D8 — Orchestrator reframed as opt-in
`charon run` (ACP + Ledger + acceptance + fence) stays, on the shared core, documented
in README as the **autonomy toggle** the user turns ON. The README's primary framing
becomes the gateway; the orchestrator is the advanced opt-in.

---

## Adversarial review (self-review before code)

Charge: attack the gateway-first design where it will actually break — streaming
semantics, money, security, and the "one core" claim. Reconciled per finding.

### R1 — Streaming makes transparent failover only *partially* possible (the hard one)
Once a 200 SSE stream's bytes have been forwarded to the client, failover is
impossible — you cannot un-send. But the two failover signals arrive at different
times:
- **Exhaustion (429/402/503/404)** arrives in the **response status/headers, before
  any body.** So the gateway can retry transparently *iff it forwards nothing until
  the first upstream returns headers.* **Resolution:** the request path buffers until
  upstream headers; on an exhaustion status it fails over with zero client-visible
  bytes. Clean and transparent.
- **Silent downgrade (pseudo-success)** is a 200 whose `model` ≠ requested — and that
  id is only in the **first SSE chunk**. **Resolution:** buffer up to the first chunk
  carrying `model` (tiny, sub-kB), classify; if downgraded and nothing forwarded yet,
  fail over. If a downgrade is detected only *after* committing bytes, we CANNOT
  retract → emit a **loud** `X-Charon-Downgrade` header + failover-failed log event +
  console alert. "Visible failover" explicitly includes "visible that we could not."
- Non-streaming responses are buffered whole → classify and fail over freely.

This is the central engineering risk; P2 must encode it as the failover state machine,
with tests for: pre-body 429 → silent failover; first-chunk downgrade → silent
failover; mid-stream downgrade → surfaced-not-hidden.

### R2 — `Retry-After` must never block the client
A 429 with `Retry-After: 3600` means "out for an hour," not "sleep this request for an
hour." **Resolution:** in-request, `Retry-After` only means *exclude this provider,
move on now*. The gateway keeps a **per-provider cooldown map** (provider →
not-before timestamp) so *subsequent* requests skip a known-exhausted provider until
its window passes. No single request ever sleeps on a provider's reset.

### R3 — "One core" must not let the gateway regress the orchestrator's fence
The gateway request path must **never** import or invoke `coordinator.run` (generalizes
ADR-0002 §2.3's read-only-web invariant). **Resolution:** the gateway is a *sibling*
consumer of `pools`/`proxy`, not built on the coordinator. Add a boundary test
asserting the gateway server module imports neither the coordinator nor the privileged
loop. Core stays stdlib-only so the gateway remains Windows-native.

### R4 — `/v1/models` aggregation must not leak topology or secrets
Aggregating models across providers is useful but must not expose `key_env` names or
raw `upstream_base` URLs. **Resolution:** `/v1/models` returns agent-facing model ids
+ optional cost metadata (operator-visible; single-user, so cost is fine), via the
**field-allowlist** pattern already used by `show_config` — never key envs or bases.

### R5 — Two config formats (toml + json) would drift
A separate `charon.toml` schema competing with `.charon/*.json` is a maintenance trap.
**Resolution (folded into D6):** one schema, two surfaces. Gateway reads the existing
JSON registry first; `charon.toml` is later sugar that loads to the *same* structures.
Do not invent a parallel model.

### R6 — Failover can mask real errors and burn money
Blindly retrying across paid providers could (a) rack up cost when every provider
402s, or (b) hide a client's own bad request. **Resolution:** only **capacity/gone**
signals trigger failover — `{429, 402, 503}` (exhausted) + `404` (dropped) + a
*verified* silent downgrade. **`400/401/403` are returned immediately**, never failed
over (failing an auth/bad-request to the next provider is both wrong and wasteful).
Bound attempts to pool size. Emit per-attempt **cost** in the failover log so spend is
visible. Reuse `proxy.py`'s existing `_EXHAUSTION_STATUSES`/`_DROP_STATUSES` — extend,
don't fork. (402 = "out of credit" is a legitimate pool-failover trigger, but the
operator must *see* it — D3.)

### R7 — Shared observer state means different lifetimes per mode
`GatewayProxy._exhausted` is process-global. In the **orchestrator** (one run) an
exhausted entry is excluded **permanently for that run** — correct. In the **gateway**
(long-lived, many independent client requests) a provider 429'd once must NOT be
excluded forever. **Resolution:** gateway mode uses a **cooldown-aware** exhausted map
(expiry from `Retry-After`/backoff, R2); orchestrator keeps per-run permanent
exclusion. Same classifier, **deliberately different retention** — called out so it is
designed, not stumbled into.

### R8 — A non-loopback, key-holding proxy is a real exposure
Bound to `0.0.0.0`, the gateway holds **all** provider keys and serves anyone with the
token — a single leaked token = someone else's bill. **Resolution:** reuse the
loopback guard (refuse non-loopback without a token); **document** that the token is
the only thing between a LAN attacker and your keys/credit, and recommend
loopback + SSH tunnel for remote use. State the single-user threat model explicitly in
README.

### R9 — The existing console is FastAPI; the gateway is stdlib — pick one for `.exe`
`proxy_server.py` (gateway) is pure stdlib; `service/app.py` (the read-only dashboard)
is **FastAPI**. For a lean Windows `.exe` and a zero-web-framework-attack-surface
privileged gateway, the P4 console should ride on the gateway's **own stdlib
`http.server`**, not FastAPI. **Resolution (operator-confirmed 2026-06-26 — ship BOTH):** build the
gateway console on stdlib (server-rendered + a tiny poll/SSE endpoint, mirroring the
existing self-contained-HTML approach) so the `.exe` bundles no web framework; AND
keep the FastAPI `service/app.py` as the richer orchestrator/server-side dashboard.
They target different deployments (lean Windows `.exe` vs full server), so shipping
both is low marginal cost — the stdlib console is needed for the `.exe` regardless,
and the FastAPI dashboard already exists. No single-console trade-off forced.

### R10 — gaps surfaced by independent adversarial review (must fix in P2)
A second, independent reviewer pressure-tested R1–R9 against the code and found three
real correctness hazards the self-review missed. They are design constraints on P2:

- **R10a — cost double-counting on failed-over attempts.** `GatewayProxy.observe`
  folds `usage` into cumulative spend whenever a 200 carries usage
  (`proxy.py:135,160-166`), *regardless of `obs.failover`*. A silent-downgrade is a
  200-with-usage that we discard and fail over from — yet its tokens/cost are still
  billed, and the successful retry bills again. **Fix:** `observe()` must not fold
  usage for a failed-over attempt (pseudo_success/dropped), or P2 must reconcile it;
  per-attempt cost (D3/R6) must reflect only what was actually served.
- **R10b — per-attempt body must be rebuilt from the original request.**
  `proxy_server.py:115-122` mutates `bj["model"]` to the route's `upstream_model` and
  re-serializes. Each pool provider has a *different* `upstream_model`, so a retry
  loop that reuses the already-mutated body would send provider A's model id to
  provider B. **Fix:** each attempt re-derives the body from the *original* parsed
  request + that provider's route.
- **R10c — exclusion is model-keyed, cooldown is provider-keyed.**
  `proxy.py:159` keys `_exhausted` by **model id**, but a 429/402 is usually
  account/provider-level (R2/R7's cooldown is per-provider). Model-keyed exclusion
  leaves other models on the same exhausted provider selectable → repeated 429s.
  **Fix:** state whether the provider cooldown replaces or supplements `_exhausted`,
  and key capacity exclusion at the provider level.

Also specify (R1/D3): the **terminal client response when the whole pool is excluded**
(status + headers) — bounded-by-pool-size covers the loop, not the final answer.

- **R10d (P2 review, noted) — exact-match downgrade is too strict.** `classify`
  flags `returned != expected` as a silent downgrade, so a provider that honestly
  answers a *versioned* id (`gpt-4` → `gpt-4-0613`) would trip a spurious failover.
  Low risk while pools are explicit; refine to a prefix/normalized compare in P3+.

(The reviewer also confirmed: concurrency is largely pre-addressed — `proxy.py:110`
`self._lock` already guards all observer state, so a cooldown map inherits it; and the
gateway-imports-no-coordinator boundary (R3) is enforceable by extending the existing
AST check in `tests/test_boundary.py`.)

### Honesty flags (carried forward)
- Real provider quirks (downgrade behavior, header bans, `Retry-After` semantics)
  differ per vendor and are unverifiable without keys. Where a key is absent, prove
  the contract against a **mock upstream** (the repo's established pattern in
  `tests/test_proxy_server.py`) and mark the live behavior **unproven** until a real
  key exercises it. Never present a mock as a live result.
- In-request failover across *paid* providers is real money; the cost-visibility log
  (D3/R6) is a correctness requirement, not a nicety.

---

## Build sequence (P0 → P6) — reconciled

- **P0 (this ADR)** — gateway-first decisions + adversarial review. *Pause for operator
  confirmation before mass implementation.*
- **P1** — `charon gateway` standalone command; `/v1/chat/completions` (stream +
  non-stream) and aggregated `/v1/models` on `GatewayProxyServer`; config from the
  registry; loopback default + optional token. (Open Q: console framework — R9.)
- **P2** — Transparent in-request failover state machine (R1/R2/R6/R7);
  `X-Charon-Provider` / `X-Charon-Failovers` headers; JSONL failover log.
- **P3** — Provider registry + presets (OpenRouter, NanoGPT, ZAI, local) with quirks;
  editable cost-rank.
- **P4** — Web console: live request stream, per-provider usage/cost/failover/health;
  loopback + token-gated.
- **P5** — Windows `.exe` (PyInstaller) + `charon.toml` + first-run helper; separate
  `windows-latest` workflow; Linux CI untouched.
- **P6** — Orchestrator as documented opt-in on the shared core; README reframed
  gateway-first.

Each phase ends **green** (pytest, ruff, mypy `src/charon`, `check_boundary.py`,
`check_version.py`) + committed + a REVIEW-LOG entry.

## Resolved with the operator (2026-06-26) — P1 unblocked
1. **Console (R9): ship BOTH** — a stdlib console on the gateway (for the lean `.exe`)
   *and* the existing FastAPI dashboard (richer server view). Low marginal cost.
2. **Config (D6/R5): add `charon.toml`** as a first-class gateway config surface
   (`tomllib`, stdlib), sharing ONE schema with `.charon/*.json` (no parallel model).
   Gateway may still read `.charon/*.json` directly to de-risk early P1.
3. **Bind (D5/R8): confirmed** — loopback (`127.0.0.1`) by default; a non-loopback bind
   requires explicit opt-in *and* a bearer token, refusing to start exposed without
   one (the gateway holds provider keys; an exposed untokened bind = open credit).
