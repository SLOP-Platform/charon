# Cline Pass → live Charon gateway wiring report

- **Date:** 2026-07-09
- **Host:** 4-lom (10.0.1.60), container `charon-gateway-1`, image `ghcr.io/slop-platform/charon:v0.3.6`
- **Method:** setup-API POST (hot-reload, NO container restart). Additive + reversible only.
- **Config dir:** `/data` (CHARON_HOME) inside the container.

---

## STEP 0 — Backups (done, before any change)

- **Off-host** (this workstation): `/home/stack/backups/charon-4lom-20260709T043528Z/`
  contains `providers.json pools.json models.json secrets.json fallback.json gateway.json quality.json spend.json`.
- **In-container** timestamped copies: `/data/{providers,pools,models,secrets,fallback}.json.clinewire-20260709T043528Z.bak`
- Secret values were **never printed**; secrets backed up as structure only.

### Rollback (exact)

Primary (API-driven, hot-reloads, no restart) — a ready script:

```
bash /home/stack/charon-private/fleet/scratch/cline-rollback.sh
```

It restores the 5 pools to their original members, removes the 5 `*-cline` models, and
removes the `cline-pass` provider. `CLINE_PASS_API_KEY` is left in the secret store.

Disk-level fallback (if the API is unavailable) — restore files, then any setup-API write hot-reloads:

```
ssh -i ~/.ssh/4lom stack@10.0.1.60 "docker exec charon-gateway-1 sh -c 'cd /data && for f in providers pools models fallback; do cp -p \$f.json.clinewire-20260709T043528Z.bak \$f.json; done'"
```

---

## STEP 1 — Key verification

- `CLINE_PASS_API_KEY` present in `/data/secrets.json` (**length 67**, value never read/printed).
- Direct probe to `https://api.cline.bot/api/v1/chat/completions` (bearer key, `cline-pass/deepseek-v4-flash`, tiny max_tokens), run **inside the container** so the key never left it:
  **HTTP 200**, valid usage returned. **Key is valid, endpoint live.**

## STEP 2 — Cline model IDs (from docs.cline.bot, confirmed 2026-07-09)

Cline uses `cline-pass/*` ids and has **no `/models` endpoint**. Full set (10):
`glm-5.2, kimi-k2.7-code, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash, mimo-v2.5, mimo-v2.5-pro, minimax-m3, qwen3.7-max, qwen3.7-plus`.

## STEP 3 — Provider added

```
provider "cline-pass": base_url=https://api.cline.bot/api/v1, key_env=CLINE_PASS_API_KEY, strip_v1=true
```
Added **without** a `key` in the payload (skips the setup-API validation probe, which
false-fails on Cline — see note below). The key is already in the store and was
independently verified in STEP 1.

## STEP 4 — Pools wired (cheap-first, cost_rank=1)

Each Cline model added as a new registry entry (`provider=cline-pass`, `free=false`,
`cost_rank=1`) and **prepended** to the matching pool. No existing member removed or
reordered. No genuinely-free members exist in these pools, so `cost_rank=1` sorts the
Cline leg **first**; the existing paid members remain as spill/backstop.

| Pool | Cline member (upstream_model) | cost_rank | BEFORE → AFTER (order) |
|---|---|---|---|
| `glm-5.2` | glm-5.2-cline (`cline-pass/glm-5.2`) | 1 | ng,nw,or,hf → **cline**,ng,nw,or,hf |
| `kimi-k2.6` | kimi-k2.6-cline (`cline-pass/kimi-k2.6`) | 1 | ng,nw,or,hf → **cline**,ng,nw,or,hf |
| `deepseek-v4-pro` | deepseek-v4-pro-cline (`cline-pass/deepseek-v4-pro`) | 1 | ng,ds,or → **cline**,ng,ds,or |
| `deepseek-v4-flash` | deepseek-v4-flash-cline (`cline-pass/deepseek-v4-flash`) | 1 | ds,ng,or,hf → **cline**,ds,ng,or,hf |
| `minimax-m3-free` | minimax-m3-cline (`cline-pass/minimax-m3`) | 1 | ng,or → **cline**,ng,or |

**5 pools wired.**

### Models NOT wired (no clean capability match — reported, not forced)

- **mimo-v2.5** — was wired, then **reverted**. Cline serves a date-suffixed variant
  `xiaomi/mimo-v2.5-20260422`; its final id segment (`mimo-v2.5-20260422`) ≠ the pool's
  `mimo-v2.5`, so Charon's downgrade detector flags every response as a silent downgrade
  (`X-Charon-Downgrade` set, quality-scored as failure). Left out to avoid polluting
  routing. `mimo-v2.5-free` pool restored to its original 3 members.
- **kimi-k2.7-code** — no `kimi-k2.7` pool exists (only k2.6/k2.5). Skipped.
- **mimo-v2.5-pro** — no matching pool. Skipped.
- **qwen3.7-max / qwen3.7-plus** — only `qwen3.6-plus` / `qwen3.5-plus` pools exist.
  Cline serves **3.7**, not 3.6 — a version substitution, not an exact match. Skipped
  (see manager note; operator may choose to accept 3.7→3.6 substitution).

## STEP 5 — Through-gateway verification (real `charon-proxy` UA)

**Streaming (the coding-agent path)** — all 5 served **HTTP 200 via the Cline leg**,
`X-Charon-Provider=cline-pass`, `failovers=0`, no downgrade:

| Pool | Result | served model |
|---|---|---|
| glm-5.2 | 200, cline-pass, 0 failovers | zai/glm-5.2 |
| kimi-k2.6 | 200, cline-pass, 0 failovers | moonshotai/kimi-k2.6 |
| deepseek-v4-pro | 200, cline-pass, 0 failovers | deepseek/deepseek-v4-pro |
| deepseek-v4-flash | 200, cline-pass, 0 failovers | deepseek/deepseek-v4-flash |
| minimax-m3-free | 200, cline-pass, 0 failovers | minimax/minimax-m3 |

Spill intact: every original member is still present after the Cline entry (see AFTER
column), so a Cline throttle/failure falls through to nanogpt/openrouter/etc. as before.

---

## ⚠ REQUIRES MANAGER ATTENTION — non-streaming response envelope

Cline's `/api/v1/chat/completions` is OpenAI-compatible **only when streaming**. For a
**non-streaming** request it returns a non-standard envelope:

```
{"data": { ...the real OpenAI object (choices, model, usage)... }, "success": true}
```

Charon relays the upstream body **verbatim** (`proxy_server.py` writes `body_bytes`
unchanged) and its usage/downgrade detector reads top-level `model` — which is absent
here, so the response is classified as a clean 200 and passed through as-is. Confirmed
live through the gateway: a non-stream call to `deepseek-v4-flash`/`glm-5.2` returns
top-level keys `['data','success']` with **no top-level `choices`** — i.e. a standard
OpenAI client doing a non-stream request against these 5 pools now gets a body it can't
parse. (Control: `gpt-5.4` via nanogpt returns the correct top-level shape.)

- **Streaming works perfectly** (dominant coding-agent path). Non-streaming is the only
  broken mode, and only for the 5 Cline-wired pools when the Cline leg serves.
- **Options for the operator/manager:**
  1. Accept it if all real clients stream (coding agents do).
  2. Add a small provider-scoped response-unwrap shim in the proxy for `cline-pass`
     (unwrap `{"data":…}` → top-level) — a **product code change**, out of scope for
     this live-ops wiring; recommend a ticket.
  3. Roll back (script above) if any non-streaming client depends on these pools.

Secondary note: the setup-API key-validation probe (`config.validate_provider_key`)
false-fails on Cline (no `/models` endpoint; `model:"."` probe likely 4xx). Harmless
here (provider added without a key since the key was pre-stored + directly verified),
but worth a product fix if Cline is ever re-added via the web UI with a key.

---

## Frontier-tier CANDIDATES (same config pass, per manager add-on)

Added as *available* pool members for operator testing — **not** displacing or reordering
anything, and **not** designated a workhorse/default. Neutral `cost_rank=1000`.

| Model | Status | Through-gateway result (real UA, streaming, tiny max_tokens) |
|---|---|---|
| `gemini-3.1-pro` | already live (pre-existing pool `gemini-3.1-pro` = [ng, or]) — **no change** | **HTTP 200** via nanogpt, 0 failovers, served `google/gemini-3.1-pro-preview` |
| `grok-4.3` | **ADDED** config-only: new pool `grok-4.3` = [`grok-4.3-ng` (nanogpt→`x-ai/grok-4.3`), `grok-4.3-or` (openrouter→`x-ai/grok-4.3`)] | **HTTP 200** via nanogpt (openrouter = backstop), 0 failovers, served `x-ai/grok-4.3` |

Keys for both providers were already present (no signup). Rollback for grok-4.3 is folded
into `cline-rollback.sh` (removes the pool + 2 models); gemini-3.1-pro is left untouched
since it pre-existed.

## Summary

- Key valid: **YES** (HTTP 200 direct, len 67).
- Provider added: **YES** (`cline-pass`).
- Pools wired: **5** (glm-5.2, kimi-k2.6, deepseek-v4-pro, deepseek-v4-flash, minimax-m3-free).
- Through-gateway 200 via Cline leg: **YES** for all 5 (streaming), 0 failovers, spill intact.
- Not matched: mimo-v2.5 (date-suffixed downgrade flag; reverted), kimi-k2.7-code,
  mimo-v2.5-pro, qwen3.7-max/plus (no exact-version pool).
- Backup: `/home/stack/backups/charon-4lom-20260709T043528Z/` + in-container
  `*.clinewire-20260709T043528Z.bak`. Rollback: `cline-rollback.sh`.
- **Frontier candidates:** `gemini-3.1-pro` confirmed live (200, nanogpt); `grok-4.3`
  added config-only and confirmed 200 (nanogpt, openrouter backstop). Both are candidates
  only — not defaulted/reordered.
- **Manager attention:** non-streaming requests to the 5 Cline pools return Cline's
  `{"data",...}` envelope (breaks OpenAI clients); streaming is clean. Decide accept /
  add unwrap shim / roll back.
