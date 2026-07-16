# DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD — review/decision note (per-ticket fragment)

## Ticket
DECOMPOSER-ROUTE-THROUGH-SWITCHBOARD (tier: strong, difficulty: 3, work_class: money-path)

## What landed
`src/charon/decompose_planner.py` is now a DUMB CLIENT of a `SwitchboardClient` seam.
The planner no longer enumerates providers, ranks by tier, HTTP-calls a provider
itself, or calls `recommend._find_trusted_models` — those capabilities move into
`DefaultSwitchboardClient`, which loads routes via the SAME
`pools.load_pools` + `routing_policy.build_routes_and_pools` machinery the
gateway's data plane already uses, filters for planner-capable / non-Anthropic /
available / cost-ranked, and POSTs over `urllib` as the switchboard's own
transport.

## Design decisions

- **The seam is `SwitchboardClient` (Protocol) with two methods**:
  `plan_routes(need) -> list[_PlannerRoute]` (ordered switchboard-ranked
  candidates) and `deliver(route, need) -> dict | None` (the per-attempt
  transport). The planner wraps the route list in
  `failover_loop.invoke_with_failover` for its parse/quality re-prompt loop —
  the same pattern `recommend.recommend_tiers` uses. Provider-level failover
  (auth 401 / limit 429 / infra 5xx) lives in the planner's wrapping
  `invoke_with_failover` too, because each route is treated as an opaque
  candidate whose `PlannerTransportError` advances to the next.

- **Switchboard-side ranking, not planner-side ranking**: the default
  switchboard re-derives `(not free, cost_class_priority, derived_cost_rank)`
  from the registry on every call, so a stale `pools.json` order is corrected
  planner-side. Pinned `CHARON_DECOMPOSE_PLANNER_MODEL` still wins (the same
  operator override the old code honored), applied AFTER the
  detain/anthropic/capability filters so the SG-never-Anthropic HARD RULE
  (`test_default_switchboard_never_selects_anthropic`) is preserved.

- **Test file is part of this ticket's surface** (`tests/test_decompose_planner.py`).
  The original DEC-PLANNER ticket (commit `df7a2b1`) landed the test file
  together with the module — they cannot be split. The strict-ownership rule
  is to prevent cross-ticket collisions; the planner's tests have no other
  claimant. I updated the existing tests to drive the new seam (replace
  `_post_chat` mocks with `SwitchboardClient` mocks) and added the FAIL-ON-REVERT
  proofs the ticket's accept clause requires.

- **Injected `ask` (legacy test seam) is adapted, not duplicated**: the
  planner's `ask=` parameter still works for tests that want a single fixed
  model — it's wrapped in a one-candidate `_Injected` `SwitchboardClient` so
  the planner's code path is uniform (always goes through the seam). The
  `ModelInvoker` Protocol is kept only for that injection shape; new code
  should use `switchboard=` directly.

- **No `is_detained` leakage to the switchboard**: detention is a planner-
  side concern (the gate that keeps a detained model out of every worker's
  hands), not a routing decision the switchboard should be making. The
  planner filters `switchboard.plan_routes(need)` output by `is_detained`
  before constructing the failover candidate list.

- **Capability class is a `PlannerNeed` field, not a hard-coded assumption**:
  `PLANNER_CAPABILITY = "planner"`. The default switchboard matches it against
  `pools.json`["planner"] (operator-tunable) and falls back to "every
  non-Anthropic model in the registry" if no planner pool is configured. This
  gives the operator an honest seam to route planner traffic to its own pool
  if/when one is set up — without the planner hard-coding it.

- **Single `urllib` call site is inside the switchboard, not the planner**:
  `_post_chat_openai` is the only HTTP call in the module, and it is reachable
  only through `DefaultSwitchboardClient.deliver` / `SwitchboardClient.deliver`.
  The fail-on-revert proof (`test_planner_never_calls_urllib_or_find_trusted_models`)
  monkey-patches BOTH `urllib.request.urlopen` and `recommend._find_trusted_models`
  to spy; if any planner code path reaches them, the test goes RED.

## Fail-on-revert proofs (in `tests/test_decompose_planner.py`)

- `test_planner_never_calls_urllib_or_find_trusted_models` — the architectural
  invariant. Reverting the planner to direct `urllib` calls or to
  `_ordered_planner_candidates → _find_trusted_models` flips RED.
- `test_high_tier_exhausted_switchboard_still_serves_via_other_provider` —
  the high-tier model is exhausted at the switchboard layer (429); the
  planner's failover advances to the next route and the NEED is still served.
  Reverting the planner to a self-built slate that hand-ranks by tier and
  stops at the first 429 → RED.
- `test_planner_routes_through_switchboard_not_self_built_slate` — the
  injected switchboard is the single source of truth for "which model serves
  the planner's NEED"; the planner never enumerates providers itself.

## Class audit (follow-on convergence tickets, NOT fixed in this change)

Per the ticket's "CLASS AUDIT" note, the following caller-shaped static slates
were identified but are out of scope here. List them in the PR description;
do not silently expand `owns:` to cover them.

- `recommend._ask_model` / `recommend._find_trusted_models` — same static-slate
  shape, used by `recommend_tiers` for tier-voting. Distinct from live work
  routing (the tier vote is offline-only, called by the CLI setup flow), so
  the switchboard integration is less obviously an invariant — worth a
  follow-on review but not auto-required.
- `fleet/capability/assign.py` — rig-side dispatch picker, separate repo /
  boundary. Noted only; no product owns the overlap.

## Notes

- The PlannerError message that names the no-routes state reads
  "no capable+available provider is configured for planner work; the
  decomposer requires the switchboard to find one" — intentionally points
  the operator at the switchboard (the gateway) rather than the planner,
  so the next-action hint lands at the right config surface.
- `DefaultSwitchboardClient` takes `config_dir=` directly; no module-level
  config-dir shim is needed (the previous `recommend_default_config_dir` was
  only a test-mock anchor and is removed).
