# AUDIT — Under-utilized capability in tools we ALREADY depend on

Agent: agen-kolar · 2026-07-24 · READ-ONLY (no edits, no commits, no board changes)

**Question asked:** not "what should we adopt" and not "what do we hand-roll" (that was
`fleet/state/HAND-ROLLED-AUDIT.md`, 2026-07-13). This audit asks the narrower, higher-value
question: **what capability already exists inside a dependency we have installed, that we
hand-roll, plan to build, or hold an open ticket to build?**

**Method.** Installed source read directly from `site-packages` / `--help`, never docs
(docs in this ecosystem were shown to lie today). Every headline claim is either marked
**[EXEC]** — reproduced by running code on this box — or **[READ]** — established from
installed source at `file:line`. Ticket cross-reference from a parallel sweep of all 113
open / 44 parked / 4 decomposed board tickets + `state/ROADMAP.tsv`.

---

## 0. The seed instance, corrected

The audit was seeded with: *`litellm.Router` supports `routing_strategy="cost-based-routing"`;
our wrapper never passes it, so we silently get `simple-shuffle`; a sub measured 300 first-picks
over a 3-leg chain → 97/105/98 uniformly random and concluded LiteLLM "discards Charon's
cheapest-capable ordering".*

The premise (we never pass `routing_strategy`) is correct. **Both conclusions drawn from it are
wrong, and the obvious fix is a trap.**

| Claim | Verdict | Evidence |
|---|---|---|
| We get `simple-shuffle` and ordering is discarded | TRUE, reproduced | [EXEC] 300 picks over 3 legs → `{c:107, a:101, b:92}` |
| Therefore "LiteLLM cannot express Charon's ordering" | **FALSE** | [EXEC] adding `litellm_params["order"]=1,2,3` → `{a:300}`, perfectly deterministic |
| Fix = pass `routing_strategy="cost-based-routing"` | **BREAKS THE GATEWAY** | [EXEC] on our sync call path it raises `RouterRateLimitError: No deployments available` |

`cost-based-routing` is **deliberately unimplemented on the synchronous path**. `router.py:1078-1080`
carries the comment *"`cost-based-routing` is intentionally omitted — `LowestCostLoggingHandler`
only implements `async_get_available_deployments`"*, and `_select_deployment_sync` returns `None`
for it, which the caller converts into `RouterRateLimitError` (`router.py:10793-10801`). Our wrapper
calls `router.completion(...)` — sync (`litellm_router.py:238`). Setting that flag would take the
gateway from *wrongly ordered* to *totally unavailable*.

**The capability we actually want is `order`, not `routing_strategy`** — see finding U1.

---

## 1. Dependency inventory (what we really have)

Interpreter: `/usr/bin/python3` 3.12.3, **279 packages** — this is the real environment.
The venv at `/home/stack/code/charon/.venv` (54 packages) has **no litellm and no httpx**, and
`import charon` fails there (editable metadata points at a deleted `/tmp/.../wt-pr56`). The
system `charon` metadata is also stale (`0.3.1` vs `pyproject` `0.6.0`, path
`/home/stack/code/charon-sr-7` which does not exist) though its `.pth` resolves. *Noted as
environment drift, out of scope for this audit.*

### Declared (`/home/stack/code/charon/pyproject.toml`)

| Extra | Packages | Installed? |
|---|---|---|
| core `dependencies` | *(empty — stdlib-only core)* | n/a |
| `service` | fastapi>=0.110, uvicorn>=0.29, pydantic>=2 | yes |
| `router` | **litellm>=1.93** | yes — **1.93.0** |
| `dev` | pytest>=8, pytest-xdist>=3.8, ruff>=0.4, mypy>=1.9, pip-audit>=2.7, httpx>=0.27 | yes |
| `packaging` | pyinstaller>=6.0 | build-time only |

### External CLIs on PATH and used

| Tool | Version | Where used |
|---|---|---|
| `ruff` | 0.15.16 | `tools/gates.json`, CI |
| `mypy` | (installed) | `tools/gates.json`, CI |
| `pytest` | (installed) | CI, `-n auto` (xdist **is** used — `.github/workflows/ci.yml:55`) |
| `bandit` | (installed) | open ticket BANDIT-PREEXISTING-FINDINGS |
| `gh` | 2.63.2 | fleet scripts throughout |
| `graphify` | uv tool | `fleet/TOOL-INVENTORY.md` §1 |
| `ksf` | `/home/stack/code/keystone/.venv/bin/ksf` | 2 files vendored; CLI not wired |

Frequency-ranked across 443 fleet `.sh`/`.py` + 21 `tools/*.py` + 4 workflows: `git` 924 sites,
`bash` 646, `python3` 302, `charon` 98, `gh` 95, `timeout` 77, `docker` 62, `pytest` 58,
`opencode` 45, `node` 37, `ssh` 26, `curl` 22, `make` 19.

**Referenced but NOT INSTALLED** (a different failure class from under-use — flagged, not audited):
`monit` (**29 call sites**, and open ticket WATCHDOG-RESTART-CMDS-VERIFY is chartered to verify
monit restart commands), `pre-commit` (18 sites), `act` (2). MCP servers: `basic-memory` (global
stdio, uv tool) and `session-bridge` (project stdio) — configured in `~/.claude.json`, no
`.mcp.json` exists.

### The headline number

`litellm.Router.__init__` accepts **52 parameters**. `charon.litellm_plane.litellm_router.make_router`
(`litellm_router.py:363-370`) sets **6**: `model_list`, `cooldown_time`, `allowed_fails`,
`num_retries`, `retry_after`, `set_verbose`. **[EXEC]** The other 46 include `routing_strategy`,
`fallbacks`, `context_window_fallbacks`, `enable_pre_call_checks`, `retry_policy`,
`allowed_fails_policy`, `provider_budget_config`, `optional_pre_call_checks`, `timeout`,
`model_group_alias`, `cache_responses`.

---

## 2. Capability tables

### 2A. LiteLLM 1.93.0 — the large surface

| Capability | Do we hand-roll it? | Open ticket to build it? | Does LiteLLM's version serve? | Evidence |
|---|---|---|---|---|
| **Deterministic chain ordering (`litellm_params["order"]`)** | YES — `routing_policy.order_chain_by_funding_class` + `_preorder_chain`, then the order is **thrown away** by simple-shuffle | ORDER-A-COST-PRIMARY-LAND; GW-CUTOVER-LIVE-WIRE | **FULL** — `order` is a strict priority tier honoured in **both** sync and async paths | [EXEC] 300/300 to leg 1. `utils.py:4475-4508`; sync `router.py:10749`, async `router.py:10346` |
| **Roll-to-next-on-exhaust across order tiers** | YES — forwarder failover loop | GW-CUTOVER-LIVE-WIRE | **FULL** — on failure the Router synthesises an ordered fallback ladder (`order=1` → `2` → `3`) | [READ] `router.py:6035-6075` "ORDER-BASED FALLBACKS" |
| **Context-window pre-filter** | We *write* `model_info.max_input_tokens` (`litellm_router.py:142`) but never enable the filter | CAPABILITY-ENGINE (**parked**): "skip requests exceeding provider max_context" | **FULL**, but **currently inert** — gated on `enable_pre_call_checks` (default `False`) | [EXEC] 4000-tok prompt, 100-tok leg + 200k-tok leg: `False` → picks the 100-tok leg; `True` → picks the 200k leg. `router.py:9891-9909`, gate at `10740` |
| **Model price + context + capability catalog** | `proxy.GatewayProxy._model_pricing` — operator-entered per model | PRICE-REFRESHER ("wrap an existing source, no bespoke scraper"), INVENTORY-TABLE, DISCOVERY-*, ADR0016 | **PARTIAL→FULL for the data-source question** — ships **2954 models / 123 providers**, offline, with `input/output_cost_per_token`, `max_input_tokens`, `supports_function_calling`, `supports_tool_choice`, `supports_vision` | [EXEC] `get_model_info("groq/llama-3.3-70b-versatile")` → ctx 128000, in $5.9e-07, out $7.9e-07, fn True. `model_prices_and_context_window_backup.json` |
| **Per-request cost callback** | Charon computes authoritative cost | LITELLM-COST-FIELD-FIX (**landed**, #190) | **ALREADY ADOPTED, correctly scoped** — verify-only cross-check per ADR-0020 | `litellm_plane/metering.py:1-12` |
| **Cooldown / `allowed_fails` / retry** | forwarder + `proxy_server.set_cooldown` | COOLDOWN-FIX3 (parked) | **ALREADY ADOPTED** (`cooldown_time`, `allowed_fails`, `num_retries`, `retry_after`) | `litellm_router.py:363-370` |
| **Per-exception retry / allowed-fails policy** | NO — single flat `num_retries=1` | — | **FULL** — `RetryPolicy` / `AllowedFailsPolicy` give per-exception counts (RateLimit vs Auth vs Timeout vs ContentPolicy) | [READ] `types/router.py:84-98`, `502-517`. Unused. |
| **Cross-model fallback when a pool is exhausted** | forwarder never-strand fallback | PFF-P2 (parked), FREE-TIER-QUOTA-SPILL (parked) | **FULL** — `fallbacks` / `default_fallbacks` / `context_window_fallbacks` / `content_policy_fallbacks` | [READ] `router.py:294-299`. All four unused. |
| **Session/deployment affinity for warm prompt caches** | `session_affinity.py` (61 lines) | — | **FULL+** — `optional_pre_call_checks=["deployment_affinity"]` + `deployment_affinity_ttl_seconds`; 527-line impl incl. API-key-hash affinity and Responses-API continuity | [READ] `router_utils/pre_call_checks/deployment_affinity_check.py:1-40`; `types/router.py:771-777` |
| **Latency-based ordering** | `latency.py` (61-line EWMA) | — | **PARTIAL** — `latency-based-routing` works sync **and** async, but replaces ordering as *primary*; ours is a *secondary* signal + degrade flag | [READ] `router.py:1093-1101` (sync case present) |
| **Per-deployment / per-provider spend budgets** | `balance.py` BalanceTracker, `spend_limits.py` | FLEET-DEMAND-BROKER (cost ceiling / detain-on-cap) | **PARTIAL — see §4** | [READ] `router_strategy/budget_limiter.py:786-800` |
| **Response caching** | `cache.py` (70 lines, SHA-256 LRU+TTL) | ROADMAP R34 | **PARTIAL** — `InMemoryCache`/`DiskCache` need no Redis and add free disk persistence; but our "exact-hash only, never semantic" invariant must be pinned | [EXEC] cache classes enumerated; `caching/caching.py` |
| **Observability exporters** | `observability.py` (150 lines: JSONL, Prometheus, webhook, Langfuse) | ISSUE-BOARD-SURFACE, 4LOM-CANARY-SERVICE | **PARTIAL** — ships `prometheus.py`, `langfuse/`, `opentelemetry.py`, `datadog/`, `s3.py`, `sqs.py` as `litellm.callbacks`; covers the two backends we hand-wrote | [READ] `litellm/integrations/` (60+ modules) |
| **Tag / metadata routing** | `virtual_keys.py` model allowlist | — | **PARTIAL** — `enable_tag_filtering` + `tag_based_routing.py` filter deployments by request tag | [READ] `router_strategy/tag_based_routing.py` |
| **Streaming** | `litellm_plane/streaming.py` (242 lines) | — | **ALREADY ADOPTED** (relay over Router chunks, keeps our downgrade-head detection) | `litellm_plane/streaming.py:1-12` |
| **Guardrails** | `guardrails.py` (122 lines PII/keyword) | RECONCILE-REVIEW-GATE etc. (different domain) | **NO — see §4** | [READ] `router.py:4286` |
| **Free-tier quota (RPD/RPWK/calendar reset)** | `quota.py` (638 lines) | FT-WIRE-QUOTA, FT-CATALOG-SEED, PRICING-LIMITS-CHECK-SH | **NO — see §4** | [READ] `io_token_rate_limit_check.py:60-62`, `398` |
| **Non-token metering (kWh/energy)** | Charon rule | GATEWAY-NONTOKEN-METERING | **PARTIAL** — has `cost_per_second` (93 models), `cost_per_query` (32), `cost_per_image`, `cost_per_character`; **no energy/kWh** | [EXEC] catalog key census; `cost_calculator.py:188-225` |
| **Time-of-day / surge pricing** | — | PEAK-PRICING-AWARE | **NO** — catalog is a flat price table, no schedule dimension | [EXEC] no time/schedule keys in catalog |
| **Model-signal decay (~30d half-life)** | `capability/` grades | ROUTER-LEDGER-DECAY | **NO** — LiteLLM has no outcome-quality ledger at all | [READ] no equivalent in `router_strategy/` |

### 2B. ruff 0.15.16 — 61 rule families available, 5 enabled

`pyproject.toml:47` → `select = ["E", "F", "I", "B", "UP"]`.

| Capability | Do we hand-roll it? | Ticket? | Serves? | Evidence |
|---|---|---|---|---|
| `S` (flake8-bandit) + `BLE` (blind-except) | YES — `tools/check_security.py` (330 lines): bare/broad except, secrets, eval/exec, `shell=True` | BANDIT-PREEXISTING-FINDINGS; ROADMAP **KS31** | **PARTIAL, but strictly stronger on several classes** | [EXEC] `ruff check --select S,BLE src/charon` → **72 findings** while `check_security.py` reports "OK: no anti-patterns found" |
| Same, breakdown | — | — | — | BLE001 blind-except ×25, S110 try-except-pass ×15, S603 ×13, S607 partial-path ×8, S105 ×4, S101 ×3, S112 ×2, **S104 hardcoded-bind-all-interfaces ×1**, **S602 shell=True ×1** |
| `PT` (flake8-pytest-style), `D` (pydocstyle), `PLR0915` | YES — `tools/check_test_patterns.py` (duplicate names, missing docstrings, oversized tests, parametrize ratio) | DTC-6 (parked, "parametrize repeating test functions") | **PARTIAL** — PT/D cover docstrings, naming and parametrize idioms; the parametrize *ratio* metric is ours | [READ] `ruff linter` output |
| `TID` banned-api | YES — `tools/check_arch.py` layer isolation | API-DECOMPOSE-CYCLE-FIX | **PARTIAL** — `flake8-tidy-imports.banned-api` can express "engine must never import gateway" declaratively; circular-import and stdlib-only-core checks are ours | [READ] `ruff linter` |

**Smoking gun:** `src/charon/acceptance.py:54` already carries `# noqa: S602`, and
`tools/check_security.py:195` explicitly honours `# noqa: S602` — i.e. our hand-rolled scanner
reimplements ruff's rule *and its noqa code namespace*, while ruff's `S` family sits switched off.
ROADMAP **KS31** states the principle in-house: *"KSF gate-plugins are thin ADAPTERS over
ruff/mypy/bandit/… — NEVER reimplement a tool; Charon uses only 3 of ~15."*

### 2C. mypy / pytest / gh

| Tool | Under-used? | Detail |
|---|---|---|
| mypy | YES, low value | `pyproject.toml:53-56` sets only `ignore_missing_imports`. Zero strictness flags (`disallow_untyped_defs`, `warn_unused_ignores`, `strict`). High churn to enable; ranked low deliberately. |
| pytest-xdist | **NO** | `-n auto` already used (`ci.yml:55`, `release.yml:62`). Correctly utilized. |
| gh | Marginal | `gh api --cache <dur>` exists natively (v2.63.2). **But see §4** — it does not serve `fleet/gh-cache.sh`. |

---

## 3. Ranked under-utilizations (highest value first)

**U1 — `litellm_params["order"]`: the missing 8 characters that make the whole cutover faithful.**
Charon already *computes* the correct chain order in `_preorder_chain` (`litellm_router.py:195-212`)
— funding class, then drain priority — and then discards it by handing an unordered `model_list` to
a simple-shuffle Router. Setting `order = i+1` from the already-computed chain index in `_deployment()`
(`litellm_router.py:133-143`) is a **faithful, complete** translation: LiteLLM will pick order-1 every
time and, on failure, walk the order ladder. **[EXEC]** 300/300 vs 97/105/98.
*Blocks:* GW-CUTOVER-LIVE-WIRE cannot honestly land without this — cutting over today would replace
cheapest-first routing with a coin flip on the live money path.
*Caveat (stated, not hidden):* `order` is static per Router build, so the Router must be rebuilt (or
`model_list` updated) when funding/balance state changes. That is **not a new constraint** — today's
`_preorder_chain` has exactly the same rebuild requirement.

**U2 — `enable_pre_call_checks=True`: one flag; our `max_input_tokens` is currently dead config.**
We compute and write `model_info.max_input_tokens` at `litellm_router.py:142`, and the filter that
consumes it is off by default, so it does nothing. **[EXEC]** with it off, a 4000-token prompt is
routed to a 100-token-context leg; with it on, it correctly rolls to the large-context leg.
This is a KSF-inert-code-shaped defect living in a *third-party config surface*, where our
inert-code gate cannot see it.
*Cancels:* **CAPABILITY-ENGINE** (parked) — its stated goal "skip requests exceeding provider
max_context" is delivered by this flag.

**U3 — Enable ruff `S` + `BLE`; shrink or retire `tools/check_security.py`.**
**[EXEC]** 72 real findings from a linter we already install and already run in CI, including one
`shell=True` and one bind-all-interfaces in a money-path gateway, while the 330-line hand-rolled
equivalent reports clean. Per the standing security-ratchet rule this is the highest-severity item
here even though U1 is the highest-leverage.
*Shrinks:* BANDIT-PREEXISTING-FINDINGS (ruff `S` supersedes running bandit separately);
advances ROADMAP KS31.
*Keep custom:* hardcoded-IP detection and `check_public_clean.py` — no ruff rule covers those.

**U4 — LiteLLM's model catalog as the price/context/capability data source.**
2954 models, 123 providers, offline, refreshed every LiteLLM release, carrying exactly the fields
several tickets are chartered to go collect. PRICE-REFRESHER's own brief says *"wrap an existing
pricing data source — adopt-not-build, no bespoke scraper"*; that source is already installed.
*Shrinks:* PRICE-REFRESHER (source question answered), INVENTORY-TABLE / INVENTORY-TABLE-SHARE
(seed rather than collect), ADR0016-DEPLOY-PRICED-COMPLETENESS (the completeness check gains a
reference table), DISCOVERY-SOURCE-ADAPTERS (one adapter is `litellm.get_model_info`).
*Bonus:* `supports_function_calling` / `supports_tool_choice` are live per-model facts relevant to
`state/TOOLCALL-ROOTCAUSE.md`.

**U5 — `fallbacks` / `context_window_fallbacks` / `content_policy_fallbacks`.** All four fallback
kwargs unset. `context_window_fallbacks` is the exact mechanism for "this prompt is too big for the
cheap leg, use the big-context one" that ROADMAP R29 (context compaction) works around by *mutating
the user's messages* — a far more invasive answer to the same problem.
*Cancels/shrinks:* PFF-P2 (parked, "cross-model substitution when own pool exhausted"),
FREE-TIER-QUOTA-SPILL (parked).

**U6 — `RetryPolicy` / `AllowedFailsPolicy`.** We use a single flat `num_retries=1` and
`allowed_fails=3` for every failure class, so an auth failure (never retryable) is treated like a
rate-limit (always retryable) — and both burn the same cooldown budget. Per-exception policies are a
dataclass away.

**U7 — `optional_pre_call_checks=["deployment_affinity"]`.** Retires `session_affinity.py` (61 lines)
for a 527-line implementation that also handles API-key-hash affinity and Responses-API continuity.

**U8 — LiteLLM `integrations/prometheus.py` + `langfuse/`.** Two of the four backends in our
hand-rolled `observability.py` (150 lines) ship maintained in-package.

**U9 — mypy strictness flags.** Real but high-churn, low-severity. Listed for completeness only.

**Ticket impact summary:** 2 parked tickets fully answered by an existing flag
(CAPABILITY-ENGINE, PFF-P2), 1 more effectively answered (FREE-TIER-QUOTA-SPILL);
5 open tickets materially shrunk (PRICE-REFRESHER, INVENTORY-TABLE, INVENTORY-TABLE-SHARE,
DISCOVERY-SOURCE-ADAPTERS, BANDIT-PREEXISTING-FINDINGS); 1 open ticket unblocked and made
honest (GW-CUTOVER-LIVE-WIRE via U1).

---

## 4. Looks similar but does NOT serve — do not rip out working code for these

**4.1 `routing_strategy="cost-based-routing"` ≠ Charon's cheapest-capable ordering.** Three
independent reasons, any one fatal:
1. **[EXEC]** It is not implemented on the sync path at all — `router.completion()` raises
   `RouterRateLimitError`. `router.py:1078-1080` says the omission is intentional.
2. It ranks on `input_cost_per_token + output_cost_per_token` — **static list price, unweighted**,
   defaulting to a sentinel `5.0` for any model not in the cost map (`lowest_cost.py:~250`). Charon
   ranks by *funding class* then *remaining balance* — live state, not list price.
3. It selects **one** deployment; it does not produce an ordering, so there is no
   roll-to-next-on-exhaust semantics to inherit.
   → Use `order` (U1). It expresses what we actually compute, and it works.

**4.2 `provider_budget_config` ≠ drain-then-park.** LiteLLM budgets are *`max_budget` over a
rolling `budget_duration` time window*, keyed by `custom_llm_provider` or deployment id
(`budget_limiter.py:786-800`). Charon's model is a **prepaid balance that drains permanently and
then parks the provider**, with **funding-class ordering** deciding who drains first. A time-windowed
cap cannot express "spend this credit down to zero, then never again until topped up", and carries no
funding-class dimension. Additionally it is `async_filter_deployments`-only. **Verdict: partial at
best — keep `balance.py`.** (`balance.py`'s real gap remains disk persistence, per the 2026-07-13
audit finding #4 — unrelated to this.)

**4.3 LiteLLM deployment rate limits ≠ `quota.py`.** LiteLLM's `rpm`/`tpm`/`itpm`/`otpm` are
**minute-granularity only** — `seconds_until_minute_reset()` and `dt.strftime("%H-%M")` keys
(`io_token_rate_limit_check.py:60-62, 398`). `quota.py` (638 lines) exists precisely for what
free tiers actually meter on: **RPD / TPD / RWK / TWK / RMO** *and* calendar-anchored resets
(UTC midnight, Monday 00:00, first-of-month). Nothing in LiteLLM has a day/week/month window or a
calendar anchor. **Verdict: does NOT serve. FT-WIRE-QUOTA stays a real build.**

**4.4 LiteLLM guardrails are a *proxy-stack* feature, not a *Router* feature.** The 50+ guardrail
integrations live under `litellm/proxy/guardrails/` and hang off the proxy hook chain — the Prisma/
Postgres/FastAPI stack ADR-0017 explicitly declined. The Router's own `guardrail_list` kwarg is
effectively inert (one lookup at `router.py:4286`). **Verdict: does NOT serve from our
Router-as-library posture. Keep `guardrails.py`.** Same reasoning retires the idea of adopting
LiteLLM's virtual keys in place of `virtual_keys.py`.

**4.5 `gh api --cache` ≠ `fleet/gh-cache.sh`.** `--cache` is real (v2.63.2) but only applies to
`gh api`. `gh-cache.sh` wraps **`gh pr list`** (`gh-cache.sh:49, 75, 112`), which has no `--cache`
flag — and, more importantly, its value is **batching** (O(repos) instead of O(tickets) calls, the
documented root cause of the rate-limit exhaustion), which response caching does not provide.
**Verdict: does NOT serve.** GITHUB-LIMITS-HARDENING and PREFLIGHT-VERIFY-MERGED-GHCACHE remain
real work.

**4.6 `latency-based-routing` ≠ `latency.py`.** It works (sync included), but it makes latency the
*primary* selector. Charon uses latency as a *secondary* tiebreak plus a graceful-degrade flag.
Adopting it as-is would silently demote cost ordering. **Partial — usable only as a tiebreak inside
an order tier, which LiteLLM cannot currently express.**

**4.7 LiteLLM cost calculator ≠ GATEWAY-NONTOKEN-METERING.** It handles per-second, per-query,
per-image, per-character billing — but has **no energy/kWh dimension**, which is the NeuralWatt case
that ticket exists for. Partial only.

**4.8 `tool_repair.py` / `response_normalizer.py` have no LiteLLM analogue.** LiteLLM normalizes
*provider wire formats*; these repair *malformed model output* (tool-call argument JSON, content
strings). Different problem. Keep.

---

## 5. Verified by execution vs by reading

**[EXEC] — run on this box, 2026-07-24** (scripts under
`…/scratchpad/t_order.py`, `t_ctx.py`, `t_caps.py`):
1. simple-shuffle randomness reproduced: 300 picks → `{c:107, a:101, b:92}`.
2. `order=1,2,3` → `{a:300}` deterministic, **on the sync path**.
3. `routing_strategy="cost-based-routing"` sync → `RouterRateLimitError`; async → works.
4. `enable_pre_call_checks` False→picks 100-tok leg, True→picks 200k leg for a 4000-tok prompt.
5. `Router.__init__` = 52 params; `make_router` sets 6; the 46 unused enumerated.
6. `get_model_info` returns live price/context/tool-calling for groq, deepseek, gemini ids.
7. Catalog census: 2954 models, 123 providers, 2481 priced, 2535 with context; non-token pricing
   key census.
8. `ruff check --select S,BLE src/charon` → 72 findings; `ruff check src/charon` (current select) →
   clean; `tools/check_security.py` → "OK: no anti-patterns found".
9. `gh api --help` → `--cache duration` exists.

**[READ] — installed source, cited `file:line`, not executed:** the order-based fallback ladder
(`router.py:6035-6075`); `RetryPolicy`/`AllowedFailsPolicy` shapes; `budget_limiter.py` key
derivation and per-deployment budget registration; `io_token_rate_limit_check.py` minute-window
keys; `deployment_affinity_check.py` behaviour; the `integrations/` and
`proxy/guardrails/guardrail_hooks/` inventories; `tag_based_routing.py`; `gh-cache.sh` internals.

**Not verified:** no live provider calls were made; no gateway was started; no ticket, config or
source file was modified. The ruff `S`/`BLE` findings are counts from a clean run — each still needs
individual triage (some `S603`/`S607` hits will be legitimate and want `# noqa` or per-file ignores).
