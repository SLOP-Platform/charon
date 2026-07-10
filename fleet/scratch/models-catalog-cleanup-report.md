# opencode `/models` picker cleanup — 2026-07-07

Scope: rig-only opencode picker config. No Charon product code touched, no
gateway pool config touched, no push, no opencode restart (takes effect on
operator's next opencode restart).

## Backup

True pre-change snapshot (23971 bytes, matches original exactly):

```
/home/stack/.config/opencode/opencode.json.bak-20260707-183516
```

(A second backup, `...-183606`, was made automatically by
`regen-charon-models.sh` when I re-ran it to verify regen-survivability —
that one snapshots the already-cleaned intermediate state, not the
original. Use `-183516` to restore pre-cleanup.)

## Grounding: how each group in the picker was produced

- **"Charon Gateway"** (`provider.charon` in `opencode.json`) — curated
  allowlist, built by `~/.config/opencode/regen-charon-models.sh` from a
  hand-maintained `CURATED_IDS` array (~30 ids) cross-checked against the
  gateway's live `GET /v1/models`. Bare kebab ids already (`glm-5.2`, not
  `charon/glm-5.2` — the `charon/` prefix only appears at the
  `provider/model` reference level, e.g. `config.model`).
- **"Charon Gateway (all models)"** (`provider.charon-full`) — same
  script, same provider block cloned with `name` overridden and `models`
  set to *every* id from the live `/v1/models` response (201 ids). Pure
  duplicate of the curated group at a different completeness level.
- **"OpenCode Zen"** — **not defined anywhere in `opencode.json` at all.**
  It's opencode's own built-in provider (id `opencode`, display name
  `"OpenCode Zen"`), auto-loaded from the models.dev registry
  (confirmed via `~/.cache/opencode/models.json` → `data["opencode"]`:
  `id: "opencode"`, `name: "OpenCode Zen"`, 75 models) whenever local
  auth for it exists. This is where the Title-Case names + `" Free"`
  suffixes come from (e.g. `hy3-free` → `"Hy3 Free"`,
  `north-mini-code-free` → `"North Mini Code Free"`,
  `deepseek-v4-flash-free` → `"DeepSeek V4 Flash Free"`) — confirmed
  against opencode's `Config.disabled_providers` schema
  (`opencode.ai/config.json`) and the SDK type defs bundled in
  `~/.config/opencode/node_modules/@opencode-ai/sdk`.

## BEFORE (`provider` block)

| key | name | # models |
|---|---|---|
| `charon` | Charon Gateway | 30 |
| `charon-full` | Charon Gateway (all models) | 201 |
| *(none — auto-loaded)* | OpenCode Zen | 75 |

Plus one naming inconsistency inside `charon`: `gpt-5.4-mini` carried an
explicit override `"name": "Charon gpt-5.4-mini"` (Title-Case-prefixed),
while every other entry had no override (bare id, uniform kebab form).

## AFTER (`provider` block)

| key | name | # models |
|---|---|---|
| `charon` | Charon Gateway | 30 |

Plus new top-level: `"disabled_providers": ["opencode"]`.

`gpt-5.4-mini`'s stray name override was removed (cost/limit metadata
kept) so every entry in the one remaining group is uniform: bare kebab
id, no per-entry display-name override.

## What was removed / why

1. **"OpenCode Zen" direct group** — disabled via top-level
   `disabled_providers: ["opencode"]` in `opencode.json`. This is the only
   config-level lever for an auto-loaded built-in provider (there's no
   `provider.opencode` block to delete — it isn't in the file). Confirmed
   the field against the live `opencode.ai/config.json` schema:
   `disabled_providers: string[]` — "Disable providers that are loaded
   automatically." Depleted-account models (Hy3 Free, North Mini Code
   Free, Nemotron 3 Ultra Free, DeepSeek V4 Flash Free, Big Pickle,
   MiMo V2.5 Free, etc.) are no longer selectable in `/model`.
   **This does not touch the Charon gateway's own pool config on
   4-LOM** — Charon's `big-pickle`/`mimo-v2.5-*`/etc. pool members that
   route *through* the gateway (`provider.charon`) are untouched and
   still reachable via their Charon-normalized ids.
2. **"Charon Gateway (all models)" duplicate group** — deleted
   `provider.charon-full` entirely, both from the live `opencode.json`
   and from the generator (`regen-charon-models.sh` no longer builds it).
   The operator's ask was literally "consolidate to ONE Charon catalog" —
   so the 201-id superset is gone, not merged. If you later want to reach
   an id outside the curated ~30, the mechanism is unchanged: add it to
   `CURATED_IDS` in `regen-charon-models.sh` and re-run.
3. **Naming inconsistency** — removed the lone `gpt-5.4-mini` Title-Case
   name override. All 30 curated entries are now uniform bare-kebab-id,
   no-override.

## Result: "Charon Gateway" is now first/primary automatically

Since it's the only provider group left in the config, it's trivially
top/primary in the `/model` picker — no explicit ordering trick was
needed. Default `config.model` (`charon/gpt-5.4`) still resolves fine.

## Bypass-Charon default — FLAGGED, NOT ADDED (needs operator confirmation)

Checked all three places a direct-provider bypass could live:
`opencode.json`'s `provider` block (only ever had `charon`/`charon-full`),
shell env for provider API keys (`env | grep -i _API_KEY\|_TOKEN`, only
`CHARON_GATEWAY_TOKEN` present), and opencode's local credential store
(`~/.local/share/opencode/opencode.db` → `credential` table, empty).

**Conclusion: there was no direct-provider bypass configured before this
cleanup.** The only other selectable group was "OpenCode Zen" itself,
which is being removed per requirement 2. So after this change, **the
`/model` picker has exactly one group and zero fallback if the Charon
gateway itself is down** — there is no direct OpenRouter/NanoGPT/etc.
entry to fall back to from inside opencode.

Per instruction, I did **not** silently add one. If you want a bypass
option, tell me which funded/reliable provider to wire up (OpenRouter
direct and NanoGPT direct were the two candidates named in the brief) and
I'll add a single `provider.<name>` block with its own `npm`/`baseURL`/
`apiKey` and a matching curated model list — same pattern as `charon`.

## Survives future regens?

Yes. `regen-charon-models.sh` was updated (not just the output):
- No longer builds/writes a `charon-full` block.
- On every run, defensively pops any stray `provider.charon-full` and
  ensures `"opencode"` is present in `disabled_providers` — idempotent,
  so even a hand-edited `opencode.json` that regresses gets re-cleaned on
  next regen.
- Re-ran it live against the real gateway (`10.0.1.60:8080`, reachable
  from this box) to verify: output is byte-for-byte the same shape as the
  manual cleanup — `provider` keys `['charon']`, `disabled_providers:
  ['opencode']`, 30 curated models, no `charon-full`, `gpt-5.4-mini`
  override still absent, `config.model` still `charon/gpt-5.4`.

## Files touched

- `/home/stack/.config/opencode/opencode.json` (cleaned; regenerated live
  during verification, so its `.bak-*` timestamp trail includes both the
  manual edit backup and the regen-run backup — see Backup section above)
- `/home/stack/.config/opencode/regen-charon-models.sh` (generator logic
  + header comment updated)

No restart triggered. Takes effect on the operator's next opencode
restart.

---

# ADDENDUM — 2026-07-07: both bypass providers wired in (operator decision)

Operator decided to add BOTH OpenRouter-direct and NanoGPT-direct as
emergency-bypass provider groups, listed below the primary Charon Gateway
group. Purpose: usable fallback when the Charon gateway itself is down.

## Backup (this round)

Pre-bypass snapshot (the cleaned single-Charon state, 9617 bytes):

```
/home/stack/.config/opencode/opencode.json.bak-20260707-184453-prebypass
```

## Bypass groups added

Both are OpenAI-compatible custom providers
(`npm: "@ai-sdk/openai-compatible"`) pointing at each service's DIRECT
endpoint — base URLs confirmed from the gateway's own provider presets on
4-LOM (`src/charon/providers.py` PRESETS, both marked "base verified live"):

| provider key | display name | baseURL | curated models |
|---|---|---|---|
| `openrouter` | OpenRouter (direct — Charon bypass) | `https://openrouter.ai/api/v1` | `deepseek/deepseek-chat-v3.1`, `deepseek/deepseek-v3.2`, `z-ai/glm-5.2`, `anthropic/claude-sonnet-4.5` |
| `nanogpt` | NanoGPT (direct — Charon bypass) | `https://nano-gpt.com/api/v1` | `deepseek/deepseek-v4-flash`, `deepseek/deepseek-v4-pro`, `openai/gpt-5.4`, `claude-sonnet-4-5-20250929` |

Model ids are each service's OWN native ids (not Charon-normalized ids) —
validated against each direct `/models` endpoint (OpenRouter 343 models,
NanoGPT 603 models) so the fallback actually resolves. Kept intentionally
small (4 each) — this is an emergency fallback, not the daily driver.

## How the keys are sourced / secured

- Keys pulled from the gateway's own secrets on 4-LOM
  (`/data/secrets.json` inside `charon-gateway-1`: `OPENROUTER_API_KEY`,
  `NANOGPT_API_KEY`) over `ssh -i ~/.ssh/4lom stack@10.0.1.60`.
- Written to per-provider 0600 files in a 0700 dir, **never printed**:
  - `~/.config/opencode/secrets/openrouter.key` (0600)
  - `~/.config/opencode/secrets/nanogpt.key` (0600)
- `opencode.json` references them via opencode's `{file:...}` substitution
  (confirmed supported in current opencode config docs), so **no plaintext
  key is stored in opencode.json**:
  - `"apiKey": "{file:~/.config/opencode/secrets/openrouter.key}"`
  - `"apiKey": "{file:~/.config/opencode/secrets/nanogpt.key}"`
  (Note: the pre-existing `charon` provider still holds its gateway token
  inline — unchanged, out of scope. Only the two new groups use file refs.)

## Verified end-to-end

- OpenRouter: `POST /chat/completions` with `deepseek/deepseek-chat-v3.1`
  (from this box) → 200, model replied. Key + endpoint good.
- NanoGPT: `POST /chat/completions` with `deepseek/deepseek-v4-flash`
  (from 4-LOM; nano-gpt.com is not reachable from the agent box) → 200,
  model replied. Key + endpoint good.

## Final picker order

1. **Charon Gateway** (`charon`) — primary/first, 30 curated models.
2. **OpenRouter (direct — Charon bypass)** (`openrouter`) — 4 models.
3. **NanoGPT (direct — Charon bypass)** (`nanogpt`) — 4 models.

`disabled_providers: ["opencode"]` unchanged — OpenCode Zen stays hidden.

## Survives regen

`regen-charon-models.sh` updated: a `BYPASS` block now re-asserts both
groups on every run (recreates a group if hand-deleted; leaves an existing
group's model list untouched so operator curation isn't clobbered; always
re-asserts base_url/apiKey-file-ref/name), and the final provider order is
forced to `charon, openrouter, nanogpt`. Re-ran the script live against
the real gateway to confirm: output = `provider` keys
`['charon','openrouter','nanogpt']`, `disabled_providers: ['opencode']`,
`{file:...}` key refs intact, valid JSON.

No opencode restart triggered — takes effect on the operator's next
opencode restart. The `~/.config/opencode/secrets/` key files must exist
on whatever machine runs opencode (they were created on this box); if the
operator runs opencode elsewhere, copy that dir (0600) or set the two env
vars and switch the refs to `{env:OPENROUTER_API_KEY}` / `{env:NANOGPT_API_KEY}`.
