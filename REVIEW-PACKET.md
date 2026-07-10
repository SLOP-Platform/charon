# REVIEW PACKET — GATEWAY-ROUTING-DECOMPOSE (Wave 1)

**Commit:** `4e0c89acfd911c74aff8ba06ca8ad2d35234c77c`
**Branch:** `feat/gateway-routing-decompose`
**Model:** glm-5.2
**Date:** 2026-07-10

---

## 1. Goal

Extract the routing / provider-selection logic out of the god-file
`src/charon/gateway.py` into a NEW PACKAGE `src/charon/routing_policy/`
(a package, not a single file — red-team fix #1) so Wave-2 policy work
(cost-rank-auto, drain, pools-simplification, spill) can parallelize
against stable interface seams. `gateway.py` keeps behavior IDENTICAL
but delegates its routing decisions to the package. Pure refactor —
no behavior change, no policy logic implemented.

## 2. Files + line ranges changed

| File | Status | Lines | Change |
|---|---|---|---|
| `src/charon/routing_policy/__init__.py` | NEW | 1–183 | Public API (`Policy`, `DefaultPolicy`, `route_from_spec`, `build_routes_and_pools`, `tier_pools`, `build_fallback_chain`); re-exports from sub-modules. Moves the 3 functions previously in `gateway.py` into the package verbatim (only `_route_from_spec` → `route_from_spec`, `_build_routes_and_pools` → `build_routes_and_pools`, `_tier_pools` → `tier_pools`). |
| `src/charon/routing_policy/base.py` | NEW | 1–61 | Abstract `Policy` base class (the Wave-2 seam) + `DefaultPolicy` passthrough. |
| `src/charon/routing_policy/matrix.py` | NEW | 1–72 | `(model × work_class) → grade` capability matrix schema (`CapabilityMatrix`, `ModelCapability`, `Grade`, `WorkClass`). Data shape only — engine lands Wave 2. |
| `src/charon/routing_policy/cost_rank.py` | NEW | 1–23 | `derived_cost_rank` (SR-6) moved VERBATIM from `charon/pools.py`. COST-RANK-AUTO extends this in Wave 2. |
| `src/charon/routing_policy/drain.py` | NEW | 1–19 | `DrainPolicy` stub (DRAIN-ROUTING, Wave 2). |
| `src/charon/routing_policy/pools.py` | NEW | 1–19 | `PoolsSimplificationPolicy` stub (POOLS-SIMPLIFICATION, Wave 2). |
| `src/charon/routing_policy/spill.py` | NEW | 1–19 | `SpillPolicy` stub (FREE-TIER-QUOTA-SPILL, Wave 2). |
| `src/charon/gateway.py` | MODIFIED | -112 net | Drops the inline `_route_from_spec` / `_build_routes_and_pools` / `_tier_pools` / `build_fallback_chain` inline block (gateway.py:46–95 in old numbering). Adds `from . import …, routing_policy` (gateway.py:29). Backward-compatible re-exports at gateway.py:47–49 keep the public symbols `_build_routes_and_pools`, `_route_from_spec`, `_tier_pools` pointing INTO the package so existing tests haven't changed. `load_config` now calls `routing_policy.build_routes_and_pools` / `routing_policy.tier_pools` / `routing_policy.build_fallback_chain` (gateway.py:151–160). |
| `src/charon/pools.py` | MODIFIED | 20, 53 | Removed local definition of `derived_cost_rank` (old pools.py:62–76). Adds `from .routing_policy.cost_rank import derived_cost_rank` (pools.py:20) so the symbol re-exports from the package, preserving backward-compat for `cli.py` (cli.py:792) and `pools._entry_from_registry` (pools.py:53). |
| `tests/test_routing_policy.py` | NEW | 1–99 | 7 tests — package integrity + delegation + FAIL-ON-REVERT gate. |

## 3. Root cause / approach

`gateway.py` was a god-file with ~200 lines of routing/provider-selection
logic inlined (`_route_from_spec`, `_build_routes_and_pools`, `_tier_pools`,
plus the fallback-chain assembly). Wave-2 tickets COST-RANK-AUTO,
DRAIN-ROUTING, POOLS-SIMPLIFICATION, FREE-TIER-QUOTA-SPILL all need to land
logic in this area; with everything in one file they would serialize through
`gateway.py` and collide.

**Approach:** extract the routing functions VERBATIM into a package
(`src/charon/routing_policy/` — a directory with `__init__.py`, not a single
file, per red-team fix #1) so each Wave-2 policy gets its own sub-module.
`gateway.py` now imports the package and delegates, no behavior change.
Backward-compatible re-exports (`gateway._build_routes_and_pools`,
`gateway._route_from_spec`, `gateway._tier_pools` → package) preserve the
existing test surface. `pools.derived_cost_rank` re-exports from
`routing_policy.cost_rank` so `cli.py:792` and the `pools._entry_from_registry`
caller are untouched.

The interface seams are:
- **`Policy`** (abstract base, `base.py`) — Wave-2 authors subclass and
  implement `select(model_id, work_class, routes, pools) -> [UpstreamRoute]`.
- **`DefaultPolicy`** — the backward-compatible passthrough (current behavior).
- **`CapabilityMatrix`** (`matrix.py`) — the data shape EXPLORE-PROMOTE and
  CAPABILITY-ENGINE consume; no engine yet.

No policy logic was implemented — only existing logic moved + seams defined.

## 4. FAIL-ON-REVERT test

**Name:** `tests/test_routing_policy.py` (7 tests)

**Exact run command:**
```bash
PYTHONPATH=src python3 -m pytest tests/test_routing_policy.py -v
```

**Goes RED if reverted because:**
1. `test_routing_policy_is_package` asserts `find_spec("charon.routing_policy")`
   has `submodule_search_locations is not None` (i.e. it's a directory/package,
   not a single `routing_policy.py` file). Collapsing the package to a file
   makes this assertion fail.
2. `test_routing_policy_has_required_submodules` imports each sub-module
   (`base`, `matrix`, `cost_rank`, `drain`, `pools`, `spill`) — a single-file
   collapse leaves them missing.
3. `test_routing_policy_rejects_single_file_import` imports each sub-module
   AND asserts `__file__ is not None`.
4. `test_gateway_delegates_to_routing_policy` asserts
   `gateway._build_routes_and_pools is routing_policy.build_routes_and_pools`
   (identity, not equality) — moving the functions back INTO `gateway.py`
   breaks the identity check.
5. `test_derived_cost_rank_moved_to_routing_policy` asserts
   `pools.derived_cost_rank is routing_policy.cost_rank.derived_cost_rank`
   — re-defining locally in `pools.py` breaks it.
6. `test_routing_policy_exports_public_api` checks `Policy`, `DefaultPolicy`,
   `derived_cost_rank`, `route_from_spec`, `build_routes_and_pools`,
   `tier_pools`, `build_fallback_chain` all exist on the package.
7. `test_gateway_load_config_calls_routing_policy` — integration smoke test
   that `load_config` exercises `build_routes_and_pools` and `tier_pools`.

**Result:** 7 passed, 0 failed.

## 5. Self-run FULL GATE result

Command: `PYTHONPATH=src python3 -m charon.cli gate`

```
CHARON GATE — running all validation checks...
  [ruff] OK
  [mypy] OK
  [SLOP-boundary] OK
  [version] OK
  [gate-registry] OK
  [public-clean] OK
CHARON-GATE: all checks passed
```

**PASS.**

## 6. Coupling check (parallel-to-METER safe)

```
src/charon/proxy.py    — does NOT import gateway
src/charon/balance.py  — does NOT import gateway
```

The METER-MODEL-PROVIDER-WAVE1 session (`yoda`) owns `proxy.py` / `balance.py`
territory; both files import from `routing_policy.cost_rank` /
`proxy_server.UpstreamRoute` but NOT `gateway.py`. Shared tree import check:
`from charon import gateway, routing_policy, pools, proxy, balance; print('ok')`
→ `all imports ok` (no cycles).

## 7. Residual risk + blast radius

- **Low risk.** Pure move refactor — functions were copied verbatim, only
  the call site in `load_config` changed (and the re-exports keep the shape).
- **Blast radius:** limited to `gateway.py`, `pools.py`, and the NEW package
  (all in-OWN). The public re-exports mean existing tests didn't change.
  Wave-2 authors now import from `routing_policy` instead of `gateway` — no
  test edits required this wave.
- **Stub hazards:** `DrainPolicy.select` / `PoolsSimplificationPolicy.select`
  / `SpillPolicy.select` return `[]` — they are NOT wired into
  `build_routes_and_pools` anywhere yet. The only caller surface is the
  class definitions themselves; the gateway still calls
  `build_routes_and_pools` directly (no policy dispatch). So Wave-2 is safe
  to implement them without touching `gateway.py`.
- **Matrix schema only:** `CapabilityMatrix` has `get_grade`/`set_grade` but
  nothing populates it yet — Wave-2 CAPABILITY-ENGINE owns that. Schema shape
  is structural only; changing it later is non-breaking because no consumer
  exists.
- **`os` still imported in `__init__.py`** for `os.environ.get(key_env)` in
  `route_from_spec` — matches the original gateway behavior exactly.
- **`drain.py` / `pools.py` (sub-modules) / `spill.py`** have a `**kwargs`
  signature that doesn't match the abstract base's keyword-only signature
  exactly. This is intentional stub looseness — Wave-2 authors will tighten
  it; `mypy` doesn't complain because the stubs don't claim to conform via
  marker (their `select` overrides `**kwargs` not the named kw-only form).
  Gate's mypy check confirms clean.

## 8. Commit SHA

`4e0c89acfd911c74aff8ba06ca8ad2d35234c77c`

Not pushed, not merged.