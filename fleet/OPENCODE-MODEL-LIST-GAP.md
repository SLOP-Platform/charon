# opencode `/model` list gap — investigation (2026-07-05)

## TL;DR

The Charon Gateway is fine. opencode's `/model` picker only shows the 14
models hand-typed into `~/.config/opencode/opencode.json`'s
`provider.charon.models` map, out of 199 the gateway actually routes.
opencode does not auto-discover models for custom OpenAI-compatible
providers — every model id must be manually listed in the config. This is
an **opencode-config gap, not a Charon product bug**.

## 1. What the gateway exposes

Queried live on 4-LOM (`charon-gateway-1`, port 8080) with the container's
own `CHARON_GATEWAY_TOKEN`:

```
GET /v1/models  ->  200 OK, "data": [...199 entries...]
```

The 199 ids returned exactly match the keys of `/data/models.json` on the
container (all concrete, routable model ids — canonical names like
`gpt-5.4`, `claude-opus-4-8`, `deepseek-v4-pro`, plus provider-suffixed
variants `-go` (Google/Gemini-relay), `-ng` (NeuralWatt), `-or`
(OpenRouter), `-ds` (DeepSeek direct), `-nw`, `-groq`, plus free-tier ids
like `deepseek-v4-flash-free`, `mimo-v2.5-free`, `nemotron-3-ultra-free`,
`north-mini-code-free`, `free-cerebras`, `free-groq`, `free-mistral-code`).

`/data/pools.json` maps each canonical model name to its ordered fallback
chain (e.g. `"gpt-5.4": ["gpt-5.4","gpt-5.4-go","gpt-5.4-ng","gpt-5.4-or"]`)
plus one special virtual pool, `"auto"`, that is *all* top-tier canonical
models. So `pools.keys()` is basically `routes.keys() ∪ {"auto"}`.

Code path — `src/charon/proxy_server.py` lines ~577-597, handler for
`GET /v1/models` / `/models`:

```python
pool_only = set(srv.pools.keys()) - set(srv.routes.keys())
exposed = [m for m in srv.model_ids if m not in pool_only]
```

This is a documented, deliberate design decision (comment cites
"MODEL-DISCOVERY"): pool **virtual** ids that aren't also concrete routes
are excluded from `/v1/models` because they're routing concepts, not real
models to bill/select directly. In the current config the only such id is
`"auto"` — every other pool key (`gpt-5.4`, `claude-opus-4-8`, ...) is
also a real route, so it stays in. Net effect: **the gateway already
enumerates all 199 concrete routable models via `/v1/models`.** This part
of the pipeline is working as designed — there is no gateway-side
completeness bug here.

`model_ids` itself is built in `src/charon/gateway.py:288`:
`model_ids=sorted(set(routes) | set(pools))`, then passed through to the
proxy server (`gateway.py:409`).

## 2. What opencode shows

Config: `~/.config/opencode/opencode.json` (this workstation — opencode
runs as a local client here, pointed at the gateway over LAN; it does not
run on 4-LOM itself).

```json
"provider": {
  "charon": {
    "npm": "@ai-sdk/openai-compatible",
    "options": { "baseURL": "http://10.0.1.60:8080/v1", "apiKey": "..." },
    "models": {
      "deepseek-v4-pro": {...}, "gpt-5.4-mini": {...}, "auto": {},
      "gpt-5.5": {}, "gemini-3.1-pro": {}, "glm-5": {}, "qwen3.6-plus": {},
      "glm-5.2": {}, "deepseek-v4-flash": {}, "deepseek-v4-flash-free": {},
      "kimi-k2.6": {}, "minimax-m3-free": {}, "mimo-v2.5-free": {},
      "nemotron-3-ultra-free": {}
    }
  }
},
"model": "charon/gpt-5.4"
```

Only **14** model ids are declared (13 unique — `deepseek-v4-pro` is
listed twice, harmless dedup). opencode's `/model` command populates its
picker **only from this static map** — confirmed against opencode docs:
for a custom `@ai-sdk/openai-compatible` provider, opencode does **not**
auto-discover from the provider's `/v1/models` endpoint. Built-in
providers (OpenAI, Anthropic, etc.) get AI-SDK-native auto-discovery;
custom OpenAI-compatible providers require every model id to be
hand-listed in `provider.<name>.models`. There is no config flag to turn
on dynamic discovery.

Note also: `"auto"` is listed in opencode's static config even though the
gateway's `/v1/models` deliberately omits it (§1) — it still works as a
request-time model id because the router handles pool names specially;
it's just invisible to anything that tries to derive the list from
`/v1/models` output rather than reading `pools.json` directly.

## 3. The gap

- Gateway-routable concrete models: **199**
- Shown in opencode `/model`: **13** (deduped)
- Missing: **186** models, including entire families never surfaced at
  all in opencode (e.g. every `gpt-5.1*`/`gpt-5.2*`/`gpt-5.3*` codex
  variant, every `claude-opus-4-*`/`claude-sonnet-4-*` id, `grok-build-0.1`,
  `big-pickle`, `kimi-k2.5`, `minimax-m2.*`, all `-go`/`-ng`/`-or`/`-ds`
  provider-pinned variants, `free-cerebras`, `free-groq`,
  `free-mistral-code`).

Root cause: **(a)** — opencode's config only declares a hand-maintained
subset. It is **not** (b): the gateway's `/v1/models` is already complete
(modulo the one intentionally-hidden `"auto"` virtual id, which is a
separate, correct design choice, not part of this gap).

## 4. Fix

This is an **opencode-config-side fix**, not a Charon product change —
the gateway already does its job correctly.

Concrete fix: regenerate `provider.charon.models` in
`~/.config/opencode/opencode.json` from the gateway's own `/v1/models`
response, instead of hand-typing entries. Simplest form (per operator's
"lead with simplest tooling" preference): a small one-shot script/skill
that:

1. `GET http://10.0.1.60:8080/v1/models` with the gateway token,
2. builds `{id: {} for id in data}` (optionally keep the two custom
   `"name"` overrides already present for `deepseek-v4-pro` /
   `gpt-5.4-mini`),
3. adds back `"auto": {}` explicitly (since it won't come from
   `/v1/models`),
4. writes/merges that map into `provider.charon.models` in
   `opencode.json`.

Run it once now to unblock the operator, and re-run whenever the gateway's
model/pool set changes (new provider onboarded, models added/removed via
`/charon/models`). No opencode auto-discovery exists to make this
self-maintaining — a periodic re-sync (manual command, or a fleet-rig
hook) is required going forward. Do **not** try to "fix" this by changing
`proxy_server.py`'s `/v1/models` filtering — it is already correct and
already excludes only the one non-model virtual id.
