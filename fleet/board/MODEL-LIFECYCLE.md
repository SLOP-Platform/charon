tier: frontier
difficulty: 4
work_class: ci-infra
branch: feat/model-lifecycle
repo: charon
depends_on: PROVIDER-CATALOG-REFRESH, MODEL-PREFLIGHT, ADD-PROVIDER-MECHANIZE
real-dep: PROVIDER-CATALOG-REFRESH — the orchestrator invokes it as the discover step; can't chain what doesn't exist.
real-dep: MODEL-PREFLIGHT — the orchestrator invokes it as the screen step; can't chain what doesn't exist.
real-dep: ADD-PROVIDER-MECHANIZE — the orchestrator invokes it as the link step; can't chain what doesn't exist.
owns: src/charon/lifecycle.py, tests/test_lifecycle.py
accept: |
  The self-managing capability lifecycle (operator vision 2026-07-13): a fresh Charon install AUTO-onboards its
  model roster and keeps it fresh on a schedule — no manual mapping/screening. ONE orchestrator over the components.
  BOOTSTRAP (fresh install / `charon setup` extension): link providers (keys) -> discover/import each provider's
  models (PROVIDER-CATALOG-REFRESH / `models import` / `discover`) -> run MODEL-PREFLIGHT on the NEW models
  (OOB-graded) -> populate the catalog (model->provider->price) + AUTO-ASSIGN tiers from the preflight winners +
  cost rank. Trusted-only (DETENTION-REDLINE) + fed to the scorecard.
  SCHEDULED KEEP-FRESH (TTL/cron, like sync-checkouts): re-discover -> preflight ONLY new/changed models
  (INCREMENTAL — never re-screen the whole roster) -> refresh prices/catalog -> re-tier. Idempotent, off-hot-path,
  stale-but-usable on failure. Detention re-evaluates from fresh actuals each cycle.
  SCALE (hard requirement — preflight is EXPENSIVE, ~42 sessions/model; hundreds of models = DAYS if exhaustive, so
  NEVER screen the whole roster at once): (1) OPERATOR-SELECTED models first; (2) then PRIORITIZED order — by tier
  NEED (understaffed tiers first), likely value, then cost (cheap models for economy tiers); skip obvious non-starters;
  (3) INCREMENTAL — an already-screened model is never re-run (cache the verdict; only new/changed); (4) BOUNDED per
  cycle — screen at most K models within a token/time BUDGET, so a cycle never blocks or runs away. This is the smart
  logical batching; screening is prioritized+incremental+budgeted, not exhaustive.
  DO: a lifecycle orchestrator that composes the four components with clean seams (each component already
  standalone); a bootstrap entrypoint (wired into `charon setup`) + a scheduled entrypoint (cron/timer). NO
  re-implementation of the components — orchestrate them.
  FAIL-ON-REVERT (tests/test_lifecycle.py): a fresh-install fixture (2 mock providers) runs bootstrap -> models
  discovered, preflighted (mock graders), catalog+tiers populated with ONLY the passing models; a scheduled run
  with a NEW mock model preflights just that one (incremental) and adds it; a model that fails preflight is NOT
  tiered. Revert the preflight-gate in the chain -> a failing model gets tiered -> RED.
scope: |
  ROUTER/work-engine — the provider/model/tier management half of the north-star work engine, made automatic +
  scheduled. The capstone that ties ADD-PROVIDER + CATALOG-REFRESH + PREFLIGHT + tiering into one self-onboarding,
  self-maintaining roster. [[charon-work-engine-vision]] [[charon-production-readiness-mindset]]
  [[charon-pools-redesign]] [[benchmark-not-a-valid-ranker]] [[charon-gateway-config-how-to]]
ds: |
  depends_on: PROVIDER-CATALOG-REFRESH + MODEL-PREFLIGHT + ADD-PROVIDER-MECHANIZE (the composed components). Runs
  LAST of the Model-Trust epic. Design-first (grounded orchestration, do not build the components into it). Money/
  capability-path: adversarial review. Schedule mechanized like sync-checkouts / SYNC-SCHEDULE.
note: operator vision — fresh-install auto-onboard + scheduled keep-fresh of the model roster; orchestrator over the 4 components.
