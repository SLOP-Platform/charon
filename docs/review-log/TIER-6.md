# De-hardwire the build-rig worker launcher (tier → concrete Anthropic model)

**Owns:** the private build rig's worker launcher script (ships nowhere near the Charon
product). **Depends on:** the `charon tier` CLI work (`charon tier resolve … --executor
anthropic`, merged).

## Change

- **Arg allowlist widened** to canonical **and** legacy tiers:
  `opus|sonnet|haiku|low|med|high) TIER="$1"; shift;;` (+ usage strings).
- **Launch model de-hardwired:** replaced `MODEL="$TIER"` with
  `MODEL="$(charon tier resolve "$TIER" --executor anthropic 2>/dev/null)" || MODEL="$TIER"`.
  The `claude -p --model "$MODEL"` launch and the entire claim/PR flow are untouched.

## Design anchors (DTC-tier-abstraction.md §"Build-rig consumption")

- **No gateway on the build-rig path.** `claude -p` speaks the Anthropic Messages API; the gateway
  is OpenAI-only (`proxy_server.py` forwards `chat/completions`, no `/v1/messages`). So the
  build rig does **not** route through the gateway — it resolves tier → *concrete Anthropic model
  name* via a config lookup. No Anthropic↔OpenAI shim. (DTC decision: "the build rig keeps its
  Anthropic executor; only the engine consumes multi-provider pools.")
- **`--executor anthropic`** returns the cheapest live tier member whose provider is
  Anthropic-API-runnable, so `claude -p` can actually execute it (the `charon tier` CLI's `_tier_resolve`:
  free-first → `cost_rank`, anthropic-only filter, non-zero exit when none/no-config).
- **`|| MODEL="$TIER"` keeps half-migrated setups working.** When `tiers.json` is absent (or
  `charon` is missing entirely), `resolve` exits non-zero → fallback fires → legacy
  `opus/sonnet/haiku` launch unchanged. `2>/dev/null` keeps the fallback silent. `set -e` is
  not tripped because the assignment is guarded by `||`.

## Verification (dry)

- `bash -n` on the launcher script → syntax OK.
- Config present (seeded `tiers.json`): `tier resolve high --executor anthropic` → `opus`
  (exit 0); alias `tier resolve opus …` → `opus` (exit 0).
- Config absent / `charon` missing: substitution exits non-zero → `MODEL="$TIER"` (legacy
  `opus`/`high` launch unchanged).

## Scope

Single owned file edited; no Charon source touched; the work-claim script is untouched
(separate ticket). POSIX-bash, no new
deps, no secrets. Review note is this per-ticket fragment (never the shared `REVIEW-LOG.md`).
