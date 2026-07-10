# Charon Provider Roster + trae.ai Research

READ-ONLY compile. Date 2026-07-09. Live box `10.0.1.60` / `charon-gateway-1` `/data`. Grounds current wiring from live `providers.json`/`pools.json`/`quality.json` and from `provider-cost-rationalization.md`.

---

## Task 1 — trae.ai as a candidate provider

### Verdict: DO NOT ADD. trae.ai is an IDE-only client, not a routable provider. No API to point Charon at.

trae.ai (ByteDance's "TRAE" AI-native IDE) is a downstream *consumer* of models, the same role Cline/Windsurf/Cursor play. It is architecturally the wrong side of the gateway: **Trae would point AT Charon, not the reverse.** It exposes no public inference endpoint.

**Funding model (IDE seat pricing, not token API):**
- Free-forever plan; Pro ~**$10/mo** (first month discounted to ~$3); Enterprise via BytePlus. [trae.ai/pricing, saasworthy]
- Billing is **request-metered, not token-metered**: ~600 "fast requests"/mo + unlimited "slow requests" for premium models. One prompt = one-or-more requests regardless of token size — a whole-codebase edit costs the same one request as an inline tweak. This is a seat/quota product, not PAYG-per-token. [websearch: yangmao.ai, saasworthy, vpsranking]

**API compatibility — the disqualifier:**
- Trae **does not expose its own API endpoint** (no `/v1/chat/completions`, no top-level `choices`, no custom envelope — nothing callable). It is "designed as a local IDE application rather than a cloud-based API service." [websearch summary of docs.trae.ai + Trae-AI/TRAE GitHub Issue #597 "Feature Request: Allow Custom API Endpoint Configuration" — i.e. even *outbound* custom endpoints are an open feature request]
- The yangmao.ai provider tracker (snapshot 2026-06-24) states outright: **"No confirmed free API quota found; the free value is mainly the web app or local open-source use,"** rate limits N/A, no OpenAI-compatible endpoint tracked. [yangmao.ai/en/providers/trae/free-api/]
- Trae lets *you* plug your own OpenAI/Claude/GLM keys INTO it (bring-your-own-model). That is the inverse of a provider Charon can route to.

**Models:** built-in premium models + bring-your-own via custom keys (GLM/Claude/OpenAI etc.). No exclusive model or free token pool that Charon lacks. [docs.trae.ai/ide/models, docs.z.ai TRAE overview]

**Funding class:** N/A — it is not a provider. If classed at all it is a flat IDE subscription (class 2-shaped) but with **no marginal-cost-$0 API surface** to exploit.

**Bottom line:** Redundant AND not API-capable without an endpoint that does not exist. Nothing to wire. If anything, Trae is a client that could be pointed at Charon's OpenAI-compatible gateway (bring-your-own-endpoint, pending their Issue #597) — an integration *demo*, not a provider add. **No signup warranted.**

Citations: https://www.trae.ai/pricing ; https://docs.trae.ai/ide/new-plans-and-billing ; https://docs.trae.ai/ide/models ; https://yangmao.ai/en/providers/trae/free-api/ ; https://github.com/Trae-AI/TRAE/issues/597 ; https://www.saasworthy.com/product/trae-ai ; https://vpsranking.com/ai/trae/

---

## Task 2 — Canonical provider roster

Funding-class taxonomy: **(1)** free-tier recurring quota · **(2)** flat subscription ($0 marginal) · **(3)** drain-then-park (finite prepaid credit) · **(4)** true PAYG (metered).

Success rates are LIVE from `/data/quality.json` (2026-07-09) except hf/cline-pass (from report; truncated in this pull). Balances for class-3 are the operator-supplied figures.

| Provider | Class | Monthly cost / balance | Wired? | Success (live) | OpenAI-shaped? | Constraints (ctx / concurrency) | Role recommendation |
|---|---|---|---|---|---|---|---|
| **nanogpt** | 2 flat | $12/mo flat ($0 marginal) | Yes (`-ng` on ~all pools) | **52/52** | Yes (clean id echo) | none observed | **Promote to cheap-first** on the 5 cline-first pools; primary drain leg everywhere |
| **groq** | 1 free | $0 | Yes (`free-groq` in `auto`) | 7/7 | Yes | free-tier rate/day caps | **Keep** — free, perfect; free-first |
| **cerebras** | 1 free | $0 | Yes (`free-cerebras` in `auto`) | 4/4 | Yes | free-tier caps | **Keep** — free-first |
| **mistral** | 1 free | $0 | Yes (`free-mistral-code`/codestral) | 2/2 | Yes | free-tier caps | **Keep** — free-first |
| **huggingface** | 1 free/PRO | $0–PRO (HF_TOKEN) | Yes (`-hf` on glm/kimi/deepseek) | 6/7 (report) | Yes | free/PRO caps | **Keep** — cheap free-tier spill |
| **opencode-go** | 2 flat? / free | ~$10/mo flat *(unconfirmed which opencode is flat)* | Yes (`fallback.json` + `-go` free legs) | 4/6 | Yes | — | **Keep as fallback**; confirm it (not zen) is the flat $10/mo — see flag |
| **opencode-zen** | 3 prepaid | ~$10 prepaid balance (`balance.py:150`) | Partial — **bare ids NOT in any pool** (pools use `-ng`/`-or`) | 6/6 | Yes | — | **Reconcile**: prepaid but unreferenced. Wire to drain the balance, or let run down |
| **cline-pass** | 2 sub | Cline subscription (cost unknown) | Yes (`-cline` rank-1 on 5 pools) | 11/11 (report) | via gateway yes; direct non-streaming unverified | `strip_v1` quirk; non-streaming envelope unverified | **Demote to spill** below nanogpt until non-streaming envelope verified; confirm sub value |
| **deepseek** | 3 prepaid | **$9.99** prepaid | Yes (`-ds` legs) | 2/2 | Yes | — | **Keep** — drain the credit, cheap; small |
| **together** | 3 prepaid | **$9.83** prepaid | Yes (`minimax-m3-together`, minimax pools) | 5/5 | Yes | — | **Keep** — drain the credit; works |
| **openrouter** | 3 prepaid | **$9.90** prepaid | Yes (`-or` 2nd leg ~every pool) | **1/10 (0.6)** | Yes | — | **INVESTIGATE** — paid-but-failing; **balance BLOCKED from draining** by 1/10 flakiness (credits/model-id/402s). Do not rely on as spill until fixed |
| **neuralwatt** | 3 prepaid | **$22.00** prepaid (memory said $20/mo flat) | Yes (`paid-neuralwatt-code` in `auto`; `-nw` on glm-5.2/kimi-k2.6) | **0/4 (FALSE fail)** | Yes | returns quant/case id variant | **Drain BLOCKED** by `proxy.py:247` `_normalize_model_id` (case/quant-suffix false-downgrade). **Operator decision: fix-normalize-and-drain, OR cancel/park (redundant — no pool depends solely on it)** |
| **featherless** | 2 flat | flat/unlimited (candidate) | **No — not wired** | n/a | (assumed) Yes | **32K ctx/session, concurrency=1** — hard router constraints | **Candidate add** only if a 32K-ceiling, serial-only spill leg is wanted; low priority given constraints |
| **trae.ai** | — | ~$10/mo IDE seat | No | n/a | **No API endpoint at all** | IDE-only; request-metered | **DROP / do not add** (see Task 1) |

Note: live `providers.json` only enumerates 5 explicit entries (opencode-zen, openrouter, neuralwatt, cerebras, cline-pass); nanogpt/groq/mistral/together/huggingface/deepseek/opencode-go resolve from built-in defaults. All appear in `quality.json`, so all are live-wired.

### Balances BLOCKED from draining (bugs, not funds)
- **neuralwatt $22.00** — blocked by `proxy.py:247` `_normalize_model_id` (case-sensitive + no quant-suffix strip → `Kimi-K2.7-Code`/`GLM-5.2-FP8` read as downgrade → scored 0/4). Provider actually returns 200s.
- **openrouter $9.90** — blocked by 1/10 flakiness (9 real failures on `-or` legs; check credits / model-id / 402s).
- Both compound the est_cost billing bug (`forwarder.py:315,400`) that fabricated the phantom $223 `spent_usd`.

### Role-change summary vs current wiring
- **Promote:** nanogpt → cheap-first on `deepseek-v4-pro`, `deepseek-v4-flash`, `glm-5.2`, `kimi-k2.6`, `minimax-m3-free` (flat $0 marginal, 52/52, clean id echo).
- **Demote:** cline-pass rank-1 → spill (non-streaming envelope unverified).
- **Fix-then-drain / or park:** neuralwatt (normalize fix), openrouter (flakiness investigation) — their prepaid balances are stranded until fixed.
- **Reconcile:** opencode-zen prepaid balance unreferenced by any pool — wire to drain or retire.
- **Drop/no-add:** trae.ai (no API); featherless only if a constrained serial spill leg is explicitly wanted.

### Needs OPERATOR DECISION
1. **trae.ai** — confirm DROP (no API to add; at most a future bring-your-own-endpoint *client* demo, not a provider). No signup.
2. **neuralwatt $22.00** — fix `_normalize_model_id` and drain, OR cancel/park (redundant, nothing breaks).
3. **opencode flat-$10 identity** — confirm whether **opencode-go** (free/fallback legs) or **opencode-zen** (shows prepaid balance → looks class-3) is the flat $10/mo subscription. Report evidence points to zen=prepaid, go=flat/free, but this is unconfirmed.
4. **openrouter $9.90** — authorize the 1/10 investigation before trusting `-or` as spill.
5. **featherless** — add as a 32K/serial spill leg? (needs a response path that respects concurrency=1 + 32K ceiling.)
6. No provider currently needs a *response adapter* (all wired ones return top-level `choices`). trae.ai would have needed one only if it had an envelope — it has no endpoint at all.
