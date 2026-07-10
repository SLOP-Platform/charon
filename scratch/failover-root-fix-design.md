# Charon gateway failover — root-fix design (DESIGN/SPEC ONLY, no code)

Date: 2026-07-08 · Author: design sub-session · Bug source: `scratch/gpt54-exhausted-diagnosis.md`
Product source of record: `/home/stack/code/charon/src/charon/`
Status: SPEC. Build is a separate operator-opened droid tab (ticket `PROXY-FAILOVER-FIX.md.parked`).

## 0. Problem recap (confirmed, from the live diagnosis)
A raw OpenAI client asked the gateway proxy for `gpt-5.4`. That model's pool has exactly
two members (`nanogpt`, `openrouter`); both returned HTTP 402 (out of balance). The
gateway synthesized `503 all_providers_exhausted` **with no `Retry-After`**, so the client
fell back to its own exponential backoff (~8h at attempt #15). Two real defects:
1. No `Retry-After` on the terminal 503 → gateway forfeits retry-cadence control.
2. No cross-model / cross-tier substitution on the **proxy serve path** — `chain_for()`
   returns only the requested model's own pool; cross-model failover exists only on the
   engine/coordinator path (`failover.py`/`router.py`/`handoff.py`), which a raw client
   never touches.

## 1. Ground-truth code map (verified this session)

| Concern | File · anchor | Fact |
|---|---|---|
| Terminal 503 synth | `proxy_server.py:815-835` | `if failovers:` branch appends last member, calls `_send_resp_headers(503,…)`, writes `all_providers_exhausted`. |
| Header emitter | `proxy_server.py:483-500` `_send_resp_headers` | Sends status/Content-Type/`X-Charon-*`/cookie only. **Never sets `Retry-After`.** |
| Single-upstream relay | `proxy_server.py:836-841` | Relays raw upstream non-200 (incl. 402/429) as-is — also with no bounded `Retry-After`. |
| Cooldown set | `proxy_server.py:1144-1155` `set_cooldown` | On `obs.exhausted`, cools provider by `min(retry_after or default, max_cooldown_s)`; keyed by `upstream_base`. `max_cooldown_s=120`, `default_cooldown` present. |
| Cooldown ordering | `proxy_server.py:1130-1142` `order_by_cooldown` | Buckets chain into `fresh` + `cooled` (cooled sorted soonest-recovery first). The natural choke point for demotion. |
| Chain resolution | `proxy_server.py:1115-1128` `chain_for` | `if model in self.pools: return list(self.pools[model])`; else policy/single route. **No tier siblings.** |
| Serve loop | `proxy_server.py:711` (`chain=srv.chain_for(requested)`), `760-841` | Iterates `order_by_cooldown(chain)`; substitutes nothing. |
| Downgrade signal | `_send_resp_headers(..., downgrade=True)` → `X-Charon-Downgrade` | Header already exists ("served a different model than requested"); today only for silent-downgrade detection. |
| Tier→pool compile | `gateway.py:167-180,233-234` `_tier_pools` | `tiers.json` members compiled by the SAME `_build_routes_and_pools` (free-first→cost_rank) and merged into `pools` as tier vids (`low/med/high`). Explicit pool vid wins on name collision. |
| Tier store | `config.py:345-365` `load_tiers` | Returns `{order, members{tier→[model ids]}, aliases{name→tier}}`; legacy default if absent. |
| Global fallback | `gateway.py:236-258` | `load_fallback_providers()` names are appended to the END of **every** pool chain (and single routes) — a funds-independent backstop mechanism that ALREADY EXISTS. |
| Balance tracker | `balance.py` `BalanceTracker` | `remaining/should_drain/is_drained/force_poll`; poll adapters for deepseek/openrouter/nanogpt. **NOT instantiated or consumed anywhere in `gateway.py`/`proxy_server.py`** (grep-confirmed dead in the serve path). |

Two facts materially shape the design:
- **Capability-equivalence already has a home: `tiers.json`.** The gateway already compiles
  tier vids into cheapest-first pool chains. P2 does not invent a capability model — it
  reuses tier membership.
- **The global-fallback mechanism already exists.** P4 is therefore config, not code, and
  would by itself have prevented this exact 503 had a non-balance-gated backstop been listed.

## 2. Component designs

### P1 — Bounded `Retry-After` on 503 (and on 402/429 relays)  ·  Phase 1 · risk LOW · NOT money-path
**Goal:** the GATEWAY owns retry cadence; a transient dual-402 can never become an 8h client stall.

**Mechanism**
1. Add optional param `retry_after: int | None = None` to `_send_resp_headers`
   (`proxy_server.py:483`). When truthy and >0, emit `self.send_header("Retry-After", str(int(retry_after)))`
   before `end_headers()`.
2. Add a small helper on the server, e.g. `retry_after_hint(chain) -> int`:
   compute soonest recovery among the chain's members from `self._cooldown`
   (`min(expiry - now)` over cooled members), fall back to `default_cooldown` when none is
   cooled, and clamp to `[1, max_cooldown_s]`. Note: at the 503 point the just-failed 402
   members were cooled at `proxy_server.py:808-809`, so the hint is normally ≈`default_cooldown`
   — always ≤120s by the existing clamp.
3. At the terminal 503 (`proxy_server.py:826`), pass `retry_after=srv.retry_after_hint(ordered)`.
4. At the single-upstream relay (`proxy_server.py:838`), when `status in (402, 429, 503)`,
   pass `retry_after=min(obs.retry_after or srv.default_cooldown, srv.max_cooldown_s)` so a
   raw upstream `Retry-After: 3420` is re-bounded to ≤120 before reaching the client. Do NOT
   set it on 400/401/403 (client/auth errors — retrying doesn't help).

**Acceptance** (`tests/test_proxy_server.py` or `tests/test_gateway_failover.py`):
- Dual-402 pool → 503 response carries `Retry-After`, integer, `1 ≤ value ≤ 120`.
- Single-upstream 429 whose upstream `Retry-After: 3420` → relayed header clamped to ≤120.
- 400/401/403 relay → NO `Retry-After` header.

**Blast radius:** header-only; no routing/spend change. Sole behavioral effect: a
`Retry-After`-respecting client now retries on the gateway's cadence instead of its runaway
exponential — the intended fix. No money-path.

### P2 — Cross-model / tier substitution on the proxy serve path  ·  Phase 2 · risk HIGH (money-path) · GATED
**Goal:** when the requested model's own pool is fully exhausted, serve from a capability-equivalent
sibling before returning 503 — without silently violating the "client asked for model X" contract.

**Capability-equivalence source:** `tiers.json` membership. Build a reverse index
`model_tier: dict[model_id → tier]` at config-compile time in `gateway.py` from
`load_tiers()["members"]` (and expose it on the server next to `model_meta`). The tier's own
pool chain (`pools[tier]`) is already compiled cheapest-first by the SAME
`_build_routes_and_pools`, so no ordering logic is duplicated.

**Mechanism (preferred — extend the chain, keep the serve loop simple):**
Add `substitute_chain_for(model) -> list[UpstreamRoute]` (or extend `chain_for`) that returns
`own_pool + [tier-sibling routes not already in own_pool]`, where the tier is
`model_tier.get(model)`. The existing serve loop then naturally continues into substitutes and
only synthesizes the 503 when the WHOLE extended chain is exhausted — reusing
`order_by_cooldown` and the existing per-route `upstream_model` substitution (the loop already
sets `bj["model"]=route.upstream_model` and `expected=route.upstream_model or requested`).

**Reuse (not duplication):** this productizes the engine semantic ("re-run the ranked router
with exhausted keys excluded" — `router.route_pool` / `handoff.choose_next_backend`) using the
gateway's already-ranked tier pool. The gateway and engine keep separate data models
(`UpstreamRoute` vs `PoolEntry`), so the reuse is the ORDERING+EXCLUSION semantic, sourced from
the shared `_build_routes_and_pools` compiler — not a literal import of the engine functions
(which would drag `pools.json`/`StaticRouter` state the gateway doesn't have).

**Least-surprise contract (the design-sensitive part — see UNVERIFIED):**
- **Opt-in, default OFF.** Gate the entire behavior behind a gateway toggle mirroring
  `failover_on_downgrade` (a `gateway.json` flag, e.g. `cross_model_failover`). Default OFF ⇒
  today's behavior is byte-identical ⇒ the money-path change never activates without explicit
  operator consent.
- **Always announce.** When a substitute (upstream_model ≠ requested) serves 200, set
  `downgrade=True` so `X-Charon-Downgrade` names the substitution. A deliberate substitution
  must NOT be misclassified as a *silent-downgrade pseudo-success* (which would wrongly trigger
  `failover_on_downgrade` failover) — flag substitute routes so the 200 path emits the header
  but does not treat them as pseudo-success.
- **Bounded direction.** Same-tier siblings ONLY (capability + rough cost parity). Never
  auto-substitute UP into a costlier tier. `cost_class:"premium"` models are already excluded
  from pool chains (`gateway.py:144-155 _is_premium`), so a substitute is never premium unless
  the operator built a premium-only pool.
- **Respect the spend cap.** Re-estimate against the substitute model's pricing under the
  existing `spend_limiter` before committing the substitute attempt.

**Acceptance** (`tests/test_gateway_failover.py` + `tests/test_gateway_tiers.py`):
- Toggle OFF (default): dual-402 own-pool → 503 exactly as today (no substitution). Regression guard.
- Toggle ON: `gpt-5.4` in tier `med`; own pool dual-402; a live `med` sibling exists → request
  is served by the sibling, response carries `X-Charon-Downgrade` naming the served model, 200.
- Toggle ON but no live sibling in the tier → still 503 (+ P1 `Retry-After`).
- Substitute never crosses into a higher tier / a premium model.

**Blast radius (MONEY-PATH — highest):** substitution routes spend to a provider/model the
client did not name. Mitigations layered above: default-OFF opt-in, same-tier-only, premium
gating, spend-cap re-check, and (once P3 lands) drained-provider demotion so a substitute is
not itself a dry backend. A wrong tier reverse-index (model mapped to the wrong tier) would
substitute a mis-capable model — acceptance must assert the reverse index against `tiers.json`.

### P3 — Balance-aware proactive demotion  ·  risk LOW-MED · complements P2
**Goal:** demote a 402/out-of-balance member BEFORE it is tried, so a dry provider is not
attempted first (and, under P2, is not chosen as a substitute).

**Reality check:** `BalanceTracker` is fully implemented but **not wired in** — nothing in
`gateway.py`/`proxy_server.py` constructs or calls it. P3 is therefore two steps:
1. **Instantiate + wire.** Build a `BalanceTracker` from provider config in `gateway.py`
   (`load_config`), pass it onto `GatewayProxyServer` (new `balance_tracker` field).
2. **Demote at the choke point.** In `order_by_cooldown` (`proxy_server.py:1130`), add a third
   bucket AFTER `cooled`: routes whose provider `balance_tracker.is_drained(route.label)` is
   True go last (or are filtered out when a non-drained member exists). Fail-safe: `is_drained`
   already returns False on `remaining() is None` (unreachable/unknown poll) → an unknown
   balance is treated as NOT drained, so a poll failure never sidelines a live provider.
3. **Refresh cadence (design note):** `remaining()` for poll providers hits the network
   synchronously; do NOT poll inline per request. Add a short-TTL cache / periodic refresh
   (e.g. poll on cooldown-expiry or a lightweight background tick) so demotion uses recent
   balance without adding request latency. Optionally, on a confirmed drained poll, proactively
   `set_cooldown` the provider so it is skipped fleet-wide until balance returns.

**Acceptance** (`tests/test_balance.py` + a serve-path test): a provider configured drained
(`is_drained True`) is ordered last / skipped; an unconfigured or unreachable-poll provider is
never demoted (fail-safe).

**Blast radius:** REDUCES wasted spend attempts (money-path-positive). Only risk is a
false-drained reading sidelining a live provider — bounded by the fail-safe (unknown ⇒ not
drained) and by keeping drained providers as a LAST bucket rather than dropping them entirely.

### P4 — Pool-widening guidance  ·  DESIGN NOTE (config, not code)
2-member balance-gated pools (both paid) share ONE failure mode: funds. Recommendations,
strongest-lever-first:
- **Populate `fallback_providers`** (`config.load_fallback_providers`; already appended to
  every pool at `gateway.py:236-258`) with a **non-balance-gated backstop** (a free-tier or
  fixed-quota HF-/opencode-zen-`-go`-served model). This alone would have prevented THIS 503:
  every pool, including `gpt-5.4`, gains a funds-independent last resort automatically — zero
  new code. Caveat: the backstop must be capability-adequate; a degraded serve still beats an
  8h stall, but pick a reasonable general model.
- Add ≥1 non-balance-gated member directly to thin paid pools where capability matters.
- Backend policy note: prefer prepaid/flat or free-quota members as the pool floor so a pool is
  never composed entirely of metered-balance backends that can go simultaneously dry.

### P5 — Outbound User-Agent fix (Cloudflare 1010 bot-block)  ·  Phase 1 · risk LOW · NOT money-path
**Goal:** stop marking healthy, funded providers dead because their Cloudflare edge 403s a
non-browser User-Agent. Same failure class as the rest of this ticket ("give up on a working
provider"), but on the outbound-header side.

**Finding (from `scratch/six-provider-verify.md`, confirmed live):** `groq`, `cerebras`,
`together` return HTTP **403 "error code: 1010"** — a Cloudflare bot-block on the UA, NOT
auth/credit. A browser-like UA flipped all three to 200.

**Ground-truth outbound-UA map (verified this session):**
| Path | File · anchor | Current UA | Problem |
|---|---|---|---|
| Proxy serve-path upstream request | `proxy_server.py:542-546` | forwards the client UA if present; else `_DEFAULT_UA` | `_DEFAULT_UA` itself is **`"charon-proxy/0.1"`** (`proxy_server.py:71`) — NOT browser-like, so CF-1010 providers 403 on the absent/banned-UA path. And a forwarded non-browser CLIENT UA (e.g. opencode's) is also 403'd by CF. |
| Banned-UA guard | `proxy_server.py:74` `_BANNED_UA_PREFIXES=("python-urllib","python-requests")` | replaces only urllib/requests defaults | Does not help a client UA that is present-but-non-browser. |
| Balance poll — deepseek | `balance.py:41` | `"charon-proxy/0.1"` (hardcoded) | Same non-browser UA → a CF-fronted balance endpoint 403s → poll returns None → **corrupts P3's demotion signal** (unknown reads as not-drained, but a live-but-blocked poll never yields real balance). |
| Balance poll — openrouter | `balance.py:70` | `"charon-proxy/0.1"` | same |
| Balance poll — nanogpt | `balance.py:100` | `"charon-proxy/0.1"` | same |

(Other `urllib`-using modules — `discover.py`, `connect.py`, `providers.py`, `recommend.py`,
`observability.py`, `routing_proxy.py`, `speculative_execution.py` — should be swept for any
outbound provider/probe call that carries a default/non-browser UA and folded onto the same
shared constant; the three above are the confirmed-critical ones.)

**Fix**
- Promote a single shared **browser-like** UA constant (make `proxy_server.py:71 _DEFAULT_UA`
  browser-like, or lift it to a shared module both `proxy_server.py` and `balance.py` import so
  it can't drift) and use it on ALL outbound provider requests + probes/polls. Replace the three
  hardcoded `"charon-proxy/0.1"` strings in `balance.py` with the shared constant.
- Baseline = one global browser-like default. **Per-provider UA override** (a `providers.py`
  preset quirk) is worth it for the residual case where the proxy forwards a client's own
  non-browser UA to a CF-1010 provider — a per-provider "force UA" quirk would override the
  forwarded UA for exactly those providers. Recommend the global default now; per-provider
  override as a fast follow if the forwarded-client-UA path still 403s in the wild.

**Acceptance** (`tests/test_proxy_server.py` + `tests/test_balance.py`):
- An outbound request built for a Cloudflare-fronted provider (groq/cerebras/together) carries a
  browser-like UA (not `python-urllib`, not `charon-proxy/0.1`) → 200, not 403 "1010".
- The balance pollers' built requests carry the shared browser-like UA and reach their endpoints.

**Blast radius:** outbound-only, header-only; no routing/spend logic changes. Positive effect:
currently-blocked funded providers (groq/cerebras/together) become actually reachable.

**Dependency note:** groq/cerebras/together are the funded/free spillover backends the operator
will lean on to widen the fragile 2-member pools (P4). **P5 is a prerequisite for that pool
diversification actually working** — without it, adding those providers to a pool just adds more
spurious-403 "dead" members. P5 also protects P3's demotion signal (unblocks the balance polls).

## 3. Phased sequence
- **Phase 1 (ship alone, no money-path):** P1 `Retry-After` + P5 outbound browser-like UA +
  P4 config guidance (populate a non-balance-gated `fallback_providers` backstop). All three are
  header/config-only, lowest risk, self-contained. Note P5 gates P4's practical value for the
  CF-fronted spillover backends.
- **Phase 2 (gated, money-path, default OFF):** P2 cross-model/tier substitution. Prerequisites:
  P1 shipped; operator decision on the least-surprise contract; `tiers.json` populated in prod.
- **Phase 3:** P3 balance-aware demotion. Independent of P2 but strongly complements it (keeps
  substitution from selecting a dry backend). P2 is SAFE without P3 (a dry substitute simply
  402s and the loop moves on — P3 only makes it efficient).

## 4. Open design questions (need manager/operator)
1. **P2 capability-equivalence source:** confirm `tiers.json` is populated on the live gateway
   (else `_legacy_tiers` gives nothing to substitute into). Is every requestable model a member
   of exactly one tier? Do we need `aliases` resolution, and what about a model in no tier
   (fall through to 503 as today — acceptable?).
2. **P2 least-surprise contract:** default-OFF opt-in vs. always-on-with-`X-Charon-Downgrade`?
   And does the real SLOP/opencode client actually read `X-Charon-Downgrade` (else the
   substitution is invisible to it)?
3. **P2 direction:** same-tier-only, or allow tier-DESCENT (fall to a cheaper tier when the
   same tier is fully dry)? Descent trades capability for availability — operator call.
4. **P3 refresh cadence:** is there an existing background tick to hang balance polling on, or
   does P3 introduce the first poller loop? (No live poller found this session.)
5. **P1 relay scope:** bound `Retry-After` on single-upstream 402/429 relays only, or also
   translate an upstream 503 with a huge `Retry-After`?

## 5. Product-standalone confirmation
Every component touches ONLY product-internal surfaces: `src/charon/proxy_server.py`,
`src/charon/gateway.py`, `src/charon/config.py`, `src/charon/balance.py`, their tests, and the
product's own config stores (`tiers.json`, `fallback_providers`, `gateway.json`). No
fleet/SLOP/rig import, path, or runtime dependency is introduced. Charon continues to ship
standalone. CONFIRMED.
