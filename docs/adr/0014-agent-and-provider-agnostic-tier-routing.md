# ADR-0014 — Agent- and provider-agnostic tier routing in the work-engine

> **Parked / subordinate to ADR-0017 (2026-07-19).** Relates-to: ADR-0017. The work-engine this tier-routing rides on is **deferred** per ADR-0017, and its provider plumbing is to be **adopted (LiteLLM)** rather than hand-rolled. The decisions below stand but are subordinate to 0017; treat as post-MVP.

Status: **Proposed** (2026-06-27). Builds on ADR-0005 (gateway-first; the
`vid→pool→provider` failover core), ADR-0004 (roles/pools/frontend), ADR-0010
(native engine substrate; D003 ACP workers, D005 deferred `WorkerBackend` port),
ADR-0007 (parallel engine; routing is a decision, not a static list). Touches the
register at **D017** (engine consumes the gateway's existing failover for tier
selection), **D018** (a thin `AgentLaunch` renderer seam keeps the engine
product-neutral; ship the opencode renderer only), **D019** (tier vid is resolved
**per-dispatch** so multi-tier is additive, not a rewrite). Honors D001
(gateway-first), D002/D003 (engine owns ACP workers in-tree), D011 (operator
decisions re-confirmed, not silently reconciled).

## Context

The engine pins the agent's model at launch and then throws away the routing
signal it was given:

- **Pinned at launch.** Both proxy-ACP launch paths bake a single concrete model
  into an opencode-specific `OPENCODE_CONFIG_CONTENT` JSON blob
  (`api.py:247-291` `_split_model`/`_acp_for_proxy`/`_pool_routes`,
  `api.py:316-350` `_start_proxy_acp`; the blob is written at `api.py:275` and
  `:347`). The agent is told exactly one `provider/model`; there is no tier
  indirection and the engine, not the gateway, has chosen the provider.
- **The tier is ignored.** `AcpBackend.dispatch` takes a `tier` parameter
  (`acp.py:141`) and never reads it — the body (`acp.py:146-171`) initializes a
  session and prompts with `unit.goal`, tier-blind. Upstream, `StaticRouter.route`
  returns `candidates[0]` (`router.py:84`): it maps a task-class to a `Tier` but
  picks the backend without consulting that tier.

Two prior attempts failed and bound the shape of the fix:
1. An inert `ANTHROPIC_MODEL` env var — opencode never read it; nothing routed.
2. Hardcoding the tier vid into opencode's config — this would route, but it
   **couples the engine to opencode's config schema**, violating the modularity
   constraint (D001/D003: the engine drives *any* ACP agent; the gateway is the
   provider-neutral layer).

The gateway **already** solves provider-agnostic, cost-ranked failover for a
*virtual id*: `GatewayProxyServer(pools={vid:[routes]}, model_ids=[vid])` resolves
`chain_for(vid)` to a cost-ranked provider chain and fails over transparently
(`proxy_server.py:620-621` kwargs, `:677-686` `chain_for`/`order_by_cooldown`).
The engine should **consume that**, not reinvent a parallel selection path.

## Decisions

### D1 — The engine routes a tier by building the per-run proxy with a tier-vid pool
For a dispatch at tier `T`, the engine resolves a **tier vid** and constructs the
per-run `GatewayProxyServer` with `pools={tier_vid: [...]}` and
`model_ids=[tier_vid]` (`proxy_server.py:620-621`). The agent's *requested model
id is the tier vid*; the gateway resolves vid→pool→provider and fails over exactly
as it does for any external client. The engine performs **no** provider selection
of its own — selection is the gateway's job, reached through its existing,
already-tested path.

### D2 — Cost ordering reuses `gateway._build_routes_and_pools`, never `_pool_routes`
The pool handed to the per-run server is built with
`gateway._build_routes_and_pools` (`gateway.py:77`), which orders each chain
**free-first → cheapest-first** from the registry's `free`/`cost_rank` metadata
(`gateway.py:92-99`). We do **not** use `api.py:_pool_routes` (`:280-291`): it
emits an *unsorted* dict keyed by native model id and has no cost ranking — using
it would silently drop free-first ordering. One ordering authority, shared with
the live gateway.

### D3 — A thin `AgentLaunch` renderer seam keeps the engine product-neutral
Introduce `ports/agent_launch.py` defining an `AgentLaunch` (the rendered launch
contract: argv, passthrough env, the requested model id) and a `render(...)` seam.
The existing opencode blob moves *behind* the seam as **the one shipped renderer**
(`OpencodeRenderer`). The engine asks the seam to render a launch for `(acp_cmd,
proxy_url, requested_model=tier_vid)` and never names opencode itself. This is the
honest minimum of D005's deferred `WorkerBackend` port — a launch *renderer*, not
a worker abstraction — earned now because a second routing mechanism would
otherwise leak opencode's config schema into the engine.

### D4 — Every renderer forces `include_keys=False`; the proxy holds the key
The renderer's passthrough env is built with `_acp_passthrough_env(include_keys=
False)` (`api.py:242-244`) — no real provider key reaches the agent; the per-run
proxy injects it. This is already true of both proxy paths (`api.py:274`,
`:346`); the seam makes it a renderer **invariant**, not a per-call choice, so a
future renderer cannot regress it.

### D5 — Tier vid is resolved PER-DISPATCH; backend-selection-by-tier is the named extension point
`AcpBackend.dispatch` already receives `tier` (`acp.py:141`). The tier→vid
resolution happens **on each dispatch**, not once at run construction, so honoring
the `tier` param is structural from day one. `StaticRouter.route` (`router.py:70`)
is the designated seam for *backend selection by tier* (today it returns
`candidates[0]`, `router.py:84`). Phase A ships a single warm backend per run but
keys its pool by the resolved tier vid; Phase B (D6) adds a tier→backend map
without reworking A. Multi-tier-ready is a hard requirement (operator), met by
construction, not by a later refactor.

### D6 — Per-stage agent lifecycle is a separate, purely-additive phase (Ticket B)
A real multi-tier run wants one warm agent *per tier* (or relaunch-on-tier-change)
and a router that selects the backend by the dispatch's tier. Because A already
(a) resolves the vid per-dispatch and (b) keys the proxy pool by tier vid, B adds
only: a `{tier: backend}` warm map (honoring D010 warm-pool default) and a
`router.route` body that reads `tier`. No A-era code is rewritten. Deferred to a
follow-up ticket.

## Consequences

- **Provider-agnostic routing with zero new selection logic.** The engine inherits
  free-first/cost-ranked ordering, per-provider cooldown, downgrade detection and
  the failover event log from the live gateway path — the most-tested code in the
  repo (`tests/test_gateway_failover.py`).
- **The engine stays product-neutral.** Opencode's config schema lives behind one
  renderer; swapping or adding an agent is a renderer, not an engine change.
- **The `select_live_entry` contract must be re-homed, not dropped.** Retiring the
  engine-side pool mode (`api.py:166` `select_live_entry`) removes the clean
  "pool exhausted" early-return (`api.py:168-174`, returning `status: "exhausted"`
  + the dry-pool note) **and** the `failover_note` skipped-model list
  (`api.py:175-177`). These are a load-bearing API contract. Ticket A **must**
  re-home them from the gateway's own observability: the per-run server's
  `status_snapshot()` (`proxy_server.py:738`) and `failover_events`/
  `recent_failovers` (`proxy_server.py:651`, `:727`) already carry the
  skipped-provider list, and a whole-chain-exhausted dispatch surfaces as a
  terminal 502 / `EXHAUSTED` outcome (`proxy_server.py:489-492`, mapped at
  `acp.py:162-163`). Ticket A translates those into the same
  `{status:"exhausted", note:…}` / `failover` result keys the old path emitted,
  so no consumer of the run-result shape regresses.
- **Coupling inventory is broader than three functions.** The opencode coupling to
  relocate behind the seam is: `_split_model` (`api.py:247-255`), `_acp_for_proxy`
  (`:258-277`), `_pool_routes` (`:280-291`), `_start_proxy_acp` (`:316-350`),
  **and** `_ACP_KEY_PASSTHROUGH` (`api.py:239`) plus `_acp_passthrough_env`
  (`api.py:242-244`, called at `:372-373`). The two passthrough symbols are part
  of the seam's env contract (D4), not incidental.
- **Privileged core stays stdlib-only / install footprint untouched** (ADR-0005 R3,
  ADR-0007 D11): the seam adds no dependency; it reshapes how the existing blob is
  produced.

## Modularity framing (honest)

Two different layers are agnostic in two different ways, and this ADR does not
overclaim:
- **The gateway is agnostic for ANY client.** A Windows GUI app or a terminal agent
  points itself at the gateway and asks for a *tier vid*; the gateway resolves the
  provider. The engine does **not** launch GUI apps and makes no claim to.
- **The engine is agnostic only for ACP terminal agents, behind the renderer seam.**
  It drives ACP agents and renders their launch via `ports/agent_launch.py`. Today
  exactly one renderer ships (opencode). Calling the engine "agent-agnostic" is
  true only at the seam boundary — the breadth is one renderer until a second is
  proven.

## Risks

- **Do not ship speculative renderers.** Only the opencode renderer ships. A
  generic/`claude-code` renderer is **not** written on spec; any additional
  renderer is gated on a live `charon doctor` probe that confirms that agent
  actually honors a proxy `baseURL` + tier-vid model id. An unprobed renderer is a
  guess, and a guessed renderer that silently fails routes nothing (the
  `ANTHROPIC_MODEL` failure mode again).
- **Vid namespace collision.** A tier vid must not collide with a concrete model id
  in the same registry, or `route_for`/`chain_for` could resolve the wrong chain.
  Ticket A validates the tier vid is pool-keyed (`model in self.pools`,
  `proxy_server.py:684`) and distinct from any single route.
- **Contract drift.** If the re-homed exhausted/failover keys diverge from the old
  strings, downstream readers (dashboard, ledger summaries) break silently — the
  test contract pins them.
- **Single-renderer monoculture.** Until a second renderer is probed, the engine's
  "agnosticism" is unexercised; treat it as a design seam, not a tested guarantee.

See `docs/review-log/E11.md` for the 3-lens adversarial reconciliation
(coupling-inventory completeness · contract-re-homing · over-claimed modularity)
that gates this build.
