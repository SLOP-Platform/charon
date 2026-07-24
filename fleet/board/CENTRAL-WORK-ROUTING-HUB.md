repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: rig-meta
branch: feat/central-work-routing-hub
owns: fleet/work-hub.sh, fleet/tests/work-hub.test.sh, docs/adr/ADR-CENTRAL-WORK-HUB.md
depends_on: FLEET-DEMAND-DRIVEN-ROUTING
real-dep: FLEET-DEMAND-DRIVEN-ROUTING — the hub composes the broker's route+failover; not just merge-order
serial_justified: the hub IS the integration — decompose + tier + route + failover behind ONE entry is the
  whole point; shipping the pieces without the single entry is the scattered state this ticket exists to end.
source: |
  operator directive 2026-07-24 — the north-star ([charon-work-engine-vision]). ONE central hub: a work request
  -> (decompose when sane) -> assign tier -> confirm AVAILABLE providers (limits/funding/perf; PRIMARY=cost) ->
  route to the cheapest AVAILABLE model AT-OR-ABOVE the capability FLOOR -> auto-failover to the next
  provider/model on any issue -> escalate UP a tier when the floor is exhausted (NEVER below — frontier work
  never lands on an economy model). Attached to ALL frameworks (model-ranking, provider cost/limits,
  balance/funding). Operator REQUIREMENTS: mechanized · VISIBLE (in the graphify code map) · FAIL-LOUD (tested +
  dogfooded) · cost-cap guardrail (approved).
note: |
  COMPOSE, do NOT rebuild, the existing pieces behind one entry (fleet/work-hub.sh):
  - decompose: WORK-DECOMPOSER (done) · tier: fleet/capability/tier_classify.py (built)
  - route by availability+cost: the broker (assign.py capped-skip + gateway litellm.Router)
  - failover UP, never below floor: spill-up (FLEET-DEMAND-DRIVEN-ROUTING #3, built)
  - GUARDRAIL: per-window spill COST-CAP — when exceeded, HOLD/queue rather than keep escalating
  - frameworks: emits to model-scorecard (ranking), reads pricing-limits (cost) + balance (funding)
  The four hard requirements are ACCEPT items, not aspirations: MECHANIZED (one entry, no manual routing),
  VISIBLE (a real wired node in the graphify code map — not orphaned), FAIL-LOUD (routing failure is loud +
  tested), DOGFOODED (an e2e real request routes end-to-end to a live model).
accept: |
  - ONE entry-point runs decompose->tier->route->failover->escalate by composing the existing pieces (no rebuild).
  - capability FLOOR honored: never routes below the assigned tier; escalates UP when the floor tier is exhausted.
  - COST-CAP guardrail PROVEN: seed a free-tier drain -> spill caps at the per-window budget -> holds/queues (not
    a stampede to frontier).
  - VISIBLE: `graphify explain "work-hub"` shows it as a wired node reaching decompose/classify/route — a
    reachability test asserts it is not orphaned/inert.
  - FAIL-LOUD + DOGFOOD: an e2e REAL work request routes through the hub to a live model; a forced routing
    failure is loud + tested; fail-on-revert.
  - attached to frameworks: emits a scorecard row, reads pricing-limits + balance on a real run.
  - ADVERSARIAL REVIEW (money-path north-star).
scope: |
  The composition entry-point + cost-cap guardrail + framework wiring + code-map visibility. Does NOT rebuild
  decompose/classify/route/failover (they exist) — it UNIFIES them behind one mechanized, visible, fail-loud,
  dogfooded entry. Reconciles + supersedes the scattered WORK-ROUTING-TO-CHARON-ENGINE / B6 / B7 (do not duplicate).
ds: |
  ## Dependencies & sequence
  P0 frontier — the anchoring lens ("work -> route"). Composes FLEET-DEMAND-DRIVEN-ROUTING (broker) +
  WORK-DECOMPOSER (done) + tier_classify.py. Build AFTER the broker (#2/#3) + classifier land, since it
  integrates them. Absorbs WORK-ROUTING-TO-CHARON-ENGINE/B6/B7 — retire those as separate items.
