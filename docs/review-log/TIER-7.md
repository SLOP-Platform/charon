# TIER-7 review note — engine tier routing

**Branch:** `feat/engine-tier-route`
**Owns:** `src/charon/adapters/acp.py`, `tests/test_acp_tier_route.py`

## Decision

`AcpBackend.dispatch()` now calls `config.tier_members(tier.value)` before
`_start()`. If the tier has members, it creates a shallow env copy with
`ANTHROPIC_MODEL = tier.value` (e.g. `"med"`) so the gateway resolves the tier
pool and fails over across members transparently.

## Design anchors cited

- **Tier vid as model id (DTC §"Engine consumption"):** `tier.value` is already
  the canonical `low/med/high` string. Injecting it directly as `ANTHROPIC_MODEL`
  means the gateway request body carries `model: "med"` → `_tier_pools()` resolves
  to the `med` chain. No translation shim; one vocabulary across caps, pools, fleet.
- **Caps keyed on canonical tier:** `FixedCap` (and `AimdCap`) already key on
  `tier.value` via the scheduler; `dispatch()` never touches caps so they remain
  on the canonical string regardless of this change.
- **No regression (absent tiers.json):** `config.tier_members()` returns `[]` only
  when the tier has no members configured. An empty list gates the injection — the
  subprocess env is unmodified and the agent uses its own model config. The
  `_legacy_tiers()` default always seeds members for all canonical tiers, so a
  fresh install with no `tiers.json` still gets the injection (pointing the gateway
  to `low/med/high` pools compiled from the legacy `haiku/sonnet/opus` seeds).
- **Caller env not mutated:** `{**env, "ANTHROPIC_MODEL": tier_vid}` always creates
  a new dict; the coordinator's env dict is untouched.
- **Passthrough wins:** `_start()` merges `{**env, **self.passthrough_env}`, so an
  operator-supplied `passthrough_env["ANTHROPIC_MODEL"]` pins a concrete model
  id even after tier injection.

## Files changed

- `src/charon/adapters/acp.py` — 9-line addition at the top of `dispatch()`;
  lazy import of `config` matches the existing `gitutil` pattern.
- `tests/test_acp_tier_route.py` — 7 tests (parametrized low/med/high, absent
  config, passthrough wins, caller env immutability, canonical values assertion).

## Gate result

520 tests pass, ruff clean, mypy clean, boundary OK, version OK.
