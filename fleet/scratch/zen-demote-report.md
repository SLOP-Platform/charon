# opencode-zen demotion — LIVE 4-LOM report

Date: 2026-07-07
Red: `opencode-zen-pool-primary`
Refs: fleet/scratch/reds-triage.md §4, fleet/POOLS-EDIT-PLAN.md §5

## Scope

Demote opencode-zen (provider `opencode-zen`) AND its coding-focused
"-go" sibling (provider `opencode-go`, confirmed to share the SAME
`OPENCODE_ZEN_KEY`/balance per `src/charon/providers.py` — this is the
"zen-go variant" the task referenced) from FIRST/primary to LAST in every
pool where either sat first. opencode-zen/opencode-go was **kept present**
everywhere (never removed) per the operator's instruction to preserve it
as a fallback for a possible future top-up. `auto` was already fixed in
an earlier session and was explicitly left untouched.

## 1. Backup

```
/
  models.json     26540 bytes, valid JSON
  pools.json       5911 bytes, valid JSON
  providers.json    375 bytes, valid JSON
  secrets.json      710 bytes, valid JSON
```
Pulled live via `docker exec charon-gateway-1 cat /data/<f>.json` over
`ssh -i ~/.ssh/4lom stack@10.0.1.60`, before any writes. All 4 files
verified non-empty and `json.load`-parseable before proceeding.

## 2. Enumeration

Computed the gateway's **effective compiled order** (not raw list order)
via `charon.gateway.load_config(state_dir="/data")` inside the container
— this matches the real free-first/cost_rank stable-sort the gateway
applies at request time, so the enumeration reflects what actually serves
traffic, not just the JSON's on-disk order.

- 50 pools total.
- 46 pools had `opencode-zen` (or `opencode-go`) as the effective FIRST
  member. This matches the ~46-pool figure from the 07-04 handoff exactly.
- 4 pools were already NOT zen-first and were left untouched: `auto`
  (fixed previously — groq first), `deepseek-v4-pro` (nanogpt first),
  `gpt-5.4-pro` (openrouter first), `gpt-5.5` (nanogpt first). Verified
  byte-identical before/after.
- Every one of the 46 pools' raw `pools.json` member list also had zen
  literally first (confirmed) AND every member of each pool ties on
  `(free, cost_rank)` in `models.json` (confirmed) — so list order fully
  determines effective priority in these pools, meaning a pure member-list
  reorder (no `cost_rank`/`free` edits) is sufficient and correct.
- All 46 pools carry BOTH the bare zen alias (position 0) and its `-go`
  sibling (position 1, provider `opencode-go`) except the 6 `*-free`
  pools, which carry only the bare zen alias (their `-go` id is a dangling
  reference already pruned from `models.json` by the prior dead-free-go
  cleanup — inert, left as-is, out of this task's scope).

## 3. Demotion mechanism

Used `POST /charon/pools {"id": <vid>, "members": [...]}` (fully replaces
a pool's member list, hot-reloads via `apply_to_env → load_config →
apply_routes`, no restart) — the documented, cleanest path from
POOLS-EDIT-PLAN.md §5. No remove-then-re-add needed; a direct reorder call
covers it.

Algorithm per pool: `new_members = [non-zen members, in original order] +
[zen-family members (bare + -go), in original relative order]`. This
moves all zen/zen-go members to the end as a block while leaving every
other member's relative order untouched — zen/opencode-go is demoted, not
removed, and reappears at the tail of the chain.

Applied via a small script
(`/home/stack/zen_demote_apply/apply_zen_demote.py` on the 4-LOM host)
issuing one POST per pool with the live `CHARON_GATEWAY_TOKEN` read from
the running container. **All 46 POSTs returned `HTTP 200 {"ok": true}`.**
Zero failures — nothing to roll back.

## 4. Per-pool before -> after (effective member order)

| Pool | Before (member order) | After (member order) | No-op (all-zen)? |
|---|---|---|---|
| big-pickle | big-pickle -> big-pickle-go | big-pickle -> big-pickle-go | YES |
| claude-fable-5 | claude-fable-5 -> claude-fable-5-go -> claude-fable-5-ng -> claude-fable-5-or | claude-fable-5-ng -> claude-fable-5-or -> claude-fable-5 -> claude-fable-5-go |  |
| claude-haiku-4-5 | claude-haiku-4-5 -> claude-haiku-4-5-go -> claude-haiku-4-5-ng -> claude-haiku-4-5-or | claude-haiku-4-5-ng -> claude-haiku-4-5-or -> claude-haiku-4-5 -> claude-haiku-4-5-go |  |
| claude-opus-4-1 | claude-opus-4-1 -> claude-opus-4-1-go -> claude-opus-4-1-ng -> claude-opus-4-1-or | claude-opus-4-1-ng -> claude-opus-4-1-or -> claude-opus-4-1 -> claude-opus-4-1-go |  |
| claude-opus-4-5 | claude-opus-4-5 -> claude-opus-4-5-go -> claude-opus-4-5-ng -> claude-opus-4-5-or | claude-opus-4-5-ng -> claude-opus-4-5-or -> claude-opus-4-5 -> claude-opus-4-5-go |  |
| claude-opus-4-6 | claude-opus-4-6 -> claude-opus-4-6-go -> claude-opus-4-6-ng -> claude-opus-4-6-or | claude-opus-4-6-ng -> claude-opus-4-6-or -> claude-opus-4-6 -> claude-opus-4-6-go |  |
| claude-opus-4-7 | claude-opus-4-7 -> claude-opus-4-7-go -> claude-opus-4-7-ng -> claude-opus-4-7-or | claude-opus-4-7-ng -> claude-opus-4-7-or -> claude-opus-4-7 -> claude-opus-4-7-go |  |
| claude-opus-4-8 | claude-opus-4-8 -> claude-opus-4-8-go -> claude-opus-4-8-ng -> claude-opus-4-8-or | claude-opus-4-8-ng -> claude-opus-4-8-or -> claude-opus-4-8 -> claude-opus-4-8-go |  |
| claude-sonnet-4 | claude-sonnet-4 -> claude-sonnet-4-go -> claude-sonnet-4-ng -> claude-sonnet-4-or | claude-sonnet-4-ng -> claude-sonnet-4-or -> claude-sonnet-4 -> claude-sonnet-4-go |  |
| claude-sonnet-4-5 | claude-sonnet-4-5 -> claude-sonnet-4-5-go -> claude-sonnet-4-5-ng -> claude-sonnet-4-5-or | claude-sonnet-4-5-ng -> claude-sonnet-4-5-or -> claude-sonnet-4-5 -> claude-sonnet-4-5-go |  |
| claude-sonnet-4-6 | claude-sonnet-4-6 -> claude-sonnet-4-6-go -> claude-sonnet-4-6-ng -> claude-sonnet-4-6-or | claude-sonnet-4-6-ng -> claude-sonnet-4-6-or -> claude-sonnet-4-6 -> claude-sonnet-4-6-go |  |
| deepseek-v4-flash | deepseek-v4-flash -> deepseek-v4-flash-go -> deepseek-v4-flash-ds -> deepseek-v4-flash-ng -> deepseek-v4-flash-or | deepseek-v4-flash-ds -> deepseek-v4-flash-ng -> deepseek-v4-flash-or -> deepseek-v4-flash -> deepseek-v4-flash-go |  |
| deepseek-v4-flash-free | deepseek-v4-flash-free -> deepseek-v4-flash-free-go -> deepseek-v4-flash-free-ng -> deepseek-v4-flash-free-or | deepseek-v4-flash-free-go -> deepseek-v4-flash-free-ng -> deepseek-v4-flash-free-or -> deepseek-v4-flash-free |  |
| gemini-3-flash | gemini-3-flash -> gemini-3-flash-go -> gemini-3-flash-ng -> gemini-3-flash-or | gemini-3-flash-ng -> gemini-3-flash-or -> gemini-3-flash -> gemini-3-flash-go |  |
| gemini-3.1-pro | gemini-3.1-pro -> gemini-3.1-pro-go -> gemini-3.1-pro-ng -> gemini-3.1-pro-or | gemini-3.1-pro-ng -> gemini-3.1-pro-or -> gemini-3.1-pro -> gemini-3.1-pro-go |  |
| gemini-3.5-flash | gemini-3.5-flash -> gemini-3.5-flash-go -> gemini-3.5-flash-ng -> gemini-3.5-flash-or | gemini-3.5-flash-ng -> gemini-3.5-flash-or -> gemini-3.5-flash -> gemini-3.5-flash-go |  |
| glm-5 | glm-5 -> glm-5-go -> glm-5-ng -> glm-5-or | glm-5-ng -> glm-5-or -> glm-5 -> glm-5-go |  |
| glm-5.1 | glm-5.1 -> glm-5.1-go -> glm-5.1-ng -> glm-5.1-or | glm-5.1-ng -> glm-5.1-or -> glm-5.1 -> glm-5.1-go |  |
| glm-5.2 | glm-5.2 -> glm-5.2-go -> glm-5.2-ng -> glm-5.2-nw -> glm-5.2-or | glm-5.2-ng -> glm-5.2-nw -> glm-5.2-or -> glm-5.2 -> glm-5.2-go |  |
| gpt-5 | gpt-5 -> gpt-5-go -> gpt-5-ng -> gpt-5-or | gpt-5-ng -> gpt-5-or -> gpt-5 -> gpt-5-go |  |
| gpt-5-codex | gpt-5-codex -> gpt-5-codex-go -> gpt-5-codex-ng -> gpt-5-codex-or | gpt-5-codex-ng -> gpt-5-codex-or -> gpt-5-codex -> gpt-5-codex-go |  |
| gpt-5-nano | gpt-5-nano -> gpt-5-nano-go -> gpt-5-nano-ng -> gpt-5-nano-or | gpt-5-nano-ng -> gpt-5-nano-or -> gpt-5-nano -> gpt-5-nano-go |  |
| gpt-5.1 | gpt-5.1 -> gpt-5.1-go -> gpt-5.1-ng -> gpt-5.1-or | gpt-5.1-ng -> gpt-5.1-or -> gpt-5.1 -> gpt-5.1-go |  |
| gpt-5.1-codex | gpt-5.1-codex -> gpt-5.1-codex-go -> gpt-5.1-codex-ng -> gpt-5.1-codex-or | gpt-5.1-codex-ng -> gpt-5.1-codex-or -> gpt-5.1-codex -> gpt-5.1-codex-go |  |
| gpt-5.1-codex-max | gpt-5.1-codex-max -> gpt-5.1-codex-max-go -> gpt-5.1-codex-max-ng -> gpt-5.1-codex-max-or | gpt-5.1-codex-max-ng -> gpt-5.1-codex-max-or -> gpt-5.1-codex-max -> gpt-5.1-codex-max-go |  |
| gpt-5.1-codex-mini | gpt-5.1-codex-mini -> gpt-5.1-codex-mini-go -> gpt-5.1-codex-mini-ng -> gpt-5.1-codex-mini-or | gpt-5.1-codex-mini-ng -> gpt-5.1-codex-mini-or -> gpt-5.1-codex-mini -> gpt-5.1-codex-mini-go |  |
| gpt-5.2 | gpt-5.2 -> gpt-5.2-go -> gpt-5.2-ng -> gpt-5.2-or | gpt-5.2-ng -> gpt-5.2-or -> gpt-5.2 -> gpt-5.2-go |  |
| gpt-5.2-codex | gpt-5.2-codex -> gpt-5.2-codex-go -> gpt-5.2-codex-ng -> gpt-5.2-codex-or | gpt-5.2-codex-ng -> gpt-5.2-codex-or -> gpt-5.2-codex -> gpt-5.2-codex-go |  |
| gpt-5.3-codex | gpt-5.3-codex -> gpt-5.3-codex-go -> gpt-5.3-codex-ng -> gpt-5.3-codex-or | gpt-5.3-codex-ng -> gpt-5.3-codex-or -> gpt-5.3-codex -> gpt-5.3-codex-go |  |
| gpt-5.3-codex-spark | gpt-5.3-codex-spark -> gpt-5.3-codex-spark-go | gpt-5.3-codex-spark -> gpt-5.3-codex-spark-go | YES |
| gpt-5.4 | gpt-5.4 -> gpt-5.4-go -> gpt-5.4-ng -> gpt-5.4-or | gpt-5.4-ng -> gpt-5.4-or -> gpt-5.4 -> gpt-5.4-go |  |
| gpt-5.4-mini | gpt-5.4-mini -> gpt-5.4-mini-go -> gpt-5.4-mini-ng -> gpt-5.4-mini-or | gpt-5.4-mini-ng -> gpt-5.4-mini-or -> gpt-5.4-mini -> gpt-5.4-mini-go |  |
| gpt-5.4-nano | gpt-5.4-nano -> gpt-5.4-nano-go -> gpt-5.4-nano-ng -> gpt-5.4-nano-or | gpt-5.4-nano-ng -> gpt-5.4-nano-or -> gpt-5.4-nano -> gpt-5.4-nano-go |  |
| gpt-5.5-pro | gpt-5.5-pro -> gpt-5.5-pro-go -> gpt-5.5-pro-or | gpt-5.5-pro-or -> gpt-5.5-pro -> gpt-5.5-pro-go |  |
| grok-build-0.1 | grok-build-0.1 -> grok-build-0.1-go -> grok-build-0.1-ng -> grok-build-0.1-or | grok-build-0.1-ng -> grok-build-0.1-or -> grok-build-0.1 -> grok-build-0.1-go |  |
| kimi-k2.5 | kimi-k2.5 -> kimi-k2.5-go -> kimi-k2.5-ng -> kimi-k2.5-or | kimi-k2.5-ng -> kimi-k2.5-or -> kimi-k2.5 -> kimi-k2.5-go |  |
| kimi-k2.6 | kimi-k2.6 -> kimi-k2.6-go -> kimi-k2.6-ng -> kimi-k2.6-nw -> kimi-k2.6-or | kimi-k2.6-ng -> kimi-k2.6-nw -> kimi-k2.6-or -> kimi-k2.6 -> kimi-k2.6-go |  |
| mimo-v2.5-free | mimo-v2.5-free -> mimo-v2.5-free-go -> mimo-v2.5-free-ng -> mimo-v2.5-free-or | mimo-v2.5-free-go -> mimo-v2.5-free-ng -> mimo-v2.5-free-or -> mimo-v2.5-free |  |
| minimax-m2.5 | minimax-m2.5 -> minimax-m2.5-go -> minimax-m2.5-ng -> minimax-m2.5-or | minimax-m2.5-ng -> minimax-m2.5-or -> minimax-m2.5 -> minimax-m2.5-go |  |
| minimax-m2.7 | minimax-m2.7 -> minimax-m2.7-go -> minimax-m2.7-ng -> minimax-m2.7-or | minimax-m2.7-ng -> minimax-m2.7-or -> minimax-m2.7 -> minimax-m2.7-go |  |
| minimax-m3-free | minimax-m3-free -> minimax-m3-free-ng -> minimax-m3-free-or | minimax-m3-free-ng -> minimax-m3-free-or -> minimax-m3-free |  |
| nemotron-3-ultra-free | nemotron-3-ultra-free -> nemotron-3-ultra-free-go -> nemotron-3-ultra-free-ng -> nemotron-3-ultra-free-or | nemotron-3-ultra-free-go -> nemotron-3-ultra-free-ng -> nemotron-3-ultra-free-or -> nemotron-3-ultra-free |  |
| north-mini-code-free | north-mini-code-free -> north-mini-code-free-go -> north-mini-code-free-ng -> north-mini-code-free-or | north-mini-code-free-go -> north-mini-code-free-ng -> north-mini-code-free-or -> north-mini-code-free |  |
| qwen3.5-plus | qwen3.5-plus -> qwen3.5-plus-go -> qwen3.5-plus-ng -> qwen3.5-plus-or | qwen3.5-plus-ng -> qwen3.5-plus-or -> qwen3.5-plus -> qwen3.5-plus-go |  |
| qwen3.6-plus | qwen3.6-plus -> qwen3.6-plus-go -> qwen3.6-plus-ng -> qwen3.6-plus-or | qwen3.6-plus-ng -> qwen3.6-plus-or -> qwen3.6-plus -> qwen3.6-plus-go |  |
| qwen3.6-plus-free | qwen3.6-plus-free -> qwen3.6-plus-free-go -> qwen3.6-plus-free-ng -> qwen3.6-plus-free-or | qwen3.6-plus-free-go -> qwen3.6-plus-free-ng -> qwen3.6-plus-free-or -> qwen3.6-plus-free |  |

Two pools (`big-pickle`, `gpt-5.3-codex-spark`) are **no-ops**: both of
their members are entirely zen-family (bare + `-go`, no third-party
provider exists for that model in the registry), so there is nothing to
promote ahead of zen — the POST succeeded but produced an identical list.
Flagging this rather than silently treating it as done: these two pools
still serve from opencode-zen first because **no alternative provider is
registered for them**. Not a bug in this task; a pre-existing registry gap
worth a follow-up ticket if the operator wants an alternative sourced for
`big-pickle` / `gpt-5.3-codex-spark`.

## 5. Verification

- Pool count after: **50** (unchanged).
- Member SET per pool: **0 pools changed** (pure reorder, nothing
  added/dropped) — diffed full `pools.json` before vs. after.
- `auto`, `deepseek-v4-pro`, `gpt-5.4-pro`, `gpt-5.5`: confirmed
  byte-identical before/after (untouched, as intended).
- Recompiled effective order (`gateway.load_config`) after apply: **44 of
  46** pools now have opencode-zen/opencode-go strictly after every
  non-zen member. The remaining 2 (`big-pickle`,
  `gpt-5.3-codex-spark`) are the all-zen no-ops above — zen is still
  "first" only because it's the *only* member type present, not because
  demotion failed.

## 6. Health probes (live chat completions)

3 pools probed post-apply, each `{"model": "<id>", "messages":[...]}`
against `POST /v1/chat/completions`:

| Pool | HTTP | Served by | Notes |
|---|---|---|---|
| `claude-sonnet-4-6` | 200 | OpenRouter (Anthropic passthrough) | response content `"pong"`, OpenRouter-shaped body (`cost_details`, `is_byok`) |
| `gpt-5.4` | 200 | OpenRouter (OpenAI passthrough) | response content `"pong"`, OpenRouter-shaped body |
| `kimi-k2.6` | 200 | NanoGPT | NanoGPT-shaped body (`energy`/`carbon_g_co2eq`/`allowance_remaining_usd`) |

All 3 returned 200 with no visible extra latency and were served by a
non-zen provider — opencode-zen was not hit on any of the 3 probes.
(NanoGPT is compiled first in these 3 chains; the Claude/GPT probes
apparently fell through nanogpt to openrouter — pre-existing failover
behavior unrelated to this task, not investigated further since zen was
never reached either way.)

## 7. Mirror regen

Ran `~/.config/opencode/regen-charon-models.sh` locally (reads
`GET /v1/models` from the gateway, not run on the 4-LOM box itself):

```
backed up -> /home/stack/.config/opencode/opencode.json.bak-20260707-160412
curated: 30 ids, full: 201 ids
OK: /home/stack/.config/opencode/opencode.json is valid JSON
```

Container was **not** restarted; no volumes touched beyond the setup-API
writes.

## Summary

- **46 pools demoted** (opencode-zen + opencode-go moved to the end of
  their member list, kept present).
- **2 pools no-op** (`big-pickle`, `gpt-5.3-codex-spark`) — no non-zen
  alternative exists for those models today; flagged, not silently
  dropped.
- **4 pools correctly left untouched** (`auto` + 3 already non-zen-first).
- 0 failures, 0 rollbacks needed, 50/50 pools intact, no member dropped
  anywhere, 3/3 health probes green and non-zen-served, mirror refreshed.
