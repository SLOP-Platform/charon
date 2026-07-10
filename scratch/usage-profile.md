# Charon actual usage profile (real demand, live-extracted)

Extracted 2026-07-08 (READ-ONLY) from gateway 4-LOM `charon-gateway-1`, build f369b7c (v0.3.6).
Purpose: ground a cost analysis in real demand, not guesses.

---

## TL;DR (for the cost analysis)
- **One model dominates the observed window: `gpt-5.4`.** 100% of the failover-ring evidence (38/38 events) is gpt-5.4; it is effectively the only model with recorded traffic in the observed window. **Framing caveat:** this dominance reflects ONE long Build/test session, **not a chosen workhorse**. `gpt-5.4` is an **incumbent-under-test**, and **no model is finalized for any tier**. Per-tier model selection is **PENDING real-code testing + the real-outcomes benchmark** (BENCH-REGROUND-LIVE / #26).
- **openrouter is the real paid backstop** — it served ~89% of paid traffic (108/122 serves) and carries **100% of the real metered cost ($7.46 in the 19h window)**. nanogpt mostly 402'd out.
- **Traffic is extremely input-heavy: ~234:1 in:out** (18.89M in / 0.08M out) — a classic coding-agent (opencode/droid Build session) profile: huge repo context, tiny completions.
- **Month-to-date spend = $221.84** (2026-07, aggregate, persisted). The $7.46 is only the current-container 19h slice.
- **There is NO per-model or per-provider spend ledger.** The only durable number is a single monthly aggregate. Everything per-model is inferred, not stored. Treat model-level demand as "gpt-5.4 = the load," confidence HIGH on dominance, but exact per-model token/$ split is UNAVAILABLE.

---

## Data sources & windows (be honest about limits)

| Source | What it holds | Window | Durability |
|---|---|---|---|
| **`GET /charon/status`** (in-memory observer, `proxy_server.py::status_snapshot`) | per-**provider** served/failed/errors/cost; ONE aggregate `usage` (tokens_in/out/cost); `recent_failovers` ring (last 50, **failover events only**) | **since container start 2026-07-08 05:24 UTC ≈ 19h** | **VOLATILE** — zeroed on every container recreation |
| **`/data/spend.json`** (`SpendLimiter`, persisted) | ONE aggregate `spent_usd` | **month-to-date 2026-07-01 → 07-08 (~8 days)** | Survives restarts; **resets monthly** |

Critical gaps:
- **No actuals ledger, no per-model accounting, no per-day history.** The "ring buffer" from the diagnosis is the in-memory `failover_events` deque (maxlen 200) and is **failover-only** — clean single-provider serves are never recorded there. So the ring under-samples: it captures only requests that had to fail over.
- The aggregate `usage` counter and `spend.json` are **single scalars** — they cannot be split by model or provider.
- `spend.json` records `cost if cost>0 else est_cost` (proxy_server.py:889/974), so **free-tier serves are billed at estimated paid rates**. => **$221.84 is the economic value of traffic (an UPPER bound), not strictly out-of-pocket dollars.** The `$7.46` openrouter figure IS real metered cost (from openrouter's response).
- The 19h in-memory window ≠ the 8-day spend window. No durable bridge between them exists.

---

## Models by token volume (ranked as far as the data allows)

Per-model token volume is **not stored**. Best available evidence:

| Rank | Model | Evidence of volume | Tokens (per-model) | Requests | Spend (per-model) |
|---|---|---|---|---|---|
| 1 | **gpt-5.4** | **38/38** of the failover ring; the model the whole gpt-5.4 pool was exhausted serving | not separable | ≥38 failover reqs (+ likely most of the 108 openrouter clean serves) | not separable |
| — | (all others) | **zero** appearances in the ring in this window | — | — | — |

**Aggregate usage across ALL models (19h in-memory window):**
- tokens_in = **18,890,932** (18.89M)
- tokens_out = **80,580** (80.6k)
- cost_usd = **$7.462376** (real metered, == openrouter's metered cost)

Interpretation: because the ring is 100% gpt-5.4 and openrouter (which served that pool) accounts for essentially all serves and all cost, **gpt-5.4 was the de-facto sole model exercised** in this window — an **incumbent-under-test**, not a finalized workhorse choice (see the TL;DR framing caveat: no model is finalized for any tier; selection is pending real-code testing + the real-outcomes benchmark). Caveat: a model served cleanly with no failover would be invisible to the ring, so "others = zero" is **not provable** — but no counter-evidence exists.

---

## Per-provider reality (routing truth, 19h in-memory window)

| Provider | served | failed | errors | cost (real metered) | last_status | Reality |
|---|---|---|---|---|---|---|
| **openrouter** | **108** | 15 | 9 | **$7.4624** | 402 | The paid backstop — carried ~89% of serves and 100% of $. Now out of balance (402). |
| nanogpt | 12 | **38** | 6 | $0.0000 | 402 | High failure rate; mostly 402'd, offloaded to openrouter. $0 = free-tier/402 (no metered cost captured). |
| huggingface | 2 | 0 | 0 | $0.0000 | 200 | Marginal; free, healthy. Not in the gpt-5.4 pool. |
| **TOTAL** | **122** | — | — | **$7.4624** | — | |

Failover ring (38 events, all gpt-5.4): served_by openrouter=32, nanogpt=6. `cooldown_seconds = {}` (no active gateway cooldown).

**Per-provider MONTH spend: NOT available** — spend.json is a single aggregate. Only the 19h slice attributes cost to a provider (openrouter, $7.46). Providers with keys but no recent traffic (neuralwatt, deepseek, groq, cerebras, together, mistral, opencode-zen/-go) recorded **nothing** in-window.

---

## Usage shape
- **Single dominant model, no long tail** — gpt-5.4 is the load; no other model surfaced in-window.
- **Massively input-heavy: ~234:1 in:out** (18.89M in / 80.6k out; ~155k in-tokens & ~660 out-tokens per serve). Signature of a coding agent shipping large repo/context prompts for small completions (the SLOP/opencode/droid Build session).
- **Bursty, single-tenant** — traffic concentrated on one pool driven to exhaustion (both paid members hit 402), consistent with one heavy Build client rather than steady multi-model demand.
- **Cost concentration risk**: 100% of real $ ran through ONE provider (openrouter) on a **2-member pool** — a single balance event dries the whole model.

---

## Top-model → provider → model mapping (what's substitutable)

Live `gpt-5.4` routing and its substitutable variants (from `/charon/status` pools):

| Pool (model id) | Providers (ordered failover chain) |
|---|---|
| **gpt-5.4** (the in-window incumbent-under-test) | **[nanogpt, openrouter]** ← both paid, both currently 402 |
| gpt-5.4-go | [opencode-go] |
| gpt-5.4-ng | [nanogpt] |
| gpt-5.4-or | [openrouter] |
| gpt-5.4-mini / -nano | [nanogpt, openrouter] |
| gpt-5.4-pro | [openrouter] only |

Same-tier sibling models the cost analysis could substitute (all on the same thin `[nanogpt, openrouter]` chain unless noted):
- gpt-5.5, gpt-5.3-codex, gpt-5.2(-codex), gpt-5.1(-codex/-max/-mini), gpt-5(-codex)
- claude-opus-4-8 / -4-7 / …, claude-sonnet-4-6/-5, claude-haiku-4-5 → all `[nanogpt, openrouter]`
- glm-5.2, kimi-k2.6 → `[nanogpt, neuralwatt, openrouter, huggingface]` (wider, has free/non-balance members)
- `-go` variants → `[opencode-go]` (a distinct, non-balance-gated backend)

Note: nearly every non-free model shares the identical `[nanogpt, openrouter]` chain — so **the whole catalog shares gpt-5.4's single failure mode** (both paid members dry → pool dead). Widening thin pools with non-balance-gated members (opencode-go, huggingface) is the substitution lever.

---

## Confidence / coverage caveats
- **HIGH**: gpt-5.4 dominated traffic in-window (incumbent-under-test, not a finalized choice); openrouter served all paid traffic & 100% of $7.46 metered cost; input-heavy 234:1 shape; $221.84 month-to-date aggregate; the pool→provider mapping.
- **MEDIUM**: gpt-5.4 = "essentially the only" model — inferred from a failover-**only** ring + provider counts, not a per-model ledger; clean-serve traffic for other models could be invisible.
- **LOW / UNAVAILABLE**: exact per-model token volumes and per-model/per-provider **month** spend — **not recorded anywhere**. Do not fabricate a per-model $ split.
- **Window caveat**: the rich per-provider/token data is only ~19h (volatile, wiped on recreate). The only multi-day number is one aggregate scalar ($221.84), which includes est_cost for free serves → upper bound, not pure out-of-pocket.
- Provider account balances (openrouter/nanogpt hard-zero vs per-key cap) not queried — out of read-only-gateway scope.
