# TIER7B — TIER-7 Phase B: multi-tier decompose routing (ADR-0014 D6)

Phase A routed ONE tier per run; a decompose run whose role-DAG stages span tiers
collapsed to a single model. Phase B makes each stage reach ITS tier's model, and
removes the dead `select_live_entry` Phase A orphaned.

## What changed (own: router.py, adapters/acp.py, api.py, failover.py, tests/test_failover.py, tests/test_tier_lifecycle.py)

1. **Backend selection by tier** (`router.py`). `StaticRouter.route` now selects the
   backend whose name == the dispatch's tier vid when one exists, else falls through
   to `candidates[0]`. Added `tier_for(task_class) -> Tier` (pure policy lookup, no
   backend needed) so api can enumerate a decompose run's tiers before any backend
   exists; `route` reuses it. The canonical-tier→vid identity is structural: the
   `Tier` enum values (`low`/`med`/`high`) ARE the canonical tier vids
   (`config.resolve_tier`) and the gateway pool keys (`gateway._tier_pools`).

2. **Warm-agent-per-tier map** (`api.py`). The `role` branch now builds the proxy
   over EVERY tier the run will dispatch to and one reused warm agent per live tier,
   keyed by vid: `run_backends = {vid: AcpBackend(rendered for vid)}`. `_run_tier_vids`
   returns `[tier_vid]` for a plain run (Phase A's **len==1 special case**, preserved
   exactly) and the role-DAG's distinct stage tiers for a decompose run. A stage
   whose tier is dry has no keyed backend, so `route` falls back to the canonical
   (first / role's) live tier — the "relaunch-on-tier-change fallback" of D6, served
   as graceful degradation. The dry-pool `{status:"exhausted"}` early-return (B4) is
   preserved: fires when NO needed tier is live (identical to Phase A for the
   single-tier case).

3. **Dead code removed.** `failover.select_live_entry` had no `src/` caller post
   Phase A (verified: `api.py` references it only in COMMENTS — the B4 re-homing
   docstrings, no live import/call). Removed the function (+ its now-unused `Callable`
   import) and its three tests from `test_failover.py`, leaving a NOTE that tier
   routing now drives the live gateway path instead of an engine-side pool probe.

4. **acp.py** — comment-only update: the per-dispatch tier-vid record and the warm
   agent now have Phase B built (in router/api), so the "not built here" notes were
   corrected. No behavior change — one AcpBackend stays warm for one tier (its vid is
   baked into the rendered launch), which is exactly what the per-tier map needs.

## Tests (`tests/test_tier_lifecycle.py`, new)
- **multi-tier decompose** routes each stage to its tier's model, asserted AT THE
  WIRE (mock upstream records the gateway-rewritten model per dispatch; capture
  pattern from `test_gateway_failover.py:19-31`). Expected sequence is computed from
  the real DAG (not hand-copied), so it tracks policy. `accept=['false']` keeps every
  stage dispatching; the Validate gate stops the pipeline before Close.
- **single-tier run unchanged** — a non-decompose role run hits exactly the role's
  tier model, once (the len==1 map; Phase A intact).
- **warm reuse vs relaunch (D010)** — a warm `AcpBackend` reuses its one subprocess
  across dispatches; the per-tier map holds a distinct subprocess per tier.

## Gate
`pytest` (547 passed), `ruff`, `mypy src/charon` (+ `mypy tests/test_tier_lifecycle.py`),
`check_boundary`, `check_version` — all green. The HARD1 dependency
(`test_run_task_routing.py`, the single-tier routing regression guard) is green on
master and stays green here.

## Note (out of scope)
`tools/check_decisions.py --check` reports two PRE-EXISTING issues (`D002`/`D011`:
`docs/REVIEW-LOG.md not found`) — the shared review-log was migrated to per-ticket
fragments under `docs/review-log/` before this branch. Both reproduce on a clean
`origin/master` checkout and touch no file in this ticket's `owns:`, so they are not
addressed here.
