# Charon Provider Cost / Routing Rationalization

READ-ONLY investigation. Live box `10.0.1.60`, container `charon-gateway-1`, config in `/data`. Source at `/home/stack/code/charon/src/charon`. Date 2026-07-09.

---

## Q1 — The $223 is almost entirely FICTIONAL

**Verdict: ~100% of `spent_usd=223.28` is a synthetic estimate, not real money. Real Charon-computed metered cost = $0.**

### The mechanism (file:line)
1. **Nothing in `models.json` carries per-token pricing.** Every one of the ~200 model entries has only `free`/`cost_rank`/`provider`/`upstream_model` — no `cost_input`/`cost_output`. The gateway builds `model_pricing` from exactly those keys (`gateway.py:290` — `{k: spec[k] for k in ("cost_input","cost_output","free")}`), so every entry ends up as `{"free": true|false}` with **no rates**.
2. **So the real-cost path can never fire.** In `proxy.py:330-349`, when the provider reports `cost_usd==0` it tries to compute `tokens_in*ci + tokens_out*co`; with `ci/co = None` it falls to `cost_source="unpriced"` and `cost` stays `0`.
3. **The killer line — `forwarder.py:315` and `:400`:**
   ```python
   srv.spend_limiter.record(cost if cost > 0 else est_cost)
   ```
   Whenever the real cost is `0` (which is ALWAYS here — free tier, flat plan, or unpriced), Charon records `est_cost` instead.
4. **`est_cost` is a fabricated floor** (`forwarder.py:140-141` → `proxy_response.py:52-62`): `est_tokens = max(len(raw_body)//4, 100)`, and with no rates it returns `est_tokens * 0.0000015` — i.e. **$1.50 per million bytes/4 of the REQUEST body**, counted on every served response, ignoring output, ignoring free/flat status.

### Proof the provider's real cost is being discarded
Live probe of NanoGPT (`deepseek/deepseek-v4-pro`) returns HTTP 200 and **explicitly reports `"cost":0, "costUsd":0, "usdCost":0`** (flat-plan). Charon sees `cost==0`, treats it as "unknown", and bills the `est_cost` floor anyway. The provider is telling the truth ($0 on a flat plan) and Charon overwrites it with a made-up number.

### Quantify fictional vs real
- **Charon-computed metered charges: $0.00** (no rates, no provider cost>0 ever observed).
- **The full $223.28 is the `est_cost` floor accumulated across every served request** — including STREAMED requests (the streaming path `forwarder.py:398-400` records spend but does NOT touch the quality counter at `:312`), so the true number of billed requests is far larger than the 110 calls in `quality.json`. Agentic coding resends full context each turn → multi-MB bodies → dollars of phantom spend per request.
- **Operator's actual monthly cost:** NanoGPT $12 flat + NeuralWatt $20 flat = **$32**, plus small prepaid pay-as-you-go on deepseek / openrouter / together / mistral. Nowhere near $223.

### Why it diverges from the $12 NanoGPT flat plan
NanoGPT is flat/prepaid and reports `cost:0` per call. Charon throws that 0 away (`cost if cost > 0 else est_cost`) and substitutes `(request_bytes/4) * $1.5e-6` per served request. It is structurally blind to (a) flat subscriptions and (b) free tiers — both surface as `cost==0` and both get the phantom floor.

### Double-count check
No per-request+per-provider double count in the current code; the SR-1 namespaced-id double-bill is fixed (`_normalize_model_id`, `proxy.py:247`). The inflation here is the est_cost-fallback, not double counting.

**FIX (needs ticket):** `record()` must not substitute `est_cost` when the provider reported a real $0 or the model is a known free/flat provider. Distinguish `cost_source in {"free","provider(0)"}` (record 0) from genuinely `unpriced`. Ideally suppress spend accounting entirely for flat-subscription providers (nanogpt, neuralwatt). After fix, reset `spend.json` (`spent_usd` 223.28 → 0).

---

## Q2 — NanoGPT vs cline-pass as cheap-first on the 5 pools

Pools where `cline-pass` (cost_rank **1**) currently drains first, nanogpt below it: `glm-5.2`, `kimi-k2.6`, `deepseek-v4-pro`, `deepseek-v4-flash`, `minimax-m3-free`.

| | NanoGPT | cline-pass |
|---|---|---|
| Quality | 46/46 (1.0) | 11/11 (1.0) |
| OpenAI-shaped | Yes (verified 200, correct model echo) | via gateway yes (11/11); direct probe to guessed path 404'd |
| Marginal cost | ~$0 (flat $12/mo already paid) | subscription (Cline pass) — cost unknown |
| Model-id echo | Clean (`deepseek/deepseek-v4-pro` → matches) | n/a here |
| Compat risk | None observed | operator-reported broken non-streaming envelope; could not independently confirm/deny (my direct non-streaming probe 404'd on the guessed `/api/chat/completions`) |

**Recommendation: promote NanoGPT to cheap-first on all 5 pools** (or, equivalently, bump `cline-pass` cost_rank above nanogpt until its non-streaming envelope is verified). Rationale: nanogpt's marginal cost is $0 on the flat plan, it's the most-proven leg (46/46), it echoes the correct model id (no false-downgrade), and once the Q1 bug is fixed its spend will correctly read ~$0. Keep cline-pass as the spill leg — its 11/11 is real but its non-streaming compat is unverified and its subscription value is only realized if it actually serves.

Per-pool (set nanogpt leg as drain-first, cline as spill):
- `deepseek-v4-pro`: order `-ng`(flat) → `-ds` → `-or`, cline last until verified.
- `deepseek-v4-flash`: `-ng` → `-ds`/`-hf` → cline spill.
- `glm-5.2`: `-ng` → `-hf`/`-or` → cline/nw spill.
- `kimi-k2.6`: `-ng` → `-hf`/`-or` → cline/nw spill.
- `minimax-m3-free`: `-ng` → `-or` → cline spill.

---

## Q3 — NeuralWatt: NOT actually failing; the $20/mo is redundant

**The 0/4 is a FALSE failure.** Live probes today:
- `GET /v1/models` → 200 (full catalog with pricing).
- `POST /v1/chat/completions model=kimi-k2.7-code` → **200**, returns `model:"moonshotai/Kimi-K2.7-Code"`.
- `POST … model=glm-5.2` → **200**, returns `model:"zai-org/GLM-5.2-FP8"`.

**Root cause of the mis-score:** `_normalize_model_id` (`proxy.py:247`) is **case-sensitive and does not strip quant suffixes** — it only takes the final path segment. So:
- expected `kimi-k2.7-code` vs returned `Kimi-K2.7-Code` → mismatch (case) → `pseudo_success`.
- expected `glm-5.2` vs returned `GLM-5.2-FP8` → mismatch (case + `-FP8`) → `pseudo_success`.

A `pseudo_success` is recorded as a quality FAILURE (`forwarder.py:312-313`, `success=not obs.pseudo_success`). So NeuralWatt works but is scored 0/4 and served with a spurious `X-Charon-Downgrade` header. **This bug hits ANY provider that returns a quant/case-variant id.**

**Pool dependency (grep `pools.json`):** NeuralWatt appears in 3 pools — `auto` (`paid-neuralwatt-code`), `glm-5.2` (`glm-5.2-nw`), `kimi-k2.6` (`kimi-k2.6-nw`). **No pool depends on it solely** — each has nanogpt/cline/openrouter/hf legs (`auto` also has free-groq/free-cerebras/deepseek/minimax). **Cancelling $20/mo breaks nothing.**

**Verdict — operator decision:** NeuralWatt is redundant (GLM-5.2 + Kimi-K2.6 already covered by nanogpt flat $12 + cline + openrouter + hf). Recommend **CANCEL to save $20/mo**, unless the operator specifically wants its speed/energy angle — in which case **fix the normalize bug** so it stops reading as 0/4. Either way the normalize bug should be fixed (it silently corrupts scoring/serving for quant variants).

---

## Q4 — Provider-value table

Costs: NanoGPT $12/mo flat, NeuralWatt $20/mo (given). opencode-zen prepaid ~$10 (`balance.py:150`). cline-pass = Cline subscription (cost unknown). deepseek/openrouter/together = prepaid pay-as-you-go. groq/cerebras/mistral/huggingface = free/PRO tiers.

| Provider | $/mo to operator | Calls | Success | OpenAI-shaped | Role | Verdict | Rationale |
|---|---|---|---|---|---|---|---|
| **nanogpt** | $12 flat | 46 | 46/46 | Yes | Primary leg on nearly all frontier pools; spill on the 5 cheap pools | **KEEP + promote** | Flat fee = $0 marginal; most proven; clean id echo. Make cheap-first (Q2). |
| **neuralwatt** | $20 flat | 4 | 0/4 (FALSE) | Yes | Extra GLM-5.2/Kimi leg + paid-neuralwatt-code in `auto` | **DROP** (operator decision) | Actually works; redundant. Cancel $20/mo, or keep+fix normalize. Paid-but-effectively-unused (mis-scored, downgrade-served). |
| **cline-pass** | Cline sub (unknown) | 11 | 11/11 | via gateway yes | Drain-first (rank 1) on 5 pools | **REPRIORITIZE** | Verify non-streaming envelope; until then demote below nanogpt. Confirm the subscription cost is worth it. |
| **openrouter** | prepaid PAYG | 10 | **1/10** | Yes | 2nd leg (`-or`) on almost every pool | **INVESTIGATE / REPRIORITIZE** | Paid-but-mostly-failing. 9 failures — check credits/model-id/402s on the `-or` legs. |
| **opencode-go** | (opencode) | 6 | 4/6 | Yes | Global fallback (`fallback.json`) + `-go` free legs | **KEEP** | Fallback safety net; moderate reliability. |
| **opencode-zen** | prepaid ~$10 | 6 | 6/6 | Yes | Bare-id catalog provider — **but bare ids are NOT in any pool** (pools use `-ng`/`-or`) | **REPRIORITIZE / reconcile** | Prepaid but largely unreferenced by current pools; confirm it's still wanted or let the balance run down. |
| **groq** | free tier | 7 | 7/7 | Yes | `free-groq` in `auto` + gpt-oss legs | **KEEP** | Free, perfect reliability. |
| **cerebras** | free tier | 4 | 4/4 | Yes | `free-cerebras` in `auto` | **KEEP** | Free, reliable. |
| **mistral** | free tier | 2 | 2/2 | Yes | `free-mistral-code` (codestral) | **KEEP** | Free. |
| **together** | prepaid PAYG | 5 | 5/5 | Yes | `minimax-m3-together` + minimax pools | **KEEP** | Works; small metered cost. |
| **huggingface** | free/PRO (HF_TOKEN) | 7 | 6/7 | Yes | glm/kimi/deepseek `-hf` legs | **KEEP** | Cheap/free; moderate reliability. |
| **deepseek** | prepaid PAYG | 2 | 2/2 | Yes | `-ds` legs (cheap deepseek) | **KEEP** | Cheap, works. |

**Flags:** openrouter = paid-but-failing (1/10). neuralwatt = paid-but-(falsely)-failing + redundant. opencode-zen = prepaid but not wired into any pool.

---

## Prioritized recommendations

1. **FIX the est_cost billing bug (ROOT CAUSE of $223)** — `forwarder.py:315,400`. Stop substituting `est_cost` when the provider reported real $0 or the model is free/flat. After fix, reset `spend.json` to 0. **[needs ticket]**
2. **FIX `_normalize_model_id` case/quant-suffix** — `proxy.py:247`. Lowercase + strip quant suffixes (`-FP8`, etc.) so quant/case variants (NeuralWatt, others) aren't false-flagged as downgrades — this corrupts quality scores and serves spurious `X-Charon-Downgrade`. **[needs ticket]**
3. **NeuralWatt $20/mo — OPERATOR DECISION**: cancel (redundant, nothing breaks) OR keep and rely on fix #2. It actually works today.
4. **Promote NanoGPT to cheap-first** on the 5 cline-first pools (flat fee, 46/46, clean id echo); demote cline-pass to spill until its non-streaming envelope is verified.
5. **Investigate OpenRouter 1/10** — paid, mostly failing on the `-or` legs (credits / model-id / 402s).
6. **Reconcile opencode-zen** — prepaid but unreferenced by any pool; decide keep-vs-drain.

**Requires operator decision:** #3 (cancel NeuralWatt $20/mo), #4 (accept cline-pass demotion / confirm its subscription value), and confirming the spend.json reset after #1.
