# Six-provider LIVE verification — neuralwatt, deepseek, groq, cerebras, together, mistral

Date: 2026-07-08 · Gateway 4-LOM `charon-gateway-1` v0.3.6 (f369b7c)
Method: isolated upstream probe from **inside the gateway container** (keys read from
`/data/secrets.json`, never printed). One `/models` call + ONE minimal
`chat/completions` (prompt "hi", `max_tokens:1`) per provider, direct to each
provider's own `base_url` — so this measures the PROVIDER, not gateway pool fallthrough.
No gateway routing involved. Total spend: ~6 tokens across all six.

## Results

| provider   | model tested                              | HTTP | works? | credit/balance signal | notes |
|------------|-------------------------------------------|------|--------|-----------------------|-------|
| neuralwatt | qwen3.5-397b (Qwen3.5-397B-A17B-FP8)      | 200  | YES    | **$22.00 budget remaining** (`X-Budget-Remaining-Usd: 22.00`, `X-Allowance-Remaining-Usd: 22.00`, energy 5.76) | Real completion returned. Explicit prepaid budget headers on every response. Best credit visibility of the six. |
| deepseek   | deepseek-v4-flash                         | 200  | YES    | **$9.93 balance** (`/user/balance`: total 9.93 USD, topped-up, `is_available:true`) | Prepaid; chat 200 + balance endpoint both confirm funds. Only 2 models exposed (v4-flash + one other). |
| groq       | llama-3.1-8b-instant                      | 200  | YES    | Free-tier rate limits healthy (14400 req/day, 6000 tok/min; 14399/5963 remaining) | 17 models. No $ balance concept — free tier, limited by rate not credit. |
| cerebras   | gpt-oss-120b                              | 200  | YES    | Free-tier rate limits healthy (5 req/min, 150/hr, 2400/day; 1M tok/day) | 3 models (incl gpt-oss-120b, llama-3.3-70b). Free tier — **tight 5 req/min cap**. No $ balance. |
| together   | meta-llama/Llama-3.3-70B-Instruct-Turbo   | 200  | YES    | Key valid, 271 models accessible; no balance header exposed | First model guess (3.2-3B) 400'd (non-serverless); 70B-Turbo serverless works. Together is prepaid — 200 implies usable funds/free-credit, exact $ unknown (no cheap balance endpoint). |
| mistral    | mistral-small-latest                      | 200  | YES    | Rate limits healthy (50k tok/min, 50 req/min; 49983/49 remaining) | 70 models. Real "Hello" completion. No $ balance header; limits suggest active (free or paid) tier. |

### Cloudflare false-negative caught (important)
First pass, **groq / cerebras / together all returned HTTP 403 "error code: 1010"** —
a Cloudflare bot-block on the default `Python-urllib` User-Agent, NOT an auth/credit
failure. Re-running with a normal browser User-Agent, all three returned **200**.
Implication: any Charon health-check or client hitting these three with a
urllib/default UA will get spurious 403s. The live gateway proxy path should be
checked to confirm it sends a browser-like UA (or these providers will look "dead"
when they are healthy). This is the single actionable risk found.

## Conclusion — usable stack additions

**All six are CONFIRMED live right now (every one returned a real 200 completion).**
Funding/usability tier:

- **Funded with real $ balance (can carry paid traffic now):** neuralwatt ($22.00),
  deepseek ($9.93). These two are the strongest additions — money on account + working.
- **Live on free/rate-limited tiers (usable, no $ balance, capped by rate):** groq
  (generous: 14.4k req/day), mistral (50k tok/min), together (271 models, prepaid/credit,
  balance unknown but serving), cerebras (works but **5 req/min** is a hard throttle —
  fine for spillover, not primary bulk traffic).

Net: the active-provider inventory's "health unverified" for these six can be closed as
**all six HEALTHY**. neuralwatt + deepseek are drop-in funded capacity; groq/mistral/
together add solid free/credit headroom; cerebras is usable but rate-capped.
Fix/verify the User-Agent on the gateway's outbound path so groq/cerebras/together
don't get Cloudflare-1010'd in production.
