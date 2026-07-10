# opencode-zen family — full removal from live pools — 4-LOM

Date: 2026-07-07
Supersedes: `fleet/scratch/zen-demote-report.md` (the earlier last-resort demote)
Refs: `fleet/POOLS-EDIT-PLAN.md` §5, `fleet/scratch/dead-free-go-prune-report.md`
Container: `charon-gateway-1` (`ghcr.io/slop-platform/charon:v0.3.6`), healthy throughout,
**never restarted**.

## Scope

Account `OPENCODE_ZEN_KEY` (shared by provider `opencode-zen` and its coding-focused
sibling `opencode-go`) is depleted and will not be refilled. Task: remove the
zen-family **entirely** from every pool that has a working non-zen alternative,
skip the (max 2) pools that are zen-only rather than create a broken/empty pool.

## 1. Backup

Off-host copy at `/home/stack/backups/charon-4lom-zen-remove-1783474553/`:
`models.json` (26540 bytes), `pools.json` (5911 bytes), `providers.json` (375
bytes). All verified non-empty and `json.load`-parseable before any writes.
In-container `.bak` copies also left in `/data/*.json.1783474553.bak`
(`secrets.json` included there, not pulled off-host).

## 2. Enumeration (live, not the stale demote report)

Enumerated via the live `/data/models.json` + `/data/pools.json` inside the
running container (`docker exec charon-gateway-1 ...`), not the demote
report's numbers — re-verified fresh per instruction.

- zen-family model ids in `models.json`: **92** (46 bare `opencode-zen` +
  46 `-go` `opencode-go`). Note: `models.json` had shrunk 206→201 since the
  demote report due to an unrelated prior prune of 5 dead `*-free-go`
  dangling ids — irrelevant to this task, just explains the count delta.
- **50 pools total.**
- **47 pools** contained ≥1 zen-family member AND ≥1 non-zen sibling →
  edited (zen-family stripped, non-zen members kept in original order).
- **2 pools** are zen-family-only → **skipped, left untouched**:
  `big-pickle` (`['big-pickle', 'big-pickle-go']`), `gpt-5.3-codex-spark`
  (`['gpt-5.3-codex-spark', 'gpt-5.3-codex-spark-go']`). No non-zen
  provider is registered for either model today.
- **1 pool** (`auto`) had no zen-family member at all (fixed in an earlier
  session) — untouched, consistent with the demote report.
- 47 + 2 + 1 = 50, matches total.

## 3. Apply mechanism

Reused the setup-API pattern from `POOLS-EDIT-PLAN.md` §5 / the demote
report: `POST /charon/pools {"id": <pool>, "members": [...]}`, which fully
replaces a pool's member list and hot-reloads (`apply_to_env → load_config →
apply_routes`), no restart. Unlike the demote (reorder-to-last), this call
**omits** the zen-family ids from `members` entirely — full removal, not
reorder. Ran via a script on the 4-LOM host itself
(`/tmp/apply_zen_remove.py`) issuing one POST per edited pool with the live
`CHARON_GATEWAY_TOKEN` read from the running container.

Model definitions in `models.json` were **not** touched/removed (unlike the
dead-`-free-go` prune) — the 2 skip-list pools still reference them, so a
global `/charon/remove {kind:model}` would have emptied those pools. Only
pool membership was edited.

**All 47 POSTs returned `HTTP 200 {"ok": true}`.** (A bug in this session's
own verification script — a space-stripped string match — falsely flagged
all 47 as failures on first pass; re-verified directly against live state,
see §4, confirming the API calls actually succeeded and no retry was
needed.)

## 4. Per-pool before → after (member list)

47 pools edited — zen-family (bare + `-go`) removed, non-zen members kept
in original relative order:

| Pool | Removed | Members after |
|---|---|---|
| claude-fable-5 | claude-fable-5, claude-fable-5-go | claude-fable-5-ng, claude-fable-5-or |
| claude-haiku-4-5 | claude-haiku-4-5, claude-haiku-4-5-go | claude-haiku-4-5-ng, claude-haiku-4-5-or |
| claude-opus-4-1 | claude-opus-4-1, claude-opus-4-1-go | claude-opus-4-1-ng, claude-opus-4-1-or |
| claude-opus-4-5 | claude-opus-4-5, claude-opus-4-5-go | claude-opus-4-5-ng, claude-opus-4-5-or |
| claude-opus-4-6 | claude-opus-4-6, claude-opus-4-6-go | claude-opus-4-6-ng, claude-opus-4-6-or |
| claude-opus-4-7 | claude-opus-4-7, claude-opus-4-7-go | claude-opus-4-7-ng, claude-opus-4-7-or |
| claude-opus-4-8 | claude-opus-4-8, claude-opus-4-8-go | claude-opus-4-8-ng, claude-opus-4-8-or |
| claude-sonnet-4 | claude-sonnet-4, claude-sonnet-4-go | claude-sonnet-4-ng, claude-sonnet-4-or |
| claude-sonnet-4-5 | claude-sonnet-4-5, claude-sonnet-4-5-go | claude-sonnet-4-5-ng, claude-sonnet-4-5-or |
| claude-sonnet-4-6 | claude-sonnet-4-6, claude-sonnet-4-6-go | claude-sonnet-4-6-ng, claude-sonnet-4-6-or |
| deepseek-v4-flash | deepseek-v4-flash, deepseek-v4-flash-go | deepseek-v4-flash-ds, deepseek-v4-flash-ng, deepseek-v4-flash-or |
| deepseek-v4-flash-free | deepseek-v4-flash-free | deepseek-v4-flash-free-go\*, deepseek-v4-flash-free-ng, deepseek-v4-flash-free-or |
| deepseek-v4-pro | deepseek-v4-pro-go, deepseek-v4-pro | deepseek-v4-pro-ng, deepseek-v4-pro-ds, deepseek-v4-pro-or |
| gemini-3-flash | gemini-3-flash, gemini-3-flash-go | gemini-3-flash-ng, gemini-3-flash-or |
| gemini-3.1-pro | gemini-3.1-pro, gemini-3.1-pro-go | gemini-3.1-pro-ng, gemini-3.1-pro-or |
| gemini-3.5-flash | gemini-3.5-flash, gemini-3.5-flash-go | gemini-3.5-flash-ng, gemini-3.5-flash-or |
| glm-5 | glm-5, glm-5-go | glm-5-ng, glm-5-or |
| glm-5.1 | glm-5.1, glm-5.1-go | glm-5.1-ng, glm-5.1-or |
| glm-5.2 | glm-5.2, glm-5.2-go | glm-5.2-ng, glm-5.2-nw, glm-5.2-or |
| gpt-5 | gpt-5, gpt-5-go | gpt-5-ng, gpt-5-or |
| gpt-5-codex | gpt-5-codex, gpt-5-codex-go | gpt-5-codex-ng, gpt-5-codex-or |
| gpt-5-nano | gpt-5-nano, gpt-5-nano-go | gpt-5-nano-ng, gpt-5-nano-or |
| gpt-5.1 | gpt-5.1, gpt-5.1-go | gpt-5.1-ng, gpt-5.1-or |
| gpt-5.1-codex | gpt-5.1-codex, gpt-5.1-codex-go | gpt-5.1-codex-ng, gpt-5.1-codex-or |
| gpt-5.1-codex-max | gpt-5.1-codex-max, gpt-5.1-codex-max-go | gpt-5.1-codex-max-ng, gpt-5.1-codex-max-or |
| gpt-5.1-codex-mini | gpt-5.1-codex-mini, gpt-5.1-codex-mini-go | gpt-5.1-codex-mini-ng, gpt-5.1-codex-mini-or |
| gpt-5.2 | gpt-5.2, gpt-5.2-go | gpt-5.2-ng, gpt-5.2-or |
| gpt-5.2-codex | gpt-5.2-codex, gpt-5.2-codex-go | gpt-5.2-codex-ng, gpt-5.2-codex-or |
| gpt-5.3-codex | gpt-5.3-codex, gpt-5.3-codex-go | gpt-5.3-codex-ng, gpt-5.3-codex-or |
| gpt-5.4 | gpt-5.4, gpt-5.4-go | gpt-5.4-ng, gpt-5.4-or |
| gpt-5.4-mini | gpt-5.4-mini, gpt-5.4-mini-go | gpt-5.4-mini-ng, gpt-5.4-mini-or |
| gpt-5.4-nano | gpt-5.4-nano, gpt-5.4-nano-go | gpt-5.4-nano-ng, gpt-5.4-nano-or |
| gpt-5.4-pro | gpt-5.4-pro, gpt-5.4-pro-go | gpt-5.4-pro-or |
| gpt-5.5 | gpt-5.5, gpt-5.5-go | gpt-5.5-ng, gpt-5.5-or |
| gpt-5.5-pro | gpt-5.5-pro, gpt-5.5-pro-go | gpt-5.5-pro-or |
| grok-build-0.1 | grok-build-0.1, grok-build-0.1-go | grok-build-0.1-ng, grok-build-0.1-or |
| kimi-k2.5 | kimi-k2.5, kimi-k2.5-go | kimi-k2.5-ng, kimi-k2.5-or |
| kimi-k2.6 | kimi-k2.6, kimi-k2.6-go | kimi-k2.6-ng, kimi-k2.6-nw, kimi-k2.6-or |
| mimo-v2.5-free | mimo-v2.5-free | mimo-v2.5-free-go\*, mimo-v2.5-free-ng, mimo-v2.5-free-or |
| minimax-m2.5 | minimax-m2.5, minimax-m2.5-go | minimax-m2.5-ng, minimax-m2.5-or |
| minimax-m2.7 | minimax-m2.7, minimax-m2.7-go | minimax-m2.7-ng, minimax-m2.7-or |
| minimax-m3-free | minimax-m3-free | minimax-m3-free-ng, minimax-m3-free-or |
| nemotron-3-ultra-free | nemotron-3-ultra-free | nemotron-3-ultra-free-go\*, nemotron-3-ultra-free-ng, nemotron-3-ultra-free-or |
| north-mini-code-free | north-mini-code-free | north-mini-code-free-go\*, north-mini-code-free-ng, north-mini-code-free-or |
| qwen3.5-plus | qwen3.5-plus, qwen3.5-plus-go | qwen3.5-plus-ng, qwen3.5-plus-or |
| qwen3.6-plus | qwen3.6-plus, qwen3.6-plus-go | qwen3.6-plus-ng, qwen3.6-plus-or |
| qwen3.6-plus-free | qwen3.6-plus-free | qwen3.6-plus-free-go\*, qwen3.6-plus-free-ng, qwen3.6-plus-free-or |

\* These `*-free-go` entries are already-dangling ids (their model
definitions were removed from `models.json` by the earlier
dead-`*-free-go` prune) — they are inert, compile-time-filtered out of the
served route, and out of this task's scope; left as-is unchanged, exactly
as the prior prune report documented.

**Skipped (zen-only, unchanged):**

| Pool | Members (unchanged) |
|---|---|
| big-pickle | big-pickle, big-pickle-go |
| gpt-5.3-codex-spark | gpt-5.3-codex-spark, gpt-5.3-codex-spark-go |

These two remain effectively dead (their only members hit the depleted
account) until the operator either sources an alternative provider for
`big-pickle` / `gpt-5.3-codex-spark`, or retires the models. Relates to
the pre-existing registry-gap flag from the demote report and ticket #11.

## 5. Verification

- Pool count after: **50** (unchanged), pool-id set identical before/after.
- **0 empty pools** created.
- **0 pools** (outside the 2-pool skip-list) still contain any zen-family
  member, live-reconfirmed against `/data/pools.json` post-apply.
- Full before/after diff of all 50 pools: every edited pool's non-zen
  member subset matches exactly, **in original relative order** — nothing
  else was reordered or dropped. The 2 skip-list pools are byte-identical
  before/after.
- `models.json`: unchanged, still 201 entries — model definitions were not
  touched, only pool membership (avoids emptying the 2 skip-list pools).
- Container: never restarted (`docker ps` uptime climbed monotonically
  across the whole operation).

## 6. Health probes (live chat completions)

3 edited pools probed post-apply, `POST /v1/chat/completions`, `max_tokens: 10`:

| Pool | HTTP | Served by | Response |
|---|---|---|---|
| `claude-sonnet-4-6` | 200 | NanoGPT (`anthropic/claude-sonnet-4.6`) | `"pong"` |
| `gpt-5.4` | 200 | non-zen (`openai/gpt-5.4`) | `"pong"` |
| `kimi-k2.6` | 200 | NanoGPT (`moonshotai/kimi-k2.6`) | `"pong"` |

All 3 returned 200; opencode-zen cannot have served any of them since it
was removed from these pools' member lists entirely (not just deprioritized).

## 7. Mirror regen

Ran `~/.config/opencode/regen-charon-models.sh`:

```
backed up -> /home/stack/.config/opencode/opencode.json.bak-20260707-183735
curated: 30 ids (charon-full removed, opencode-zen disabled)
OK: /home/stack/.config/opencode/opencode.json is valid JSON
```

Pulled live from `GET /v1/models`, not run inside the container.

## Summary

- **47 pools edited**: opencode-zen + opencode-go **fully removed** from
  member lists (not just demoted), non-zen siblings preserved in order.
  Count removed: 92 zen-family member-slots across 47 pools (2 ids × 46
  four-way pools with one gap, see table for exact per-pool counts).
- **2 pools skipped** (`big-pickle`, `gpt-5.3-codex-spark`) — zen-only,
  left untouched per the safety rule; flagged above for a separate
  operator decision (retire vs. source an alternative provider).
- **1 pool untouched** (`auto`) — already zen-free from a prior session.
- 0 failures, 0 empty/broken pools, 0 non-zen members lost or reordered,
  container never restarted, 3/3 health probes green and confirmed
  non-zen-served, local opencode.json mirror refreshed.
- This supersedes the earlier last-resort demote — zen-family is now
  fully absent from every multi-provider pool on 4-LOM.
