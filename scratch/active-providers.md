# Charon active providers — live snapshot (READ-ONLY)

Date: 2026-07-08 · Gateway: 4-LOM `charon-gateway-1` v0.3.6 (build f369b7c)

## Definitions / method
- **Active** = referenced in the live routing pools AND has a working credential
  present (secret set) AND not in an active gateway cooldown right now.
- Credentials live in `/data/secrets.json` (mode 600); `key present` = the provider's
  `key_env` has a non-empty value there. No key values were read or printed.
- Provider base_url/key_env resolve from the built-in preset registry
  (`src/charon/providers.py::PRESETS`) plus `/data/providers.json` overrides.
- Health from `GET /charon/status` (`providers` last_status + `cooldown_seconds`).
  `cooldown_seconds` was **`{}`** at snapshot → NO provider is cooled/sidelined now.

## ACTIVE providers (11) — configured + key present + in pools + not cooled
| provider    | enabled | key present | key_env (secret) | health now |
|-------------|---------|-------------|------------------|------------|
| openrouter  | yes | yes | OPENROUTER_API_KEY | **DEGRADED — last_status 402 (out of balance)** |
| nanogpt     | yes | yes | NANOGPT_API_KEY    | **DEGRADED — last_status 402 (out of balance)** |
| huggingface | yes | yes | HF_TOKEN           | HEALTHY — last_status 200 |
| opencode-zen| yes | yes | OPENCODE_ZEN_KEY   | active; no recent traffic (health unverified) |
| opencode-go | yes | yes | OPENCODE_ZEN_KEY (shared w/ zen) | active; no recent traffic (health unverified) |
| neuralwatt  | yes | yes | NEURALWATT_API_KEY | active; no recent traffic (health unverified) |
| deepseek    | yes | yes | DEEPSEEK_API_KEY   | active; no recent traffic (health unverified) |
| groq        | yes | yes | GROQ_API_KEY       | active; no recent traffic (health unverified) |
| cerebras    | yes | yes | CEREBRAS_API_KEY   | active; no recent traffic (health unverified) |
| together    | yes | yes | TOGETHER_API_KEY   | active; no recent traffic (health unverified) |
| mistral     | yes | yes | MISTRAL_API_KEY    | active; no recent traffic (health unverified) |

Notes:
- No `disabled_providers` / skip-list observed; `fallback` chain is empty (`[]`).
- **opencode-go shares OPENCODE_ZEN_KEY** (preset `providers.py:42-44`) — it is active
  even though it has no standalone secret; it backs 43 `-go` pools.
- MISTRAL_API_KEY is set and mistral is referenced in 1 pool → counted active, though
  it is a very thin footprint.
- The two DEGRADED providers (openrouter, nanogpt) are still "active" by
  configuration/credential/not-cooled, but are currently returning 402 and cannot serve
  paid models until balance is restored. They back the largest share of pools
  (openrouter in 98 pools, nanogpt in 93), so this is high-blast-radius.

## CONFIGURED-but-INACTIVE / not-in-service
- **Preset-available, NO key, NOT in pools** (available to add, not active): zai, chutes,
  fireworks, sambanova, replicate, xai, cohere, openai, perplexity, and the local
  presets lmstudio / jan / ollama / vllm / local. Reason: no credential in secrets.json
  and not referenced by any pool.
- `/data/providers.json` explicitly defines only 4 (opencode-zen, openrouter, neuralwatt,
  cerebras); the other active providers resolve purely via the preset registry + secret.

## Plain active list (inline)
openrouter, nanogpt, huggingface, opencode-zen, opencode-go, neuralwatt, deepseek, groq, cerebras, together, mistral

(Caveat: openrouter and nanogpt are active-but-DEGRADED — both returning 402 out-of-balance right now.)
