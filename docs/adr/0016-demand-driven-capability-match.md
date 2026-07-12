# ADR-0016 — Demand-driven capability match (zero static rank)

Status: **Proposed** (2026-07-12). Supersedes the hand-assigned `cost_rank`
integer selection rule in ADR-0004 (D4/R2) and the pool-ordering half of
ADR-0004's `_build_routes_and_pools`. Builds on and **finishes/unifies/deploys**
already-built work: ADR-0004 (routing gateway / pools / failover chain), the
v0.5.0 ROUTER wave (cost-rank-AUTO R2/R5, capability-matrix R3, latency-signal
R8, pricing-checker R17), and the parked drain-then-park lifecycle (R11) +
balance-wire (R46). This ADR does **not** design a new engine — it removes the
last hand-typed data from a mechanism that already exists and largely runs.

## Context

The live gateway (self-hosted deployment, image `v0.4.1`) selects the
provider for a requested model by sorting each pool on hand-assigned `cost_rank`
integers in `/data/models.json`. Those integers **rot and are literally wrong**.
Verified this session (`fleet/state/POOL-INVESTIGATION.md`): for `deepseek-v4-pro`
the live order is `-go=5` (opencode-go, DEAD 401) → `-ng=10` (nanogpt, DEAD 429)
→ `-or=50` (openrouter) → `-ds=60` (**deepseek-direct, FUNDED + WORKING + actually
cheapest**) → `-cline=900`. The two cheapest ranks are dead providers and the one
funded working provider is ranked 4th, so under load the chain burns its budget on
dead hops and reports "pool too thin / all_providers_exhausted". A global
`fallback.json = {"providers":["opencode-go"]}` appends that same dead provider to
the end of *every* chain.

The root cause is not the data being stale *today* — it is that the data is
**hand-typed once and never re-derived**. Any fix that re-types the integers
(even correctly) rots again the next time a provider changes price, runs out of
credit, or resets a quota. The operator's directive: replace static rank with an
**active, mechanized, demand-driven match** and ban hand-typed rank integers
outright.

### The operator's fatigue (this ADR must answer it)

The operator is explicitly tired of "new methods that also rot." This ADR is only
worth adopting if every selection input is either (a) pulled live per request, or
(b) sourced + refreshed on a TTL with drift detection, or (c) reactive to a real
upstream signal — **never** a human-typed value that decays silently. The
"Adversarial stress-test" section below is the load-bearing part of this document:
it names every place full-live is impossible and shows the anti-rot discipline
that keeps the degraded path honest.

## Decision

Replace static-rank pool ordering with a **demand-driven capability match**:

1. **A request ANNOUNCES the model it needs** — the OpenAI-compatible `model`
   field, already the routing key (`forwarder.forward_with_failover` →
   `srv.chain_for(requested)`).
2. **Providers that can serve that model ANNOUNCE their terms** — price (live from
   `/models` where exposed; sourced+TTL where not), remaining capacity (only where
   a balance/quota endpoint exists), and health (reactive exhaustion signal +
   cooldown + latency).
3. **The router MATCHES the need to the cheapest HEALTHY capable provider**, and
   **rolls to the next-cheapest on exhaustion** — this is `order_pool_by_live_cost`
   → `order_by_cooldown` → the failover loop, all already built.
4. **If NO provider can serve it → FAIL LOUD**, surfaced to the caller with which
   model, which providers were tried, and why each failed (the fail-loud contract
   below — a hardening of the existing `all_providers_exhausted` synthesis).
5. **Zero static rank integers.** `cost_rank` as a hand-typed field is deleted from
   the config schema; ordering is derived from live/sourced price only. The one
   surviving escape hatch (`cost_class`, the funding-class axis a scalar can't
   express) stays, because it is a *category* the operator sets deliberately, not a
   decaying magnitude — but even it is validated against the reactive signal.

### Selection order (the match, precisely)

For a requested model id, the ordered candidate chain is computed per request as:

```
chain = chain_for(model)                         # who CAN serve it (pool/route)
      → filter: capability_matrix.supports(...)  # who can serve THIS KIND of request (R3)
      → filter: max_context / max_concurrency     # who can admit THIS request (R7)
      → filter: parked(provider)                  # drain-then-park removes drained (R11, NEW-wire)
      → order:  order_pool_by_live_cost(...)      # cheapest first by LIVE metered $ (R2/R5)
      → order:  order_by_cooldown(...)            # healthy-first, cooled-last (R7/R8)
then: try in order, roll on exhaustion signal, PARK the drained provider,
      FAIL LOUD if the chain empties.
```

Every stage above **already exists in the repo**; this ADR's build work is to
(a) delete the static rank the ordering currently still leans on, (b) add the two
missing live inputs (price-pull, park-wire), (c) harden the fail-loud terminal, and
(d) **deploy** the v0.5.0 mechanism that is built but not live.

## The live / degraded / sourced matrix

The honest core. Each selection input has a source-of-truth and a refresh rule.
No input is a hand-typed magnitude.

| Input | Best case (LIVE) | Degraded case (SOURCED / REACTIVE) | Anti-rot discipline | Source of truth (code) |
|---|---|---|---|---|
| **PRICE** | Providers exposing per-token price in `/models` (OpenRouter, NanoGPT) → **pull live**, cache to `model_pricing`. Once traffic exists, the **observed** per-(model,provider) cost from the meter overrides even the quoted price. | Providers with no price API (deepseek.com direct, opencode-zen) → a **SOURCED** price in the canonical pricing table (`provider-pricing-limits.tsv`, R17) with a `source_url`, **re-verified on a TTL** by the pricing-checker, never hand-typed into `models.json`. | Pricing-checker (R17) flags any drift > threshold between the canonical source and config as a tracked red + operator alert. Live meter supersedes both once there is traffic. TTL re-pull, not a one-time entry. | `balance.py` poll adapters; `proxy.py all_model_provider_costs`; `routing_policy.order_pool_by_live_cost`; `pricing_limits_checker.py` |
| **CAPACITY** ("how much is left") | Only where a balance/quota endpoint exists: DeepSeek `/user/balance`, OpenRouter `/credits`, NanoGPT `/check-balance` → **predictive** (skip before it 402s). | The common case — **most providers have no balance API** (opencode-zen confirmed none, feat-req anomalyco/opencode#10448 open). → **REACTIVE**: try → 401 CreditsError / 402 / 429 → **PARK + ROLL** (drain-then-park). | Predictive capacity is *advisory only* and drifts (modeled `starting_usd − spend`); it is **never** the authoritative park trigger. The reactive upstream signal is authoritative — it cannot rot because it is the provider's own answer. | `balance.py` (poll + fixed); reactive: `proxy.py _is_billing_error`, `_EXHAUSTION_STATUSES`; park: R11 |
| **HEALTH** | Reactive exhaustion taxonomy, per funding class (verified this session): opencode-zen/-go **401 CreditsError** (prepaid, one shared pool, re-arm = operator top-up only); nanogpt **429** (weekly quota, re-arm = automatic on weekly reset); neuralwatt **tiered** plan + PAYG overage (park only when the *last* pool hits zero). | n/a — health is inherently reactive; there is no "static health." | Park + re-arm is **per funding class**, not one flag (R11 re-arm table). A parked provider stops being retried (kills the churn) but re-arms on its class's real signal — top-up, weekly reset, or overage-exhaustion — so it can never be permanently wrong. | `proxy.py classify` → `forwarder` failover; cooldown `set_cooldown`/`order_by_cooldown`; park/re-arm: R11/R16 |
| **LATENCY** | EWMA per provider label, recorded on every response (`RollingLatency`, R8). | Can't probe every provider per request → **short-TTL cache**, refreshed on each real response and on exhaustion-signal; a slow-provider flag deprioritizes (never removes). | Latency is a *secondary* tiebreak only, never a primary rank, so a stale sample can at worst mis-order two otherwise-equal providers — it can't route to a dead one. Refreshed on every real call = self-healing. | `latency.py RollingLatency`; `proxy_server.order_by_cooldown` `_lat_sort_key` |

**The rule that prevents re-rot:** the *primary* ordering magnitude (price) is
either live-pulled or meter-observed or sourced-with-TTL-drift-detection. The
*category* axis (`cost_class` funding class) is operator-set but is a small
enumerated set validated against the reactive signal. Everything else (capacity,
health, latency) is reactive or self-refreshing. **No selection input is a
hand-typed decaying number.**

## Fail-loud contract

When the capability match cannot serve the requested model — every capable
provider is exhausted, parked, over-context, or unreachable — the gateway returns
a **single terminal, structured** error (never a silent downgrade, never a
misleading relay of one provider's raw error). This hardens the existing
`all_providers_exhausted` synthesis (`forwarder.py:372-393`).

**HTTP:** `503` (transient — chain may recover) or `502` (no route configured at
all). **`Retry-After`** header bounded to `[1, max_cooldown_s]` (soonest chain
member to recover).

**Body (OpenAI-compatible error envelope):**

```json
{
  "error": {
    "message": "no capable provider could serve model 'deepseek-v4-pro'",
    "type": "all_providers_exhausted",
    "requested_model": "deepseek-v4-pro",
    "providers_tried": [
      {"provider": "deepseek",   "status": 401, "reason": "CreditsError: insufficient balance", "class": "prepaid",   "rearm": "operator top-up"},
      {"provider": "nanogpt",    "status": 429, "reason": "weekly quota exhausted",              "class": "free-daily","rearm": "auto @ weekly reset"},
      {"provider": "openrouter", "status": 402, "reason": "payment required",                    "class": "metered",   "rearm": "top-up"}
    ],
    "no_provider_reason": "every capable provider is parked or exhausted",
    "retry_after_s": 42
  }
}
```

**Headers** (already emitted, retained): `X-Charon-Provider`, `X-Charon-Failovers`,
`X-Charon-Failover-Reasons`. **New:** the structured `providers_tried` array
(provider, status, reason, funding class, re-arm condition) so the operator sees
*why each failed* and *when each comes back* without reading logs. The distinction
from a 4xx client/auth error is preserved: a genuine `400/401(bad-key)/403` is
relayed transparently (not retry-worthy), only capacity/exhaustion failures
synthesize the terminal fail-loud.

## Reconciliation with built code

The heart of "this is finishing, not a rewrite." Every row cites file:line.

| Capability | State | Where (file:line) |
|---|---|---|
| Per-model provider failover chain + roll-on-exhaust (H6) | **BUILT + LIVE (v0.4.1)** | `proxy_server.chain_for` (616), `forwarder.forward_with_failover` loop (320-570), `failover.next_entry` (39-52) |
| Exhaustion taxonomy → failover (401 CreditsError / 402 / 429 / 503) | **BUILT + LIVE** | `proxy.py _is_billing_error` (206-211), `_EXHAUSTION_STATUSES` (41), `_EXHAUSTION_BODY_PATTERNS` (48) |
| cost-rank-AUTO: derive rank from per-token price | **BUILT in repo, NOT deployed** (live = v0.4.1) | `routing_policy/cost_rank.derived_cost_rank` (32-56) |
| Live-cost cheapest-first reorder at request time | **BUILT + WIRED in repo, NOT deployed** | `routing_policy.order_pool_by_live_cost` (241-262); called `forwarder.py:291-306` |
| Per-(model,provider) live cost meter (data source for the above) | **BUILT + WIRED** (forwarder passes `provider=route.label`; docstrings claiming "empty/Wave-2-deferred" are STALE) | `proxy.py record` folds cost (478-481), `all_model_provider_costs` (549); fed at `forwarder.py:443-445, 545-546` |
| `record_spend` live per-request price capture | **BUILT + WIRED** (but inert — tracker is None) | `forwarder.py:466-467, 560-561` → `balance.record_spend` (220-249) |
| Latency signal (EWMA, slow-flag, tiebreak) | **BUILT + LIVE** | `latency.py`, `order_by_cooldown` (631-657) |
| Capability matrix (reasoning etc.) + max_context/max_concurrency | **BUILT + WIRED** | `forwarder.py:207-242`, `gateway.py:334` |
| Pricing/limits drift checker (sourced-price TTL verify) | **BUILT** (R17) — detector, not yet a live `/models` puller | `pricing_limits_checker.py check_pricing_limits` (276) |
| **BalanceTracker construction from config** (un-inert record_spend; enable predictive capacity) | **TICKETED — R46-BALANCE-WIRE** (parked behind F29-REGISTRY-SLICE) | target `gateway.py build_server` (~329); `GatewayConfig.balance_tracker=None` (94) |
| **Drain-then-park lifecycle** (park drained provider, re-arm per funding class, sole-leg guard) | **TICKETED — R11 DRAIN-THEN-PARK** (parked) + R16 GRACEFUL-DEGRADE | `fleet/board/DRAIN-THEN-PARK.md.parked`; targets `balance.py`, `gateway.py` |
| **Live price-pull from provider `/models`** (OpenRouter, NanoGPT quoted price → `model_pricing`) | **NEW** | new adapter alongside `balance.py` poll adapters; feeds `order_pool_by_live_cost` |
| **Structured fail-loud `providers_tried` contract** | **NEW** (hardens existing synthesis) | `forwarder.py:372-393` |
| **DELETE static `cost_rank` integers** from schema + `/data/models.json` | **NEW** | `cost_rank.py`, `pools.py PoolEntry.cost_rank`, config schema, `.60` data |

**Six-line summary — BUILT / TICKETED / NEW:**
- **BUILT + LIVE (v0.4.1):** failover chain, roll-on-exhaust, exhaustion taxonomy, latency signal, capability/context/concurrency filters.
- **BUILT in repo, NOT DEPLOYED (v0.5.0 dead tag):** cost-rank-AUTO, live-cost cheapest-first reorder, per-(model,provider) cost meter — the whole demand-driven *price* brain already runs; it just isn't on .60.
- **TICKETED:** R46 (construct BalanceTracker → un-inert record_spend + predictive capacity), R11 (drain-then-park + funding-class re-arm), R16 (auto-recover), R17 (sourced-price TTL drift).
- **NEW (small):** live `/models` price-pull adapter; structured fail-loud `providers_tried`; delete static `cost_rank`.
- The demand-driven design is **~80% built** — the work is deploy + 2 small new pieces + un-inert 2 tickets + delete the rot.
- **Not a from-scratch rewrite.**

## Build decomposition (ordered, collision-aware, E2E)

Sequenced by the shared-god-file chain (`gateway.py` / `balance.py` are the
contention axis) and by "deploy-what-exists first so the operator gets relief
immediately." **P = product repo (charon); D = .60 deploy (operator-gated).**

| # | Ticket | Repo | Owns (contention) | Depends on | Delivers |
|---|---|---|---|---|---|
| **0** | **DEPLOY v0.5.0 cost-rank-AUTO to .60** | D | live `/data/*`, image tag | — | The built live-cost reorder goes live; interim POOL-INVESTIGATION config edits (disable dead providers, drop `opencode-go` fallback) applied same push. **Immediate relief.** Operator-gated (docker). |
| **1** | **F29-REGISTRY-SLICE** (prereq already staged) | P | `gateway.py`, `proxy_server.py` | — | Declarative module registry so R46 registers cleanly. (Pre-existing wave; unblocks the serial chain.) |
| **2** | **R46-BALANCE-WIRE** | P | `gateway.py`, `balance.py` | #1 | `build_server` constructs `BalanceTracker` from provider config → `record_spend` un-inerts; predictive capacity enabled where a balance API exists. |
| **3** | **LIVE-PRICE-PULL** (NEW) | P | new `price_pull.py` (disjoint), reads into `model_pricing` | #0 mechanism | Poll `/models` on OpenRouter/NanoGPT for quoted per-token price on a TTL → feeds `order_pool_by_live_cost` before traffic exists (cold-start ordering without a hand-typed number). Sourced-price providers fall to R17 table. |
| **4** | **R11 DRAIN-THEN-PARK** (+ R16 recover) | P | `balance.py`, `gateway.py` | #2 | Park a provider on its reactive exhaustion signal; re-arm per funding class (top-up / weekly reset / overage); **sole-leg guard** (never park the only remaining leg of a pool). Removes the retry-churn. |
| **5** | **FAIL-LOUD-CONTRACT** (NEW) | P | `forwarder.py` (terminal synth) | — (parallel-safe w/ #3) | Structured `providers_tried` array (provider, status, reason, funding class, re-arm) on the terminal 503; distinct from relayed 4xx. |
| **6** | **DELETE-STATIC-RANK** (NEW) | P | `cost_rank.py`, `pools.py`, config schema | #3, #4 landed & live-verified | Remove hand-typed `cost_rank` from schema + validators + `.60` data; ordering now derives from live/sourced/meter price only. `cost_class` (category) retained. Land LAST so ordering never regresses mid-migration. |
| **7** | **R17 sourced-price TTL** (already built as detector) | P | `pricing_limits_checker.py`, canonical TSV | — | Confirm the sourced-price refresh loop feeds cost-rank; alert on drift. |
| **8** | **DEPLOY R46+R11+pull+fail-loud to .60** | D | image tag, `/data/*` | #2-#6 green | The full demand-driven match goes live; operator-gated. |

**Collision notes:** #2 and #4 both own `balance.py` + `gateway.py` → strictly
serial (#2 before #4, per R46/R11 ds). #3 (new file) and #5 (`forwarder.py`
terminal) are disjoint from that chain → run concurrently. #6 lands only after
#3+#4 are **live-verified**, so the static rank is never removed while anything
still reads it.

### E2E verification (the acceptance)

1. **Happy path — cheapest live healthy wins:** issue a real
   `deepseek-v4-pro` completion at the gateway with a funded DeepSeek key and a
   drained opencode-zen key present. **Assert** `X-Charon-Provider:
   api.deepseek.com` (the funded cheapest), **not** a dead provider; and
   `X-Charon-Failovers` reflects any dead hops skipped/parked (0 after park warms
   up). No static `cost_rank` present in `/data/models.json`.
2. **Roll-on-exhaust:** drain the primary (or point it at a 402 mock); **assert**
   the request rolls to the next-cheapest healthy provider and the drained one is
   **parked** (subsequent requests skip it — no repeated 401 churn in
   `recent_failovers`).
3. **Fail-loud — no provider can serve:** request a model whose entire capable
   chain is exhausted/parked; **assert** HTTP 503, body `type:
   "all_providers_exhausted"`, a populated `providers_tried` array naming each
   provider + status + funding class + re-arm, and a bounded `Retry-After`.
4. **Anti-rot:** flip a price in the R17 canonical source; **assert** the checker
   flags a drift red + alert and the next request re-orders — with **no** human
   editing a rank integer.

## Consequences

**Positive**
- The selection brain is demand-driven and self-refreshing; no hand-typed rank can
  rot the routing again.
- Immediate operator relief from step 0 (deploy what's already built) before any
  new code.
- Failures are legible: the caller sees which providers were tried, why, and when
  they return.
- ~80% reuse — the risk surface is small (2 new files + 2 un-inert tickets +
  1 deletion), not a rewrite.

**Negative / cost**
- Live `/models` price-pull adds a per-TTL network dependency; mitigated by
  cache + fallback to sourced table + meter-observed override.
- Predictive capacity exists for only ~3 providers; everyone else is reactive
  (a first request *will* hit the 401/429 that triggers the park — accepted, it's
  the only truthful signal a provider without a balance API gives).
- Deleting `cost_rank` breaks any external config that set it; mitigated by keeping
  the `cost_class` category and a one-release deprecation warning in the validator.

## Adversarial stress-test (does THIS rot too?)

The operator's standing objection: every "new method" also rots. Walk each input
and name the decay mode + the guard.

1. **"Live price-pull will 500 / rate-limit / lie."** → Price-pull is *advisory
   cold-start ordering only*; the moment real traffic exists, the **meter-observed**
   per-(model,provider) cost overrides the quoted price (`order_pool_by_live_cost`
   already prefers `metered_cost`). A wrong/stale quote self-corrects on the first
   billed response. Pull failure → fall back to sourced table, never to a hand
   integer. **Cannot silently rot** — it's superseded by observation.

2. **"The sourced price table is just hand-typed rank with extra steps."** →
   No: it carries a `source_url` and is **re-verified on a TTL** with drift
   detection (R17), which raises a tracked red + operator alert on any change past
   threshold. A hand `cost_rank` integer has no source, no TTL, no alarm — it rots
   in silence. The difference is the *drift alarm*, and it is mechanized.

3. **"Modeled balance (`starting_usd − spend`) will drift from reality."** →
   Acknowledged and **designed around**: modeled balance is **advisory / predict-
   early only**; the authoritative park trigger is the **reactive upstream signal**
   (401 CreditsError / 429), which is the provider's own truth and cannot drift.
   The one place drift could route wrong (predictively skipping a provider that
   actually has credit) fails *safe* — the sole-leg guard (R11) forbids parking the
   last leg of a pool, so an over-eager predictive park can never strand a request.

4. **"Latency EWMA goes stale for an idle provider."** → Latency is a *secondary
   tiebreak*, never a primary rank; missing/stale data sorts as `+inf` (deprioritized
   but never removed). Worst case it mis-orders two otherwise-equal providers; it can
   never send traffic to a dead one. Refreshed on every real response.

5. **Biggest residual risk (see below) — cold-start + no-price + no-balance
   provider.** A provider that exposes *neither* a price API *nor* a balance API
   *nor* has any traffic yet (e.g. a freshly added opencode-zen) has **no live
   magnitude at all** — only the sourced table (which may be missing) and the
   reactive signal (which only fires *after* a request is spent on it). For that
   provider, first-request ordering is genuinely unknowable and it may be tried out
   of true cost order once, until the meter observes it or the reactive signal parks
   it. This is the irreducible floor of "demand-driven": you cannot know a
   provider's marginal cost before you either look it up or spend on it. The guard
   is that this is **self-correcting within one request** (meter observes it) and
   **bounded** (sourced table + funding-class default `cost_class` gives a coarse
   initial bucket), but it is the one place the design still leans on an operator-
   supplied *category* (`cost_class`) rather than a measured number.

## Single biggest risk

**Cold-start ordering for a provider with no price API, no balance API, and no
traffic yet is fundamentally unknowable — the design cannot fully eliminate an
operator-supplied input there; it can only shrink it from a rot-prone *magnitude*
(`cost_rank` integer) to a coarse, enumerated *category* (`cost_class` funding
class) that is validated against the reactive signal.** Everything else is live,
meter-observed, sourced-with-TTL, or reactive. If the operator expects *zero*
human input including the funding-class category, that last mile is not achievable
without a universal price/balance API that providers do not offer — and pretending
otherwise (by hand-typing a cost number) is exactly the rot this ADR removes. The
honest answer is: **zero static rank, yes; zero static category, no** — and the
category is drift-checked, not silently decaying.

## Pointers

- ADR: `docs/adr/0016-demand-driven-capability-match.md` (this file).
- Built mechanism: `routing_policy/__init__.py:102-262`, `proxy_server.py:616-740`,
  `forwarder.py:167-570`, `proxy.py:206-560`, `balance.py`, `latency.py`.
- Tickets: `fleet/board/R46-BALANCE-WIRE.md`, `DRAIN-THEN-PARK.md.parked`,
  `COST-RANK-AUTO.md.parked`, `PRICING-LIMITS-CHECKER.md`,
  `fleet/state/EXHAUSTION-PARK-TICKETS.md`.
- Live-config facts + interim edits: `fleet/state/POOL-INVESTIGATION.md`.
- Deploy-drift caution: memory `charon-deploy-drift-lessons` (config/secrets/state
  live on the mounted `/data` volume on .60, not the image).

