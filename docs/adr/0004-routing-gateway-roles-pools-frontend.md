# ADR-0004 — Routing/gateway plane: roles, model-pools, cost-first failover, agents & the standalone frontend

- **Status:** Accepted (2026-06-26)
- **Deciders:** Rafael (operator)
- **Relates to:** ADR-0001 (thin orchestrator), ADR-0002 (boundary), ADR-0003 (planes)
- **Grounded by:** five research subsessions (cited in `docs/research/`) — execution/ACP,
  gateways/providers, LangGraph-vs-build, the hermes-spec evaluation, and the
  orq.ai comparison. Adversarially verified; key vendor claims checked, not assumed.

## Context

Tiers 1–4 proved the continuity *contract* (Ledger, fence, handoff, cost
accounting, consensus) against MOCKS. The operator's actual product goal:

- Assign a **role** (coder, reviewer, planner…) an **ordered pool of models**;
  use the primary until its session/rate limit **exhausts**, then fail over to the
  next — **no waiting for resets, no work loss**.
- **Minimize cost:** prefer **free** then **flat-rate** over per-token.
- **Give users choices:** support several providers AND several agents.
- **Standalone, VPS-deployable** app reachable from anywhere; SLOP-embeddable but
  stands alone.

This ADR records the decisions that turn the proven contract into a usable tool.

## Decisions

### D1 — Model-selection locus = Option B (profile-pinned backends)
ACP has **no "set model" request**; a model is the agent's internal config. So a
pool entry = an **ACP agent subprocess pre-pinned to a model** (e.g.
`opencode acp -m openrouter/qwen3-coder`). Charon selects the *profile*, detects
exhaustion, kills + spawns the next, and re-seeds from the Ledger. This **is** the
Tier-2a cross-vendor handoff, with "vendor" = "(agent, model) profile."

### D2 — Supported agents (ACP-drivable + BYO-key)
- **Tier A — native ACP, any provider:** OpenCode (baseline), OpenHands (LiteLLM;
  vet dual-license), Goose, Cline, Qwen Code, Kilo CLI.
- **Tier B — adapter ACP, premium (hard roles):** Codex CLI + gpt-5.5
  (`@agentclientprotocol/codex-acp`), Claude Code + Opus
  (`@zed-industries/claude-code-acp`).
- **Reject:** Cursor (natively ACP but **vendor-locked**, no BYO-key — optional
  only for an existing Cursor subscriber, never default); Crush (no ACP yet +
  **FSL-1.1** restricts commercial competitors); Aider (ACP not shipped).
- **Hermes = reference pattern, not a dependency** (multi-harness client is an
  unmerged PR; ACP-server only ships a Copilot adapter).

### D3 — Supported providers (tiered pool, with safety flags)
Each pool entry carries `cost_tier` (free|flat|ptk|premium) and **`code_safe`**
(defensible for proprietary code: no-train + acceptable jurisdiction). Default
ordering **local → free → flat workhorse → cheap PTK → premium tail**:
- **local:** Ollama (only *unconditionally* code-safe option).
- **free:** Groq (best signaling + Kimi K2 + no-retention), Cerebras (volume; 8K
  ctx cap), OpenRouter `:free` (thin; exclude may-train providers).
- **flat workhorse:** **nano-gpt $8/mo** (cleanest exhaustion contract) ‖
  **OpenCode Go $10/mo** (operator owns; *silently downgrades to free models on
  exhaustion* — see D5).
- **cheap PTK fill:** Fireworks → Together → DeepInfra (FP4 caveat).
- **premium tail:** OpenCode Zen (GPT+Claude, US, zero-retention), OpenRouter-paid
  (pin fp8+; exclude may-train).
- **Quarantine to non-sensitive roles (not code-safe):** Gemini **free** (trains
  on you), ElectronHub, Chutes non-TEE, and PRC-jurisdiction first-parties
  (DeepSeek-direct, Moonshot, Z.ai). **Skip:** ElectronHub, GitHub Models
  (workhorse), Chutes non-TEE for proprietary code.

### D4 — Router = role → ordered pool (free-first, cost-ranked)
Extend `StaticRouter` policy from `task_class→tier` to
`role → [ (backend, model, cost_rank, free?, code_safe?) ]`, sorted free-first
then by cost, walked by the existing **exclude-on-exhaustion** mechanism (H6).
Policy is **data** in `.charon/` (`models.json` registry + `pools.json`), tunable
without redeploy. Native/static; **no network gateway in the loop** (BR-3).

### D5 — Exhaustion detection (the failover trigger)
Authoritative signal is **gateway-side**: HTTP `429`/`402` +
`error_type:rate_limit_exceeded` + honor `Retry-After`; `/api/v1/key` preflight
where available. ACP `usage_update` is **opportunistic** (OpenCode doesn't promise
it). **Pseudo-success guard (mandatory):** verify the response's **`model` field
matches the requested model** and treat a mismatch (silent downgrade) as a
failover trigger, not a success. Wire all of this into `Health.exhausted`.

### D6 — Orchestration = BUILD thin, not LangGraph
A native **DAG-of-stages runner** over `coordinator.run` + the Ledger
(~250–400 LOC, zero deps). **Reject LangGraph/LangSmith:** they drag
`langchain-core`→`langsmith` (egress client) into the privileged loop and their
checkpointer competes with the Ledger as source of truth (INV-1). Adopt the
*patterns* natively: typed stage nodes/edges; **the Ledger IS the checkpointer**
(append graph position); the L2 reviewer gate generalizes to "interrupt before
commit"; an optional OpenTelemetry *exporter* reading the Ledger if external
dashboards are ever wanted (local-first, no egress).

### D7 — Frontend & deploy (the standalone surface)
- **Primary surface = a minimal web dashboard** served by Charon's service:
  providers/keys · agents · role→pools · projects · a **live Ledger run view**
  (progress/cost/handoffs/stage graph). Token-gated, single-operator; the
  **container is the security boundary** (INV-B4). Reachable on a VPS behind a
  reverse proxy + HTTPS + token.
- **Watch-the-agent-work (live diffs/stream) stays CLI/TUI** (operator-accepted) —
  keeps the web UI's scope small.
- Run-launch from the web goes through the **enqueue → in-container worker** path
  (the DTC design-of-record: the exposed web process never runs the privileged
  loop in-process). MVP worker = a separate process in the same container.
- Config lives in a git-tracked `.charon/` dir (no hidden state; Ledger/config
  stay the source of truth).
- **Honest posture:** single-operator-on-your-fenced-box, **not** a hardened
  multi-tenant SaaS; that hardening is a later tier.

### D8 — Cherry-picks from the hermes-spec (adopt as DATA, into existing planes)
- **Role decomposition** (Triage→Plan→Implement→Review→Validate→Close) as
  Ledger/routing metadata feeding D6's DAG runner.
- **Blast-radius taxonomy + human-approval triggers** as conservative **fence
  policy data** that can only *raise* required autonomy/approval, never lower the
  container-gated L2+ floor.
- **Reject:** Hermes-as-orchestrator / curl|bash privileged installs (supply-chain
  gate); provider/credential config pushed into the worker (egress); multi-file
  `*.yaml` progress state (INV-1); judge-panel consensus *as proof* (already
  settled: consensus is additive insurance, not a security boundary).

## Invariants preserved
INV-1 (single Ledger = truth) · zero-third-party-dep privileged loop ·
`SUPPLY-CHAIN.md` gate · **no data egress from the privileged loop** (providers
live behind the gate, never in the loop) · container-gated L2+ (INV-B4) · INV-P0
(add a backend/provider = config, not code).

## Risks / honesty register
- **Live ACP is unproven** until `charon doctor` is green against a real agent on
  `build-host`; everything below ships proven against mocks first.
- **Free cap is global** (OpenRouter): free buys model *diversity*, not quota
  *headroom* — continuity comes from the local→flat→paid ordering.
- **Pseudo-success downgrade** (OpenCode Go, quantizing routers) — D5's
  model-field check is mandatory, not optional.
- **Codex `base_url` bugs** for non-OpenAI providers — `doctor` must probe a real
  completion, not trust config.
- **Gemini/Qwen free tiers sunsetting** in 2026 — don't anchor the free story on
  them.

## Build sequence (MVP, fastest-sane)
1. **Router** — free-first cost-ranked `role→pool` + `models.json`/`pools.json`
   (mock-provable now).
2. **Exhaustion/failover** — 429-shape detection + model-field pseudo-success
   guard wired to `Health` (mock-provable now).
3. **ACP client** — real stdio/JSON-RPC client exercised against a mock ACP agent.
4. **Web dashboard** — minimal control panel + Ledger view (token-gated).
5. **Live grounding** — `charon doctor` on `build-host` (real OpenCode + OpenRouter),
   then a real run, then deploy.

Process note: decisions here were settled by the five research streams; this ADR
gets **one focused review pass** (not a full DTC) before building, to keep the
MVP on a few-days track.

---

## Reconciliation — focused review, 2026-06-24

One adversarial review pass found load-bearing gaps; reconciled as follows (the
D1–D3/D6/D8 framework stands; D4/D5/D7 are amended; build sequence reordered):

### R1 — D5 needs a mechanism: the observing gateway proxy (was CRIT)
Charon drives the agent over ACP and **does not see the raw gateway HTTP
response** — so "verify the returned model matches the request" was unobservable.
**Resolution (new D5.1):** a thin **Charon-owned OpenAI-compatible observing
proxy**. The ACP agent's provider `baseURL` points at the proxy
(`http://127.0.0.1:<port>/v1`); the proxy forwards to the configured upstream
(OpenRouter/nano-gpt/Zen/…) and **observes every response**: HTTP `429`/`402` +
`Retry-After`, the `usage`/cost object, and the returned `model` id. From that it
feeds `Health.exhausted` (authoritative, gateway-side) and the Ledger cost spans,
and raises a **pseudo-success failover** when the returned `model` ≠ requested
(catches OpenCode-Go-style silent downgrades). ~100–150 LOC stdlib
(`http.server` + `urllib`); it carries the upstream API keys, so **credentials
stay in Charon's control plane, never in the worker** (also resolves the
hermes-spec "provider config in the worker = egress" concern). The proxy *is* the
gateway-gate made concrete; providers are reached only through it.

### R2 — D4 schema + router signature (was HIGH, under-specified)
- `.charon/models.json` — registry: `{ "<provider>/<model>": { "cost_tier":
  "free|flat|ptk|premium", "cost_rank": <int>, "code_safe": <bool>,
  "upstream_base": "<url>", "free": <bool> } }`.
- `.charon/pools.json` — `{ "<role>": ["<provider>/<model>", …] }` (author order
  = priority; the router additionally stable-sorts by `(not free, cost_rank)` so
  free-first/cheap-first holds even if hand-order slips).
- `WorkUnit` gains `role: str = "coder"`. `StaticRouter` gains
  `route_pool(role, exclude) -> PoolEntry`; the existing
  `route(task_class, exclude)` path is **unchanged** (backward-compat for the 66
  tests). Proven-red test: load a pool, assert free picked first, flat on
  exhaustion, premium last, all-excluded → clean raise.

### R3 — D7 re-scoped to an honest MVP (was HIGH, scope vs timeline)
MVP frontend = **CLI/TUI for config + launch + watch-the-agent**, plus a thin
**read-only** web view of the Ledger (progress/cost/handoffs) — the "single
pane" observe surface. **Deferred past MVP:** web-based config/pool CRUD, live
streaming, the stage-graph visualization, multi-"project" workspaces. The exposed
web process stays **read-only and must never call `coordinator.run`** (enforced by
`test_boundary.py`, ADR-0002 §2.3); run-launch is enqueue→worker, deferred with
its consumer.

### R4 — D6 (stage DAG runner) deferred past MVP
MVP needs only **role-aware routing** (R2's `role` on the unit), not the full
plan→code→review stage graph. When built: **one Ledger per task** (INV-1); stages
are sequential dispatch units; roles are checkpoint metadata — never one Ledger
per role.

### R5 — Build sequence reordered (de-risk ACP fidelity early)
0. **`charon doctor`** on `build-host` vs real OpenCode+OpenRouter **as soon as the
   VM is reachable** — verify ACP usage/resume fidelity and that the proxy sees
   what it must. Don't serialize the mock work behind it, but treat it as the
   first thing to confirm against reality.
1. Observing proxy (R1) — mock upstream. 2. Free-first router (R2) — mocks.
3. Exhaustion/failover wired proxy→Health + pseudo-success guard — mocks.
4. ACP client protocol shape vs a mock ACP agent. 5. Read-only web Ledger view +
   CLI config. 6. Live integration on `build-host`; then deploy.

### R6 — Conditional/honesty flags (was MED)
- **OpenHands** is **license-gated** (AGPL/dual-license vs Charon MIT) — *not* in
  the default set until a supply-chain audit clears it; OpenCode is the baseline.
- **Gemini/Qwen free** are **sunset-risk** — default free-first prefers **stable
  free (Ollama, Groq)**; Gemini/Qwen marked deprecated-with-date, not defaults.
- **OpenCode-Go / any silent-downgrade gateway** is **autonomy-gated**: usable
  unattended only after the proxy (R1) confirms it detects downgrades — else
  propose-only.
- **Fence policy data (D8)** can only **raise** gates: `Fence` validates on load
  and rejects any entry lowering an op below the container-gated L2+ floor; in
  Mode-B the `.charon/` policy is read-only to the agent loop.
- **D1 handoff** is **checkpoint-boundary only**: exhaustion is acted on *after*
  a dispatch returns (as the code already does), never mid-edit; a mid-dispatch
  crash loses only the post-checkpoint delta (H5), never committed work.

**Verdict adopted:** with R1–R6, ADR-0004 is buildable. R1 (proxy) and R2 (schema)
were design fixes, not just wording; R3/R4 tighten the MVP to hit the timeline.
