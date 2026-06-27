# TIER-3 Review Note — `charon tier` CLI

## Design anchors honored

**`tier init`** — calls `config.set_tiers` with the hardcoded DTC defaults:
`order=["low","med","high"]`, `members={"low":["haiku"],"med":["sonnet"],"high":["opus"]}`,
`aliases={opus→high, sonnet→med, haiku→low, frontier→high, strong→med, economy→low}`.
Idempotent — safe to re-run. Day-one == today: each tier's single Anthropic member
matches the legacy fleet model name exactly.

**`tier ranks`** — emits `<name> <rank>` lines for EVERY canonical tier AND every alias.
Consumed by `claim.sh` (TIER-5) ONCE before `flock` into a bash assoc array; non-Anthropic
ranks fall out for free. Legacy fallback when absent: `claim.sh` hardcodes
`[opus]=3 [sonnet]=2 [haiku]=1`.

**`tier resolve <tier> --executor anthropic`** — finds the cheapest member in the tier
whose provider is Anthropic-API-runnable:
- Models in `models.json` with `provider=="anthropic"` qualify.
- Models NOT in `models.json` are assumed to be native Anthropic model names (the legacy
  `haiku`/`sonnet`/`opus` day-one case) and also qualify.
- Sort key: `free→0, cost_rank else 1000` ascending; stable preserves stored order on ties.
- Non-zero exit when no qualifying member exists → shell `||` fallback fires in TIER-6.

**`tier set <tier> --members m1,m2`** — reads current tiers (loading legacy defaults if file
absent), updates the one tier's member list, writes all three tiers atomically via
`config.set_tiers`. Accepts canonical names or aliases (alias-folded via `resolve_tier`).

**`tier list`** — human-readable; degrades gracefully on absent file.

**Graceful degradation** — all five commands call `config.load_tiers()` which returns the
legacy default dict when `tiers.json` is absent. No command fails on a missing file.

## Constraints / decisions

- Imports `config` lazily inside each helper; nothing loaded at module-init (boundary guard
  stays green; `charon version` remains fast).
- `_is_anthropic` treats unknown model ids as Anthropic-runnable: this is the correct
  day-one default when the operator hasn't imported models yet. As they populate `models.json`
  the filter tightens naturally.
- `_cmd_tier` dispatches through named helper functions rather than nesting inside one
  function — easier to unit-test and extend.
- `tier set` without `--members` is a no-op save (idempotent); not tested because the fleet
  never calls it that way.

## Files changed

- `src/charon/cli.py` — added `_tier_init`, `_tier_ranks`, `_tier_list`, `_tier_resolve`,
  `_tier_set`, `_cmd_tier` (lines 431-516 approx) + `tier` subparser block in
  `build_parser()`.
- `tests/test_cli_tier.py` — 14 tests covering all five subcommands, the absent-file
  fallback, the cheapest-member selection, alias resolution, and non-zero exits.

## Gate result

523 passed, ruff clean, mypy clean, boundary OK, version OK.
