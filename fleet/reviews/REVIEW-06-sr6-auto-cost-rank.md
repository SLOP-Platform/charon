# Adversarial Review — SR-6 auto-derive cost_rank + cost_class gating

- Branch: `feat/sr6-auto-cost-rank`  (fleet ticket #6 / SR-6)
- Worktree: /home/stack/code/charon-sr6  @ commit `208545e`
- Base: origin/master `f79a898`
- Reviewer stance: adversarial-by-default; verified against the branch, not the commit message.

## Verdict: BLOCK

The headline deliverable — "auto-derive `cost_rank` from SR-5b real per-token
pricing instead of hand-set values" — **does not function in the production
routing path**. It is provably inert for any model created through the normal
config API. The `cost_class` premium-gating half works; the auto-derive half
does not. All new tests pass only because they exclusively exercise a code path
production never takes, which masks the gap. On a money/correctness routing path,
"passes tests but the feature is dead in prod" is a block.

## Changed files (diff --stat origin/master...HEAD)

```
 src/charon/api.py     |   3 +-   # add cost_class to _MODEL_FIELDS web surface
 src/charon/config.py  |  27 +-   # cost_class param + _normalize_cost_class + bulk carry-through
 src/charon/gateway.py |  51 +-   # _derived_cost_rank + premium gating in _build_routes_and_pools
 tests/test_gateway.py | 135 +    # 7 new SR-6 tests
```
Single commit `208545e`. No product code outside these files.

## Gate & tests

- `python3 -m charon.cli gate`:
  - `[ruff] OK`, `[mypy] OK`, `[SLOP-boundary] OK`
  - `[version] VERSION DRIFT: pyproject=0.3.3 installed=0.3.1` → FAILED (exit 1)
  - **This failure is environmental, not the branch.** pyproject is `0.3.3` and
    is NOT touched by this branch; `origin/master:pyproject.toml` is also `0.3.3`;
    the installed editable package in this shared worktree is a stale `0.3.1`.
    origin/master would fail this identical check in this environment. Attempted
    `pip install -e .` to clear it — blocked by PEP 668 (externally-managed env),
    so could not refresh the install read-only. Not a branch defect, but the gate
    is red and must be cleared (reinstall/bump installed pkg) before merge to keep
    the tree honestly green.
- `PYTHONPATH=src python3 -m pytest -q`: **1151 passed** in ~83s. (Includes the 7
  new SR-6 tests, all green.)

## PRIMARY FINDING (BLOCKER) — auto-derive is dead in the production path

`gateway._derived_cost_rank` short-circuits on any explicit `cost_rank`:

```python
explicit = spec.get("cost_rank")
if explicit is not None:
    return int(explicit)          # <-- taken for EVERY real model
```

But every model persisted through the config API **always carries an explicit
`cost_rank`**, because both writers stamp a default:

- `config.add_model` (line 243): `entry = {"free": ..., "cost_rank": int(cost_rank)}`
  — `cost_rank` defaults to `1000`, always written.
- `config.add_models_bulk` (line 281): `"cost_rank": int(e.get("cost_rank", 0 if free else 1000))`
  — always written.

`charon models add` and provider discovery/import (the only ways real models reach
`state_dir/models.json`, which is what `load_config(state_dir=...)` reads in prod)
therefore stamp `cost_rank: 1000` on every paid model. The gateway then reads that
default `1000` as an "operator override" and **never runs the pricing derivation.**

The code cannot distinguish the auto-default `1000` from an operator-chosen `1000`.

### Empirical repro (production path, models.json via add_model)

Two paid models added the normal way, NO explicit cost_rank, cheap vs dear pricing;
pool lists `dear` first:

```
persisted models.json:
   dear  {'free': False, 'cost_rank': 1000, 'cost_input': 5e-06,  'cost_output': 1.5e-05}
   cheap {'free': False, 'cost_rank': 1000, 'cost_input': 5e-07,  'cost_output': 1.5e-06}
pool 'auto' order: ['http://dear/v1', 'http://cheap/v1']   # dear FIRST — WRONG
EXPECTED if SR-6 works:  ['http://cheap/v1','http://dear/v1']
```

The derivation is exercised only by hand-written TOML that omits `cost_rank`
entirely — which is exactly and only what all 7 new tests use. **No test exercises
the models.json / add_model derivation path.** The suite is green and the feature
is non-functional simultaneously; the tests give false confidence on the money path.

### Fix direction (small)
Either (a) stop stamping a default `cost_rank` in `add_model`/`add_models_bulk`
(persist it only when explicitly provided, so `spec.get("cost_rank")` is genuinely
`None` when the operator did not set one), or (b) introduce an explicit
"unset" sentinel distinct from the `1000` default. Then add a test that adds
priced models via `config.add_model`/`add_models_bulk` (NOT raw TOML) and asserts
the derived cheap-first order. Without (a)/(b) the ticket's stated purpose is unmet.

## SECONDARY FINDINGS

1. **Second cost-sort surface not updated (`pools.load_pools`).** `router.py`
   (the ACP router role-pool path) sorts by raw `int(spec.get("cost_rank", 1000))`
   in `pools.py:91` and was NOT changed by SR-6. The gateway docstring even claims
   the ordering "matches `pools.load_pools` (D4)" — but for any TOML model without
   `cost_rank` the two surfaces would now diverge (gateway derives from pricing,
   router uses `1000`). In practice they still agree today only *because* the
   primary bug keeps derivation from ever firing. If the primary bug is fixed,
   this divergence becomes live and must be fixed in lockstep.

2. **Blended formula & scale — correct where it runs.** `blended = (3*cost_input +
   cost_output)/4`, then `round(blended * 1e6 * 100)`. Pricing is canonical
   per-token USD (`providers._extract_pricing`), so `$0.5/1M in + $1.5/1M out`
   → blended `$0.75/1M` → rank `75`; `$5/$15` → `750`. Monotonic, non-negative
   (`max(0, ...)`), free-first preserved via the `(not free, rank)` tuple. The
   3:1 in:out weighting is an arbitrary-but-reasonable heuristic; documented.

3. **Missing-pricing handling is safe.** Both `cost_input`/`cost_output` absent →
   returns neutral `1000` (no crash, no divide-by-zero — division is by the
   constant 4). One-sided pricing coerces the missing side to `0.0`.

4. **cost_class handling is sound.** `_normalize_cost_class` lowercases, validates
   against the enum, silently drops unknowns (tested for add_model and bulk).
   Premium gating removes premium members from cheap-first chains but keeps them in
   `routes` (explicitly requestable), and refuses to silently empty an all-premium
   pool (operator opt-in). This half of the ticket is correct and does work in prod
   (cost_class is read as its own field, not gated behind the cost_rank default).

## Blast radius / live pools (deepseek-v4-pro / gpt-5.5, NanoGPT anchor)

No live regression risk from this branch: because the primary bug makes derivation
inert, all real models keep whatever `cost_rank` they already have (default `1000`
→ tie → stable listed-order sort). NanoGPT stays anchored iff it is already listed
as such; SR-6 does not reorder live pools. So the branch is *safe* but *ineffective*
— it neither breaks routing nor delivers the cheaper-first behavior it promises.

## Product / build-rig boundary

Clean. Diff scanned for `/home/stack`, `fleet`, `SLOP`, `runner`, `charon-private`
— zero hits in committed src/config. `[SLOP-boundary]` gate check passes.

## Summary

- cost_class premium-gating: correct, works in prod, well-tested. ✅
- auto-derive cost_rank from pricing: implemented but unreachable in prod; tests
  cover only the TOML path and mask it. ❌ (blocker)
- Fix is small (don't stamp default cost_rank / use an unset sentinel) + add a
  models.json-path test + reconcile `pools.load_pools`. Re-review after.
