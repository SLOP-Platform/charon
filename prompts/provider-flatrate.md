# PROVIDER-FLATRATE — Add featherless.ai + cost-optimized provider config

## Why

The gateway currently has no truly flat-rate ($/month, unlimited tokens) OpenAI-compatible provider
except NanoGPT. featherless.ai offers $25/mo unlimited access to 40,000+ HuggingFace models with a
standard OpenAI-compatible endpoint. This is the missing flat-rate anchor for the "try free/flat first,
then cheapest per-token, then frontier" pool configuration.

Additionally, DeepInfra and Cerebras are ultra-cheap per-token providers not yet in PRESETS.
SiliconFlow is cheap but per-token only — optional add.

## What to do

### 1. Add provider presets

Add to `src/charon/providers.py` PRESETS dict:

```python
"featherless": ProviderPreset(
    "https://api.featherless.ai/v1", "FEATHERLESS_API_KEY",
    note="Featherless.ai — flat-rate $25/mo unlimited tokens across 40,000+ HuggingFace "
         "open-weight models. OpenAI-compatible. Model IDs use org/model format "
         "(e.g., deepseek-ai/DeepSeek-V3). Get key at https://featherless.ai/dashboard."),

"deepinfra": ProviderPreset(
    "https://api.deepinfra.com/v1/openai", "DEEPINFRA_TOKEN",
    note="DeepInfra OpenAI-compatible endpoint. Pay-per-token (very cheap — "
         "~$0.05–$0.50/M tokens). Some models free. Model IDs use org/model format. "
         "Get key at https://deepinfra.com/dashboard."),

"cerebras": ProviderPreset(
    "https://api.cerebras.ai/v1", "CEREBRAS_API_KEY",
    note="Cerebras — fastest Llama inference available (1,800+ tok/s). Free tier + "
         "pay-per-token. Get key at https://cloud.cerebras.ai."),
```

### 2. Validate preset URLs

Run `charon providers test` for each new provider. Mark base URLs as verified or unverified in the
`note:` field. Providers whose `/models` endpoint returns 200 (or 401 — needs key) are considered
verified; providers that 404 or timeout need investigation.

### 3. Recommended cost-optimized pool configuration

Document (not auto-configure) the recommended tier/pool setup. This is guidance for the operator,
not code — the gateway doesn't auto-create pools.

**Tier 1: `low` (free-only)**
```bash
charon models import openrouter --free-only --into-pool low
```
Gets all OpenRouter `:free` models (Gemini Flash, Llama, Qwen free variants) + Groq free tier.

**Tier 2: `med` (flat-rate + ultra-cheap)**
```
pool members (in order):
  1. featherless/<best-coding-model>     # flat-rate $25/mo — always try first
  2. groq/llama-4-scout-17b              # free tier, blazing fast
  3. deepinfra/<cheapest-coding-model>   # ~$0.05/M input
  4. deepseek/deepseek-chat              # ~$0.27/M input
  5. cerebras/llama-4-maverick           # fastest, cheap
  6. openrouter/qwen3-coder              # strong coding, ~$0.40/M
```

**Tier 3: `high` (frontier)**
```
pool members (in order):
  1. openrouter/claude-sonnet-4          # best coding quality
  2. openrouter/gpt-4o                  # strong generalist
  3. openrouter/gemini-2.5-pro          # Google's best
```

**Global fallback:**
```bash
charon fallback set --providers openrouter,groq,deepseek,featherless
```

### 4. SiliconFlow (optional)

Per-token only, not flat-rate. If added:
```python
"siliconflow": ProviderPreset(
    "https://api.siliconflow.com/v1", "SILICONFLOW_API_KEY",
    note="SiliconFlow — per-token pay-as-you-go. 200+ models. GPT-OSS-120B at "
         "$0.05/M input is notable. Get key at https://cloud.siliconflow.com."),
```

## Providers investigated and rejected

| Provider | Reason |
|---|---|
| synthetic.net (all URLs including dev.synthetic.net) | Unreachable — transport error on all endpoints |
| useapiary.com | B2C chat web app, no developer API, no OpenAI-compatible endpoint |
| Ollama cloud | Already in presets (local); cloud is usage-based GPU time, not flat-rate |

## Hard constraints

- No secret values in presets (key_env only — operator supplies the key)
- All base URLs must be reachable (verified live or marked unverified with note)
- `strip_v1=True` for all three (bases end in /v1 or analogous version segment)
- `downgrade_prone=False` for all (direct providers, not aggregators)
- Gate GREEN: `PYTHONPATH=src python3 -m pytest -q ; ruff check ; mypy src tests`

## Acceptance

- All 3 new presets present in `providers.py` PRESETS dict
- `charon providers list` shows featherless, deepinfra, cerebras
- `charon providers test featherless` succeeds (or reports expected 401 — needs key)
- Existing tests pass; no regression in provider resolution
- Each preset has a `note:` documenting pricing model and key source

## REPORT BACK — MECHANIZED FORMAT (required)
End your session by emitting EXACTLY this block. Fixed fields, one line each, no diffs or logs.
Validate it before you finish: `bash /home/stack/charon-private/fleet/check-session-report.sh <file>`
Full spec + rationale: `/home/stack/charon-private/fleet/SESSION-REPORT-FORMAT.md`

```
=== SESSION REPORT v1 ===
TICKET:       <ticket-id>
SESSION:      <jedi-name> | <model>
STATUS:       DONE | BLOCKED | REFUSED | PARTIAL
COMMIT:       <sha> | none
FILES:        <n> changed: <paths>
OWNS-OK:      yes | NO — <file> is owned by <ticket>
GATE:         PASS | FAIL — <detail>
TESTS:        <n> passed, <n> failed, <n> skipped
RED-PROOF:    broken=<exit> green=<exit> | n/a — <why> | NOT-DONE
OBSERVABLE:   MET | DEFERRED — <what could not be observed and why>
RAN:          <what you proved by EXECUTING>
READ:         <what you concluded by READING only>
BRIEF-ERRORS: none | <what this brief got factually wrong>
BLOCKED-BY:   none | <ticket or condition>
NEXT:         <the single thing the manager should do next>
=== END REPORT ===
```
**Emit it even if you are BLOCKED or REFUSED — especially then.** A correct refusal is the most
valuable report there is; a silent exit is worth nothing. **BRIEF-ERRORS is not optional politeness**
— on 2026-07-26 sessions caught nonexistent files in an OWNS clause, a ticket whose work already
existed, and a wrong premise about `upstream_model`. The brief is wrong more often than the session is.
