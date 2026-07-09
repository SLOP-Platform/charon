> ARCHIVED 2026-07-08 — superseded by POOLS-REDESIGN-ADR-v2.md (the manual free/cheap stack it planned was hand-deployed; the redesign supersedes the manual approach)

# Charon 4-LOM Gateway — Free/Cheap-Primary Insertion Plan

READ-ONLY investigation done 2026-07-03. Nothing on the host or in any repo was
modified. This is an apply-plan for the manager to execute.

Live container: `charon-gateway-1`, image `ghcr.io/slop-platform/charon:v0.3.1`,
`charon gateway --state-dir /data --host 0.0.0.0 --port 8080`, config volume
`charon_charon-config` → `/data`. Token = `CHARON_GATEWAY_TOKEN`
(in the container env; do NOT paste it into the plan/logs).

---

## 0. CRITICAL SCHEMA FINDING (read first — it changes how "primary" works)

The gateway config is THREE files in `/data`:

- `models.json` — registry: `"<alias>": {free, cost_rank, provider, upstream_model?}`
- `pools.json`  — `"<virtual-id>": ["<alias>", ...]` (50 pools)
- `providers.json` — per-provider overrides (base_url / key_env)

**The order you write in `pools.json` is NOT the effective priority.** At load
time (`gateway._build_routes_and_pools`) every pool is re-sorted:

```python
ordered = sorted(members, key=lambda m: (not free[m], cost_rank[m]))  # STABLE sort
```

i.e. **free-first, then cheapest-first; list order only breaks ties.**

Right now **every single model in the live registry has `free:false` and
`cost_rank:1000`** — they ALL tie, so the stable sort preserves the listed order.
That is the ONLY reason "list order == priority" appears true today (and why the
gpt-5.5 / gpt-5.4-pro "-or first" reorders currently hold — pure list order).

**Consequence for us:** to make a new provider a *primary* we must give its model
entry a rank that sorts ahead of `opencode-zen` (which is `free:false, rank:1000`).
Two honest ways:
- genuinely free (Groq/Cerebras/OpenRouter `:free`) → `free:true` (+ small
  `cost_rank` to order among the frees). Sorts above ALL current entries.
- cheap-paid (NeuralWatt, DeepSeek-direct, paid OpenRouter) → `free:false` +
  `cost_rank` between 1 and 999 → sorts above the rank-1000 zen tie-group but below
  the frees.

This is a pure AUGMENT: we never touch the metadata of the existing 200+ aliases,
so every existing fallback chain keeps its exact relative order (they all still tie
at rank 1000 and the stable sort preserves them). The new/promoted entries simply
float in above `opencode-zen`. **No `:free`/`-or`-first ordering is disturbed
because we are not editing those entries.**

---

## 1. Current structure summary

- **50 pools.** One catch-all `auto` (48 members) + 49 per-model pools.
- Per-model pools follow a suffix convention: bare alias = **opencode-zen**
  (primary today), `-go` = opencode-go, `-ng` = nanogpt, `-nw` = neuralwatt,
  `-ds` = deepseek-direct, `-or` = openrouter. Example:
  `deepseek-v4-pro = [deepseek-v4-pro(zen), -go, -ds, -ng, -or]`.
- **opencode-zen is primary in effectively every pool** (bare alias listed first),
  EXCEPT `gpt-5.5` and `gpt-5.4-pro` where `-or` (openrouter) is listed first, and
  `gpt-5.5-pro` (bare first). The `auto` pool's first member is `claude-fable-5`
  (opencode-zen).
- providers.json currently defines only: opencode-zen, openrouter, neuralwatt.
  (groq/nanogpt/deepseek/opencode-go resolve from built-in presets in
  `providers.py`; no override needed for groq.)
- secrets.json currently holds: OPENCODE_ZEN_KEY, OPENROUTER_API_KEY,
  NEURALWATT_API_KEY, DEEPSEEK_API_KEY, NANOGPT_API_KEY.
- **No `fallback.json`** (no global fallback appended today).

Pool taxonomy for tiering:
- **Highest-traffic / model-agnostic:** `auto` — the biggest cost lever; a client
  asking for `auto` wants "anything cheap that works", so cross-model free
  primaries are SAFE here.
- **Branded coding/agent pools (same-model promotion is safe):** `glm-5.2`,
  `glm-5.1`, `glm-5`, `kimi-k2.6`, `kimi-k2.5`, `deepseek-v4-pro`,
  `deepseek-v4-flash`, `qwen*` — these already carry the same model on a cheaper
  provider (NeuralWatt / DeepSeek-direct); we just promote that entry above zen.
- **Explicit free-tier pools:** `deepseek-v4-flash-free`, `mimo-v2.5-free`,
  `qwen3.6-plus-free`, `minimax-m3-free`, `nemotron-3-ultra-free`,
  `north-mini-code-free` — named "free" but every member is currently the PAID zen
  path. Prime targets for a genuine-free primary.
- **Branded premium pools (LEAVE — see Risks §7):** `claude-*`, `gpt-5*`,
  `gemini-*`, `grok-*`, `minimax-m2*` — substituting Groq-llama for a client that
  explicitly asked for Claude/GPT is a silent cross-model swap. Excluded from this
  conservative plan.

---

## 2. Proposed edits

### 2a. New `providers.json` addition (Cerebras — no preset exists)

Merge this one object into `/data/providers.json` (leave the 3 existing entries
untouched). Matches the neuralwatt/opencode-zen shape:

```json
"cerebras": {
  "key_env": "CEREBRAS_API_KEY",
  "base_url": "https://api.cerebras.ai/v1"
}
```
(`strip_v1` defaults true and is correct — the base ends in `/v1`. Groq needs NO
providers.json entry; its preset already carries base + GROQ_API_KEY.)

### 2b. New models.json entries (7 new aliases — no collision with existing ids)

```json
"groq-llama-3.3-70b":  {"free": true,  "cost_rank": 0,  "provider": "groq",      "upstream_model": "llama-3.3-70b-versatile"},
"groq-gpt-oss-120b":   {"free": true,  "cost_rank": 1,  "provider": "groq",      "upstream_model": "openai/gpt-oss-120b"},
"groq-llama-3.1-8b":   {"free": true,  "cost_rank": 2,  "provider": "groq",      "upstream_model": "llama-3.1-8b-instant"},
"nw-kimi-k2.7-code":   {"free": false, "cost_rank": 100,"provider": "neuralwatt", "upstream_model": "kimi-k2.7-code"},
"cerebras-gpt-oss-120b":{"free": true, "cost_rank": 10, "provider": "cerebras",  "upstream_model": "gpt-oss-120b"},
"cerebras-glm-4.7":    {"free": true,  "cost_rank": 11, "provider": "cerebras",  "upstream_model": "zai-glm-4.7"},
"cerebras-gemma-4-31b":{"free": true,  "cost_rank": 12, "provider": "cerebras",  "upstream_model": "gemma-4-31b"}
```

Rank ladder (lower = tried first): Groq-70B(0) → Groq-120B(1) → Groq-8B(2) →
Cerebras(10-12) → NeuralWatt-code(100) → DeepSeek-direct(200, see 2d) →
opencode-zen(1000). Cerebras is ranked BELOW Groq deliberately (its ~5 RPM makes it
a bad #1 for interactive traffic — see Risks §7).

### 2c. Promote existing same-model cheap providers (edit ONLY cost_rank)

Re-add these existing aliases with a lower `cost_rank` (nothing else changes — same
provider, same upstream_model). This lifts them above zen in their own pool only:

```json
"glm-5.2-nw":          {"free": false, "cost_rank": 100, "provider": "neuralwatt", "upstream_model": "glm-5.2"},
"kimi-k2.6-nw":        {"free": false, "cost_rank": 100, "provider": "neuralwatt", "upstream_model": "kimi-k2.6"},
"deepseek-v4-pro-ds":  {"free": false, "cost_rank": 200, "provider": "deepseek",   "upstream_model": "deepseek-v4-pro"},
"deepseek-v4-flash-ds":{"free": false, "cost_rank": 200, "provider": "deepseek",   "upstream_model": "deepseek-v4-flash"}
```

### 2d. Promote the genuine-free OpenRouter entry in the free pool (edit cost_rank+free)

`north-mini-code-free-or` is the real `:free` OpenRouter variant. Mark it free so it
becomes primary of `north-mini-code-free`:

```json
"north-mini-code-free-or": {"free": true, "cost_rank": 8, "provider": "openrouter", "upstream_model": "cohere/north-mini-code:free"}
```

### 2e. Pool membership changes (only pools that need a NEW member added)

Same-model promotions in 2c/2d need NO pool edit (the alias is already a member; the
new rank floats it up). Only two pools need a new member inserted:

**`auto`** — prepend the four agent/interactive free primaries (full new member
list; the trailing 48 are the existing members verbatim, order preserved):

```json
"auto": [
  "groq-llama-3.3-70b", "groq-gpt-oss-120b", "groq-llama-3.1-8b", "nw-kimi-k2.7-code",
  "claude-fable-5","claude-opus-4-8","claude-opus-4-7","claude-opus-4-6","claude-opus-4-5",
  "claude-opus-4-1","claude-sonnet-4-6","claude-sonnet-4-5","claude-sonnet-4","claude-haiku-4-5",
  "gemini-3.5-flash","gemini-3.1-pro","gemini-3-flash","gpt-5.5","gpt-5.5-pro","gpt-5.4",
  "gpt-5.4-pro","gpt-5.4-mini","gpt-5.4-nano","gpt-5.3-codex-spark","gpt-5.3-codex","gpt-5.2",
  "gpt-5.2-codex","gpt-5.1","gpt-5.1-codex-max","gpt-5.1-codex","gpt-5.1-codex-mini","gpt-5",
  "gpt-5-codex","gpt-5-nano","grok-build-0.1","deepseek-v4-pro","deepseek-v4-flash","glm-5.2",
  "glm-5.1","glm-5","minimax-m2.7","minimax-m2.5","kimi-k2.6","kimi-k2.5","qwen3.6-plus",
  "qwen3.5-plus","big-pickle","deepseek-v4-flash-free","mimo-v2.5-free","qwen3.6-plus-free",
  "minimax-m3-free","nemotron-3-ultra-free","north-mini-code-free"
]
```

Effective post-sort order of `auto`: **groq-llama-3.3-70b → groq-gpt-oss-120b →
groq-llama-3.1-8b → nw-kimi-k2.7-code → (all existing entries, unchanged order,
tail = opencode-zen family).**

**`deepseek-v4-flash-free`** — prepend a genuine free primary (this "free" pool is
currently 100% the paid zen path):

```json
"deepseek-v4-flash-free": ["groq-llama-3.1-8b","deepseek-v4-flash-free","deepseek-v4-flash-free-go","deepseek-v4-flash-free-ng","deepseek-v4-flash-free-or"]
```

### 2f. Per-pool BEFORE → AFTER (effective priority after the sort)

| Pool | BEFORE (effective #1 → …) | AFTER (effective #1 → …) |
|------|---------------------------|--------------------------|
| `auto` | claude-fable-5 (zen) → … | groq-70B → groq-120B → groq-8B → nw-kimi-code → claude-fable-5 (zen) → … |
| `glm-5.2` | glm-5.2 (zen) → -go → -ng → -nw → -or | **glm-5.2-nw (NeuralWatt, same model)** → glm-5.2 (zen) → -go → -ng → -or |
| `kimi-k2.6` | kimi-k2.6 (zen) → -go → -ng → -nw → -or | **kimi-k2.6-nw (NeuralWatt, same model)** → kimi-k2.6 (zen) → -go → -ng → -or |
| `deepseek-v4-pro` | deepseek-v4-pro (zen) → -go → -ds → -ng → -or | **deepseek-v4-pro-ds (DeepSeek direct)** → zen → -go → -ng → -or |
| `deepseek-v4-flash` | deepseek-v4-flash (zen) → -go → -ds → -ng → -or | **deepseek-v4-flash-ds (DeepSeek direct)** → zen → -go → -ng → -or |
| `deepseek-v4-flash-free` | deepseek-v4-flash-free (zen) → … | **groq-llama-3.1-8b (free)** → zen → -go → -ng → -or |
| `north-mini-code-free` | north-mini-code-free (zen) → -go → -ng → -or | **north-mini-code-free-or (OpenRouter :free)** → zen → -go → -ng |

In every case opencode-zen and the full existing chain remain BELOW the inserted
primary and keep their order.

**Deliberately NOT changed (conservative scope):** all `claude-*`, `gpt-5*`,
`gemini-*`, `grok-*`, `minimax-m2*` pools, and the `gpt-5.5`/`gpt-5.4-pro` `-or`-first
reorders (untouched → preserved). See Risks §7 for the aggressive-scope option.

---

## 3. secrets.json additions (values supplied at apply time)

- `GROQ_API_KEY`
- `CEREBRAS_API_KEY`

(NEURALWATT_API_KEY, DEEPSEEK_API_KEY, OPENROUTER_API_KEY already present — the
promotions in 2c/2d need no new secret.)

---

## 4. providers.json addition

Only the `cerebras` object from §2a. (groq uses its built-in preset.)

---

## 5. Apply mechanism — RECOMMENDED: setup API, hot-reload, NO restart

The container runs with `setup_dir=/data` (because it was started with
`--state-dir` and no `--config`), so the write+hot-reload setup API is LIVE. Each
successful POST calls `secrets.apply_to_env()` → `load_config(/data)` →
`server.apply_routes(...)`, i.e. it re-reads ALL config and swaps routes on the live
server with zero downtime and no dropped socket. Endpoints (all token-gated;
curl sends no Origin/Sec-Fetch-Site so the CSRF guard passes):

- `POST /charon/providers` — validates + LIVE-PROBES the key, stores it in the 0600
  secrets.json, writes the providers.json override, reloads. (Bad key → 400, nothing
  persisted.)
- `POST /charon/models` — upserts a models.json entry, reloads.
- `POST /charon/pools`  — replaces a pool's member list, reloads.

`curl` is present on the host and the gateway is published on `127.0.0.1:8080`, so
run curl over ssh from the host. Set `T` to the token first (read it from the
container, don't hardcode it in a shared file):

```bash
SSH='ssh -i ~/.ssh/4lom stack@10.0.1.60'
T=$($SSH 'docker exec charon-gateway-1 printenv CHARON_GATEWAY_TOKEN')
post(){ $SSH "curl -s -X POST 'http://127.0.0.1:8080/charon/$1?token=$T' -H 'Content-Type: application/json' -d '$2'"; echo; }
```

### Step 0 — BACK UP the live config first (data-loss guard)
```bash
$SSH 'docker exec charon-gateway-1 sh -c "cd /data && for f in models pools providers secrets; do cp -a \$f.json \$f.json.$(date +%s).bak; done && ls -la /data/*.bak"'
```

### Step 1 — providers + secrets (operator pastes real keys)
```bash
post providers '{"name":"groq","key":"<GROQ_API_KEY>"}'
post providers '{"name":"cerebras","base_url":"https://api.cerebras.ai/v1","key_env":"CEREBRAS_API_KEY","key":"<CEREBRAS_API_KEY>"}'
```
Expect `{"ok":true,...,"probe":{"valid":true,...}}`. A 400 means the key failed its
live probe — fix the key before continuing.

### Step 2 — new models (7) + promotions (5)
```bash
post models '{"id":"groq-llama-3.3-70b","provider":"groq","upstream_model":"llama-3.3-70b-versatile","free":true,"cost_rank":0}'
post models '{"id":"groq-gpt-oss-120b","provider":"groq","upstream_model":"openai/gpt-oss-120b","free":true,"cost_rank":1}'
post models '{"id":"groq-llama-3.1-8b","provider":"groq","upstream_model":"llama-3.1-8b-instant","free":true,"cost_rank":2}'
post models '{"id":"nw-kimi-k2.7-code","provider":"neuralwatt","upstream_model":"kimi-k2.7-code","free":false,"cost_rank":100}'
post models '{"id":"cerebras-gpt-oss-120b","provider":"cerebras","upstream_model":"gpt-oss-120b","free":true,"cost_rank":10}'
post models '{"id":"cerebras-glm-4.7","provider":"cerebras","upstream_model":"zai-glm-4.7","free":true,"cost_rank":11}'
post models '{"id":"cerebras-gemma-4-31b","provider":"cerebras","upstream_model":"gemma-4-31b","free":true,"cost_rank":12}'
# promotions (same provider/model, lower rank):
post models '{"id":"glm-5.2-nw","provider":"neuralwatt","upstream_model":"glm-5.2","free":false,"cost_rank":100}'
post models '{"id":"kimi-k2.6-nw","provider":"neuralwatt","upstream_model":"kimi-k2.6","free":false,"cost_rank":100}'
post models '{"id":"deepseek-v4-pro-ds","provider":"deepseek","upstream_model":"deepseek-v4-pro","free":false,"cost_rank":200}'
post models '{"id":"deepseek-v4-flash-ds","provider":"deepseek","upstream_model":"deepseek-v4-flash","free":false,"cost_rank":200}'
post models '{"id":"north-mini-code-free-or","provider":"openrouter","upstream_model":"cohere/north-mini-code:free","free":true,"cost_rank":8}'
```
NOTE: `/charon/models` preserves existing context_window/etc. metadata; it takes
provider/upstream_model/free/cost_rank from the payload, so re-supply them exactly
as above for the promotions.

### Step 3 — the two pools that gain a new member
```bash
post pools '{"id":"auto","members":["groq-llama-3.3-70b","groq-gpt-oss-120b","groq-llama-3.1-8b","nw-kimi-k2.7-code","claude-fable-5","claude-opus-4-8","claude-opus-4-7","claude-opus-4-6","claude-opus-4-5","claude-opus-4-1","claude-sonnet-4-6","claude-sonnet-4-5","claude-sonnet-4","claude-haiku-4-5","gemini-3.5-flash","gemini-3.1-pro","gemini-3-flash","gpt-5.5","gpt-5.5-pro","gpt-5.4","gpt-5.4-pro","gpt-5.4-mini","gpt-5.4-nano","gpt-5.3-codex-spark","gpt-5.3-codex","gpt-5.2","gpt-5.2-codex","gpt-5.1","gpt-5.1-codex-max","gpt-5.1-codex","gpt-5.1-codex-mini","gpt-5","gpt-5-codex","gpt-5-nano","grok-build-0.1","deepseek-v4-pro","deepseek-v4-flash","glm-5.2","glm-5.1","glm-5","minimax-m2.7","minimax-m2.5","kimi-k2.6","kimi-k2.5","qwen3.6-plus","qwen3.5-plus","big-pickle","deepseek-v4-flash-free","mimo-v2.5-free","qwen3.6-plus-free","minimax-m3-free","nemotron-3-ultra-free","north-mini-code-free"]}'
post pools '{"id":"deepseek-v4-flash-free","members":["groq-llama-3.1-8b","deepseek-v4-flash-free","deepseek-v4-flash-free-go","deepseek-v4-flash-free-ng","deepseek-v4-flash-free-or"]}'
```

### Fallback apply path (if the setup API is ever unavailable)
Edit the JSON in the volume directly, then reload by restart:
```bash
# ... write /data/{providers,models,pools}.json + secrets.json via docker exec ...
cd /home/stack/charon && docker compose restart gateway   # re-runs load_config from /data
```
Restart is ~2 s and is proven safe (config lives on the persistent `charon-config`
volume; the entrypoint re-applies secrets to env on start). Prefer the API path —
it validates keys and never drops the socket.

---

## 6. Verification (post-apply)

```bash
# a) health + model count grew by 7 (was N → N+7); pool count MUST still be 50
$SSH "curl -s 'http://127.0.0.1:8080/v1/models?token=$T'" | python3 -c 'import sys,json;print("served_models",len(json.load(sys.stdin)["data"]))'
$SSH 'docker exec charon-gateway-1 python3 -c "import json;print(\"pools\",len(json.load(open(\"/data/pools.json\"))))"'   # expect 50
# b) new primary sits at the top of auto (effective order):
$SSH 'docker exec charon-gateway-1 python3 -c "import json;from charon import gateway;c=gateway.load_config(state_dir=\"/data\");print([r.upstream_base for r in c.pools[\"auto\"][:3]])"'
# expect the groq base (https://api.groq.com/openai/v1) first
# c) live tool-calling completion routed through a new primary:
$SSH "curl -s -X POST 'http://127.0.0.1:8080/v1/chat/completions?token=$T' -H 'Content-Type: application/json' -d '{\"model\":\"auto\",\"messages\":[{\"role\":\"user\",\"content\":\"Call the add tool on 2 and 2.\"}],\"tools\":[{\"type\":\"function\",\"function\":{\"name\":\"add\",\"description\":\"add two ints\",\"parameters\":{\"type\":\"object\",\"properties\":{\"a\":{\"type\":\"integer\"},\"b\":{\"type\":\"integer\"}},\"required\":[\"a\",\"b\"]}}}],\"tool_choice\":\"auto\"}'"
# expect a 200 with a tool_calls[] entry; then confirm the hop hit Groq:
$SSH 'docker logs charon-gateway-1 --tail 30 2>&1 | grep -i "groq\|api.groq\|route" | tail'
```
If (c) shows a tool_calls response and the log shows the groq upstream, the free
primary is live and billing has shifted off opencode-zen for `auto`.

---

## 7. Risks / flags

1. **Cross-model substitution — the big one.** In `auto` and the `*-free` pools,
   a client that asked for "auto" now gets Groq-llama first instead of Claude/GPT.
   That is intended for a cost-relief catch-all, but any client PINNED to a branded
   id (`claude-opus-4-8`, `gpt-5.5`, …) is UNAFFECTED by this plan — those pools are
   left on their existing chains. To relieve branded-pinned traffic you must either
   (a) point those clients at `auto`, or (b) accept cross-model injection into the
   branded pools (aggressive scope — NOT in this plan; flag for a separate decision).
2. **Cerebras ~5 RPM.** Ranked below Groq on purpose; it is a bad interactive #1.
   Kept OUT of `auto`'s top and out of the branded interactive pools. Only wire it as
   a batch/large-context option (the cerebras-* models exist in the registry after
   §2b but are not yet placed as anyone's primary — add them to a dedicated batch
   pool if/when you create one).
3. **Groq free caps.** 70B ≈ 1000 RPD, 6k TPM; 8B ≈ 14.4k RPD. On 429/exhaustion
   the gateway fails over down the chain (→ gpt-oss-120B → 8B → zen), so a cap is a
   soft degrade, not an outage. Fine for a solo dev; watch TPM on long contexts.
4. **NeuralWatt cost unknown.** Promoted as `free:false, rank:100` (cheap-paid
   assumption). If it turns out metered near opencode-zen rates, the glm-5.2 / kimi
   / auto promotions save little — verify NeuralWatt pricing before trusting it as a
   primary. It still sits ABOVE zen so it can't be worse than status quo per-call
   unless NeuralWatt is pricier than zen for that model.
5. **Provider-probe gate.** `/charon/providers` refuses to persist a key that fails
   its live probe (returns 400). Good safety, but it means Step 1 must run with
   genuinely working keys or nothing downstream resolves.
6. **`upstream_model` ids are unverified against each vendor's live catalog.** The
   ids in §2b (e.g. `openai/gpt-oss-120b` on Groq, `zai-glm-4.7`/`gemma-4-31b` on
   Cerebras, `kimi-k2.7-code` on NeuralWatt) come from the task brief; if any is
   wrong the gateway will 404 that upstream and fail over (no hard break, but that
   candidate is dead weight). Confirm each id with a one-shot completion after apply.
7. **Excluded providers respected.** No Gemini / CommandCode / Synthetic.new entries
   are added or promoted anywhere in this plan; existing entries for them are left
   untouched.
8. **`models.json` / registry vs coordinator.** `src/charon/pools.py`
   (`PoolEntry`, agent-based) is the ACP COORDINATOR loader and is NOT what this
   gateway uses — the gateway uses `gateway.load_config` over
   models.json/pools.json/providers.json. Do not confuse the two schemas; all edits
   here are the gateway schema.
