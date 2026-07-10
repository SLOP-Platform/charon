# owl-alpha add — STOPPED at Step 1 (slug retired, zero live endpoints)

Date: 2026-07-07 (4-LOM: `ssh -i ~/.ssh/4lom stack@10.0.1.60`, container `charon-gateway-1`)

## Outcome

**STOP. No config changes made. No backup needed (nothing was written).**

## Step 1 — catalog + live probe (read-only, no writes)

1. Fetched the live OpenRouter catalog (`GET /api/v1/models`, via curl over ssh
   from the 4-LOM host — 343 models returned). Searched case-insensitively for
   `owl`, `longcat`, `stealth`, `alpha`: **zero matches**. `owl-alpha` is not in
   the general model listing.

2. The user's guessed slug `openrouter/owl-alpha` does still exist as a
   *registered model definition* — `GET /api/v1/models/openrouter/owl-alpha/endpoints`
   returns 200 with real metadata (`"name":"Owl Alpha"`, the same "high-performance
   foundation model designed for agentic workloads" description referenced in
   press coverage) but **`"endpoints": []`** — no provider is currently serving it.

3. Decisive live probe: used the gateway's own already-configured
   `OPENROUTER_API_KEY` (read from `/data/secrets.json` on the running
   container, not modified) to POST a real `chat/completions` request to
   `https://openrouter.ai/api/v1/chat/completions` with
   `"model":"openrouter/owl-alpha"`. Result:
   ```
   HTTP 404
   {"error":{"message":"No endpoints found for openrouter/owl-alpha.","code":404}}
   ```
   Confirmed dead — not a transient/rate-limit error, an explicit "no endpoints"
   404 from OpenRouter itself.

## Context (why it's gone) — soft signal, not required for the STOP decision

Web search corroborates the task's own hypothesis: OpenRouter ran an anonymous
stealth slot called "Owl Alpha" (1M context, agentic/tool-use focus, no lab
attributed) for roughly two months (~May–June 2026). On **2026-06-30**, Meituan
publicly unveiled **LongCat-2.0** (1.6T-param MoE, ~48B active, MIT license,
DeepSeek-style sparse attention, 1M context) and multiple outlets (VentureBeat,
Decrypt, KuCoin, Yahoo/Decrypt syndication) reported LongCat-2.0 as the model
behind Owl Alpha. This is third-party reporting, not something Charon verified
against the model itself — model self-ID is unreliable and moot here anyway
since the slot no longer serves at all. It's consistent with: once unmasked,
OpenRouter retired the anonymous stealth alias (the model definition record is
still there for historical/link purposes, but with the endpoint list emptied).

Sources (background only):
- https://x.com/OpenRouter/status/2049864339570757920
- https://openrouter.ai/openrouter/owl-alpha
- https://venturebeat.com/technology/meituan-open-sources-longcat-2-0-the-1-6t-near-frontier-agentic-coding-model-thats-been-leading-openrouter-trained-entirely-on-chinese-chips
- https://decrypt.co/372579/longcat-2-0-meituan-ai-stealth-model-openrouter
- https://dayverse.id/en/articles/true-identity-of-owl-alpha-on-openrouter-revealed/

## What was NOT done (per STOP-on-error instruction)

- No `/data/*.json` backup taken (no writes were planned or made, so no
  data-loss risk existed to guard against).
- No `/charon/models` or `/charon/pools` POST issued.
- No `owl-alpha` alias added to the live gateway's `models.json`/`pools.json`.
- No self-ID / capability sanity probe run (nothing to probe — the model has
  no live endpoint to call).
- `~/.config/opencode/regen-charon-models.sh` NOT re-run (nothing changed to
  regenerate for).

## Recommendation

If a real LongCat-2.0 route is still wanted, it should go through Meituan's
own OpenAI-compatible endpoint or a labeled OpenRouter entry if one appears
under a proper (non-stealth) slug later — that would be a new, separate task
with its own honest curated id (e.g. `longcat-2.0`, correctly labeled, not
"owl-alpha"). Re-check `https://openrouter.ai/api/v1/models` periodically;
if a labeled LongCat entry shows up with non-empty `endpoints`, that's the
signal to revisit.
