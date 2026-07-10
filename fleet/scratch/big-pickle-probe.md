# big-pickle live-gateway probe — 2026-07-07

**Verdict: big-pickle = WORKS-FREE right now.** It does not need OpenCode Zen funded.
Other paid Zen models are correctly 401ing (confirms the reported outage is real) —
big-pickle is specifically exempt from the negative-balance gate on Zen's side.

## Method

- SSH'd to 4-LOM (`stack@10.0.1.60`), read `CHARON_GATEWAY_TOKEN` via
  `docker exec charon-gateway-1 printenv` (no sudo needed — user is in the docker group;
  value never printed to logs/output).
- Hit the published gateway directly: `POST http://localhost:8080/v1/chat/completions`
  from the 4-LOM host, `max_tokens` 3–40, no config changes made.
- Cross-checked routing against `/data/pools.json` and `/data/models.json` inside the
  container (mounted from `charon_charon-config` volume) to know which provider each
  call actually hit.

## Pool-shape discovery (matters for interpreting results)

`big-pickle`'s pool is `["big-pickle", "big-pickle-go"]` — the bare id routes straight
to provider `opencode-zen` (models.json: `{"provider":"opencode-zen","free":false}`).
This direct-to-zen shape (own id first in its own pool, no nanogpt/openrouter member)
is **rare** — only two models have it: `big-pickle` and `gpt-5.3-codex-spark`.

Every other "-free" named Zen-family model (`mimo-v2.5-free`, `deepseek-v4-flash-free`,
`qwen3.6-plus-free`, `minimax-m3-free`, `nemotron-3-ultra-free`,
`north-mini-code-free`) has a pool of **only** `-go/-ng/-or` members — none of them
route to bare/zen directly. So `mimo-v2.5-free` does NOT test Zen health; it's served
by nanogpt (`-ng`) every time. Swapped the "control for any-free-zen-works" test to
`gpt-5.3-codex-spark`, the only other model sharing big-pickle's direct-zen pool shape.

## Results

### 1. `big-pickle` (zen-direct)
```
HTTP_STATUS: 200
{"model":"big-pickle","choices":[{"finish_reason":"length",
  "message":{"content":"","reasoning_content":"We are asked: \"Reply with just: yes\"...
  So the response should be exactly \"yes\"."}}],
 "usage":{"prompt_tokens":88,"completion_tokens":20,...},"cost":"0"}
```
Real completion (reasoning_content populated, deepseek/zen-style
`prompt_cache_hit_tokens` usage schema), `cost: "0"`. Reproduced twice, consistent.

### 2. `gpt-5.3-codex-spark` (zen-direct, same pool shape — best available "does any
   other zen route work" control; the literal `-free` models don't touch zen at all,
   see above)
```
HTTP_STATUS: 503
{"error":{"message":"all providers exhausted","type":"all_providers_exhausted",
 "failover_reasons":["opencode-zen=401","opencode-go=401"]}}
```
Confirms: OpenCode Zen genuinely 401s across the board for this model — the reported
negative-balance outage is real and reproducible live. `opencode-go` (big-pickle-go's
provider) also 401s and isn't in `providers.json`'s configured provider list anyway
(`opencode-zen`, `openrouter`, `neuralwatt`, `cerebras` — `opencode-go` is effectively
unconfigured/dead weight).

### 3. `gpt-5.4-ng` (non-zen control, nanogpt-backed)
```
HTTP_STATUS: 200
{"model":"openai/gpt-5.4","choices":[{"message":{"content":"Hi! How can I help?"}}],
 "x_nanogpt_pricing":{"cost":0.000173...}}
```
Normal paid success via nanogpt, as expected — gateway and non-zen providers are
healthy.

## Conclusion

- **big-pickle is genuinely free and working today**, served directly by
  `opencode-zen`, `cost: "0"` per response, no funding needed for this specific model.
- OpenCode Zen's account-level outage (negative balance → 401) is real and confirmed
  live against another zen-direct model (`gpt-5.3-codex-spark`) — so the broader "401ing
  across the board" report is accurate for paid/gated Zen models.
- big-pickle appears to be carved out from that gate on Zen's side (a genuinely
  free-tier model independent of account balance) — it is the exception, not proof the
  whole Zen account is fine.
- The nominal "-free" named Zen-family models (mimo-v2.5-free etc.) currently have
  **no working path to Zen at all** in this deployment's pool config — they only ever
  resolve to nanogpt/openrouter members. That's a separate, pre-existing pool-config
  gap worth a ticket if the intent was for those to actually hit Zen's free tier.

No gateway config, secrets, or state were modified during this probe.
