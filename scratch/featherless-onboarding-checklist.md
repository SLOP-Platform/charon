# Featherless flat-rate leap — ONBOARDING CHECKLIST (#3)

**Purpose:** a durable, copy-pasteable checklist for the operator to adopt the flat-rate
provider stack **when they choose to**. This document changes NOTHING — no signups, no
config writes, no key creation happen here. It is the runbook to execute later.

**Source of record:** `best-stack-recommendation.md` (Stack C Hybrid ★), `provider-pricing.md`,
`six-provider-verify.md`. Compiled 2026-07-08.

**Recommended shape (Stack C Hybrid):** Featherless Premium $25/mo flat = open-model
bulk workhorse · DeepInfra metered = cheap concurrency spillover · gpt-5.4 on
nanogpt/openrouter kept as a **metered escape hatch** (NOT the default). Ordered
input-cheap-first everywhere (the load is 234:1 input:output — input cost is the whole game).

---

## THE ONE HARD GATE (read first)

> **The capability cutover from `gpt-5.4` to any open model is UNPROVEN and MUST NOT be
> assumed.** No open model (DeepSeek / Qwen3-Coder / GLM) is confirmed to match gpt-5.4 on
> real Build outcomes. The decision to widen the open-model share is owned by the
> **real-outcomes benchmark pivot (#26 / #25)** — actuals ledger + reds-replay — NOT by
> cost, vibes, or this checklist.
>
> **Adoption rule:** add the open workhorse as **secondary / shadow first**. Keep gpt-5.4 as
> primary or as the live escape hatch. **Cut over only when the benchmark says the open model
> is good enough.** Everything below is structured to make that swap *reversible*.

---

## STEP 1 — Featherless (flat-rate open-model workhorse)

### 1a. Pick the plan
- **Single-user gateway (operator is the ONLY consumer behind Charon) → Premium $25/mo.**
  Any open model, unlimited tokens, 4 concurrent units, no logging. This is the recommended
  FIRST plan. ToS reading: **YELLOW** (personal/prototyping-by-purchaser only).
- **If the gateway will EVER front anyone but the operator → Scale ($75–200/unit/mo), NOT
  Premium.** Scale is the only Featherless tier whose ToS is claimed to permit inference
  resale. Do NOT rely on that claim until the ToS re-read in 1e is done.
- Reference points: $10 Basic (≤15B models only — too small for the workhorse), $25 Premium
  (any model — pick this), $100 Agent-Standard (≤229B, 256K ctx), $200 Agent-Max (any).

### 1b. Sign up
- URL: **https://featherless.ai** → Plans page: **https://featherless.ai/plans**
- Create account, subscribe to **Premium ($25/mo)**.

### 1c. Get the API key
- Dashboard → API Keys → create a new key. Copy it once (store in a password manager;
  it will be pasted into Charon's secret store in Step 4, never into a file in the repo).

### 1d. OpenAI-compatible endpoint contract
- **base_url:** `https://api.featherless.ai/v1`
- **Auth header:** `Authorization: Bearer <FEATHERLESS_API_KEY>` (standard OpenAI style)
- **Endpoints:** `POST /v1/chat/completions`, `GET /v1/models`
- Smoke test (fill the key — run only after signup, this is the LEGIT test call, ~1 token):
  ```bash
  curl -s https://api.featherless.ai/v1/chat/completions \
    -H "Authorization: Bearer $FEATHERLESS_API_KEY" \
    -H "Content-Type: application/json" \
    -d '{"model":"deepseek-ai/DeepSeek-V3.2","messages":[{"role":"user","content":"hi"}],"max_tokens":1}'
  ```
  (Model id must be a valid Featherless/HF slug — confirm the exact slug via `GET /v1/models`.)

### 1e. Rate / concurrency limits to expect
- **Throttled by CONCURRENT UNITS, not tokens/RPM.** Premium = **4 concurrent units**;
  **unlimited monthly requests + unlimited tokens.** When >4 parallel Build requests hit at
  once, the 5th queues — this is the wall, and it is exactly why DeepInfra spillover (Step 2)
  exists. Because tokens are free, the 234:1 input-heavy load is a landslide win here.

### 1f. ToS RE-READ ACTION (required before relying on Scale)
- [ ] Fetch and read the **full** `https://featherless.ai/terms` page (not a search snippet).
- [ ] **Verify verbatim** that the **Scale** tier explicitly permits **inference resale /
      proxying third-party traffic**. This clause was only seen in a search snippet (MEDIUM
      confidence). If the full ToS does NOT clearly permit resale on Scale, **Featherless
      cannot legitimately back a multi-user gateway** and the multi-user plan must be
      reconsidered.
- [ ] Confirm the individual-plan language: individual plans are "for interactive use or
      prototyping by the purchaser; other purposes → subscription terminated, no refund."
      This confirms Premium is single-user-ONLY.

---

## STEP 2 — DeepInfra (cheap metered concurrency spillover)

### 2a. Sign up
- URL: **https://deepinfra.com** → sign in (GitHub/Google), then Dashboard → API Keys.

### 2b. Get the API key
- Dashboard → **API Keys** → create → copy once (→ Charon secret store in Step 4).

### 2c. OpenAI-compatible endpoint contract
- **base_url:** `https://api.deepinfra.com/v1/openai`
- **Auth header:** `Authorization: Bearer <DEEPINFRA_API_KEY>`
- Standard `POST /v1/openai/chat/completions`, `GET /v1/openai/models`.

### 2d. Cheapest big open models to configure ($/1M in / out — DeepInfra is the price leader)
| Model (config as spillover, input-cheap-first) | Price in/out | Model slug (verify live) |
|---|---|---|
| **Qwen3-235B** (cheapest input — favor for the 234:1 shape) | **$0.09 / $0.10** | `Qwen/Qwen3-235B-A22B` |
| **DeepSeek-V3.2** | **$0.26 / $0.38** | `deepseek-ai/DeepSeek-V3.2` |
| DeepSeek-V3 | $0.32 / $0.89 | `deepseek-ai/DeepSeek-V3` |
| Llama-3.3-70B-Turbo | $0.10 / $0.32 | `meta-llama/Llama-3.3-70B-Instruct-Turbo` |
| Llama-3.1-8B / Mistral-Nemo (tiny/last-ditch) | $0.02 / $0.05 · $0.02 / $0.04 | — |
- Confirm every slug and price on **https://deepinfra.com/pricing** and `GET /models` before
  wiring — open-model rosters/prices drift weekly.

---

## STEP 3 — Coding-workhorse candidates + the cutover gate

**Candidates to evaluate as the open workhorse (serve on Featherless flat; spillover on
DeepInfra metered):**
- **DeepSeek V3.2** (a.k.a. the DeepSeek-V4 line) — strong general coding.
- **Qwen3-Coder / Qwen3-235B** — cheapest input on DeepInfra; natural spillover default.
- **GLM (GLM-5)** — alternative; pricier metered ($0.95/$2.55 on SiliconFlow) so prefer it on
  the flat Featherless tier if chosen.

**EXPLICIT GATE (repeat of the hard gate, applied here):**
- These are **candidates**, not a decided replacement for gpt-5.4.
- **Wire them as SECONDARY / SHADOW first.** Route real traffic to gpt-5.4 as today (or
  mirror to the open model for measurement) — do NOT flip the default bulk target to an open
  model on day one.
- **Cut over only when the real-outcomes benchmark (#26/#25) says the open model is good
  enough** on actual Build outcomes (actuals ledger + reds-replay). Until then the open model
  earns bulk traffic incrementally, benchmark-approved, and gpt-5.4 stays reachable.

---

## STEP 4 — Wire into Charon (product-standalone, NO code change)

**Fact:** adding a provider needs **no code change**. `featherless` and `deepinfra` are NOT in
the built-in preset registry, so you supply `base_url` + `key_env` explicitly on add; the
setup-API validates the key with a live probe, persists to `providers.json`, stores the secret
0600, and **hot-reloads the live routes** (no restart). In the deployed container
`CHARON_HOME=/data`, so config + secrets live on the mounted `/data` volume.

### 4a. BACK UP /data FIRST (data-loss guard — do this before any write)
```bash
# inside/against the box hosting charon-gateway-1, /data is the mounted volume
docker exec charon-gateway-1 sh -c 'cd /data && tar czf - providers.json models.json pools.json' \
  > charon-data-backup-$(date +%Y%m%d-%H%M%S).tar.gz
# (secrets.json is 0600 — back it up separately/securely if you keep a copy at all)
```

### 4b. Setup-API contract (all POSTs are token-gated + CSRF-guarded)
- Base: the gateway URL, e.g. `http://127.0.0.1:8080` (or open the web UI at `/charon/setup`).
- **Auth:** `Authorization: Bearer <GATEWAY_TOKEN>` (or `?token=<GATEWAY_TOKEN>` in the URL).
- **CSRF:** cross-origin / cross-site writes are refused; call same-origin (the built-in
  `/charon/setup` page handles this for you) or from a local script hitting the same host.
- Provider add validates the key with a real completion probe **before** persisting — a bad
  key returns 400 and writes nothing.

### 4c. Add the two providers (input-cheap-first ordering starts here)
```bash
GW=http://127.0.0.1:8080
TOK=<GATEWAY_TOKEN>

# Featherless (flat workhorse) — base_url + key_env REQUIRED (not a preset)
curl -s -X POST "$GW/charon/providers" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"name":"featherless","base_url":"https://api.featherless.ai/v1",
       "key_env":"FEATHERLESS_API_KEY","key":"<PASTE_FEATHERLESS_KEY>"}'

# DeepInfra (cheap metered spillover) — base_url + key_env REQUIRED (not a preset)
curl -s -X POST "$GW/charon/providers" -H "Authorization: Bearer $TOK" \
  -H "Content-Type: application/json" \
  -d '{"name":"deepinfra","base_url":"https://api.deepinfra.com/v1/openai",
       "key_env":"DEEPINFRA_API_KEY","key":"<PASTE_DEEPINFRA_KEY>"}'
```

### 4d. Add one model per backend, then pool them cheap-first
Charon **pools** map a virtual model id → an **ordered list of MODEL ids** (each model
references a provider). So: define a model on each provider, then chain them. Order =
flat-rate first → cheapest-input metered → funded backstop last.
```bash
# workhorse-on-featherless (flat, tries first)
curl -s -X POST "$GW/charon/models" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"id":"work-featherless","provider":"featherless","upstream_model":"deepseek-ai/DeepSeek-V3.2","cost_class":"prepaid"}'
# spillover-on-deepinfra (cheapest input)
curl -s -X POST "$GW/charon/models" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"id":"work-deepinfra-qwen","provider":"deepinfra","upstream_model":"Qwen/Qwen3-235B-A22B","cost_input":0.09,"cost_output":0.10,"cost_class":"metered"}'

# the pool the Build client points at — flat → cheap-metered → funded backstop
curl -s -X POST "$GW/charon/pools" -H "Authorization: Bearer $TOK" -H "Content-Type: application/json" \
  -d '{"id":"coding-workhorse","members":["work-featherless","work-deepinfra-qwen","neuralwatt-<model>","deepseek-<model>"]}'
```
- Keep the **gpt-5.4 pool = `[nanogpt, openrouter]`** as-is; route to it only for explicit
  premium requests (the escape hatch). Do NOT make it the default bulk target, and do NOT
  delete it — it is the fallback if the open workhorse underperforms.
- Optionally set global `fallback_providers` (POST `/charon/fallback`,
  `{"providers":["groq","mistral","together","neuralwatt","deepseek"]}`) so a balance event
  never dries a pool.
- After each POST the routes hot-reload; confirm via `GET /charon/config`.

### 4e. Known operational gotcha (from six-provider-verify)
- The gateway's outbound path must send a **browser-like User-Agent**. groq/cerebras/together
  return spurious Cloudflare `403 error 1010` on `Python-urllib`, which would make healthy
  backstops look dead. Verify/fix the UA before trusting failover health.

---

## STEP 5 — ToS / legitimacy gate (the compliance boundary)

**Today (single-user gateway, operator is the ONLY consumer): the whole Stack C is clean under
a YELLOW reading. No GREEN plan is required while single-tenant.**

**The condition that makes each flat-rate plan NON-COMPLIANT** — memorize this line:

> **The moment the Charon gateway serves inference to ANYONE other than the operator**, every
> personal/individual flat-rate plan behind it is in violation.

Per-provider trigger:
| Provider / plan | Compliant while… | Becomes non-compliant when… | Fix |
|---|---|---|---|
| **Featherless Premium $25** | operator-only behind the gateway | any third party is served through it | move to **Featherless Scale** (only after the 1e ToS re-read confirms resale) |
| **DeepInfra / OpenRouter / nanogpt / DeepSeek (metered)** | standard commercial PAYG, operator use | verify each provider's resale clause before multi-user | metered terms are more permissive but re-read resale clauses |
| MiniMax / Ollama / Synthetic (NOT in this stack) | — | personal-account / substitute-service / account-sharing bans → RED for multi-user | excluded from the multi-user spine |

**Other ToS caveats carried forward:**
- DeepSeek-direct is **China-hosted** (data-sensitivity) — backstop only, never primary.
- Mistral's **free** tier trains on your data — use paid/opt-out only.
- OpenRouter bans building a competing resale service + anti-circumvention (no multi-account
  free-tier stacking).

**Multi-user-clean spine (if/when the gateway fronts others):** Featherless **Scale** (pending
the resale-clause re-read) + OpenRouter pass-through — materially higher base cost (~$75–200).

---

## Execution checklist (tick when you actually do it — not now)
- [ ] Decide plan: Premium $25 (single-user) — confirm still single-user.
- [ ] Featherless: sign up, subscribe Premium, create key.
- [ ] **Re-read full Featherless ToS; verify Scale resale clause (Step 1e).**
- [ ] DeepInfra: sign up, create key, confirm model slugs + prices live.
- [ ] Back up `/data` (Step 4a).
- [ ] POST both providers (Step 4c), POST models + `coding-workhorse` pool (Step 4d).
- [ ] Keep gpt-5.4 pool intact as the escape hatch; open model added SECONDARY/SHADOW.
- [ ] Verify browser-UA on outbound path (Step 4e).
- [ ] **Do NOT widen open-model share until the #26/#25 benchmark approves the cutover.**
