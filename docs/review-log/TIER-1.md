# Tier config store (review note)

Foundation of the model-tier abstraction (DTC: "tier = a first-class, gateway-served
pool in its own namespace"). Extends `src/charon/config.py` in place; adds
`tests/test_tier_config.py`. No other files touched (owns: those two).

## Design anchors honored
- **One canonical vocabulary `low/med/high`** (`types.Tier`). `opus/sonnet/haiku` +
  `frontier/strong/economy` are aliases ONLY. `CANONICAL_TIERS` is fixed; `set_tiers`
  refuses any non-canonical `order` and any alias targeting a non-canonical tier, so
  `capacity.FixedCap` keys can never desync.
- **Tiny optional `tiers.json` in `config_dir()`** — `{order, members, aliases}`. Reuses
  the existing `_load`/`_save` atomic-write pattern (`config.py` `_save`, tmp+replace).
  No new model schema, no DB, no migration runner; members are model ids that already
  live in `models.json`.
- **Absent file → legacy behavior**: `_legacy_tiers()` returns canonical order, legacy
  aliases, and one Anthropic model per tier (`low→haiku, med→sonnet, high→opus`) so
  day-one == today.

## Two decisions worth flagging
1. **`tier_rank` is 1-based, not the literal `order` index.** The work-spec said
   "index into order," but the DTC's own build-rig contract (the work-claim script's example:
   `"low 1\nmed 2\nhigh 3\nopus 3"`) and the legacy fallback ranks
   (`opus=3 sonnet=2 haiku=1`) are both 1-based. Using `order.index(canon)+1` makes the
   canonical and legacy ranks coincide for free (`high=3=opus`), so there is no separate
   legacy-rank table to drift. Unknown names → `0`, matching the work-claim script's `${RANK[$1]:-0}`.
2. **`set_tiers` does NOT verify member ids exist in `models.json`.** It validates id
   format (`_ID_RE`) only. Registry existence is the gateway's concern (the gateway tier-pool work reuses the
   registry at pool-compile time); enforcing it here would couple the store to load order
   and make the round-trip test require seeding models first. Kept decoupled by design.

`resolve_tier` keeps a legacy-synonym fallback even when the file is present, so dropping
a known alias from `tiers.json` never breaks backward compat.

## Gate
`pytest -q`, `ruff check`, `mypy src/charon`, `check_boundary src`, `check_version` all green.
