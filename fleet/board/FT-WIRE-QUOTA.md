repo: charon
tier: strong
difficulty: 4
work_class: money-path
branch: feat/ft-wire-quota
depends_on: FT-QUOTA-ENGINE, FT-CONFIG-SURFACE, FT-CATALOG-SEED, FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE, PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING
dep-kind: build
serial_justified: cohesive single wiring — all logic lives in the new free_tier_gate.py; the forwarder.py + gateway.py edits are one minimal injection call each and must land together as one activation.
real-dep: |
  Shares SAME-FILE surface with in-flight tickets — must rebase onto their merges, NEVER run as a
  concurrent second writer: forwarder.py (FAIL-LOUD-CONTRACT, FORWARDER-RECONCILE) and gateway.py
  (PROVIDER-PROBE-FIX, GATEWAY-NONTOKEN-METERING — PRICING-LIMITS-CHECKER was decomposed
  2026-07-15; GATEWAY-NONTOKEN-METERING is its gateway.py-owning child, PRICING-LIMITS-CHECK-SH is
  the rig-only sibling with no gateway.py edit). Also needs FT-QUOTA-ENGINE (the engine), FT-CONFIG-SURFACE
  (the limits shape) and FT-CATALOG-SEED (the seed) merged first. Keep the forwarder/gateway edits MINIMAL
  (one build call + one skip call); all real logic lives in the new free_tier_gate.py to shrink the collision.
owns: src/charon/forwarder.py, src/charon/gateway.py, src/charon/routing_policy/free_tier_gate.py, tests/test_free_tier_gate.py
accept: |
  Activate the inert QuotaTracker so the gateway is PROACTIVELY free-tier-aware: skip a free leg BEFORE it
  hits its rpd/rpm/tpm/tpd wall, falling to the next-cheapest available leg (next free tier, then
  drain-first paid) — never stall. Today QuotaTracker (src/charon/quota.py) is dead code; the gateway only
  reacts AFTER a 402/429 returns (forwarder.py:557-574), so free tiers are neither used to their limit nor
  respected before the wall.
  DO:
  - src/charon/routing_policy/free_tier_gate.py (NEW): a thin wrapper owning the QuotaTracker instance +
    the skip decision. Given the ordered candidate legs for a request + an est_tokens, drop any leg whose
    QuotaTracker.should_skip is True, preserving order (so the next-cheapest AVAILABLE leg — free first,
    then drain-first paid via the existing funding-class order — is chosen). After a call completes, call
    record(provider, tokens_used). est_tokens: reuse whatever token estimate the forwarder/cost path
    already computes; do NOT add a new tokenizer.
  - src/charon/gateway.py: add _build_quota_tracker(providers_cfg, state_dir) sibling to
    _build_balance_tracker (same resolved state_dir), fed by FT-CONFIG-SURFACE's per-leg free_tier limits,
    falling back to FT-CATALOG-SEED's free_tier_catalog for a known leg with no explicit config. Wire it
    into GatewayProxyServer like balance_tracker.
  - src/charon/forwarder.py: at leg selection (where order_by_cooldown / funding-class order is applied),
    consult free_tier_gate to drop at-ceiling free legs BEFORE dispatch, and record() usage after. ONE
    injection point; do not scatter quota logic through the loop.
  - >=1-VIABLE: never skip the LAST viable leg on a quota ceiling — if quota would empty the candidate set,
    keep the least-over-ceiling leg (mirrors the balance sole-leg guard; ties into S8). A ceiling-skip must
    be observable (a counter/log), never silent.
  FAIL-ON-REVERT (tests/test_free_tier_gate.py, new, hermetic — no network): with a free leg configured at
  rpd=2 and a paid fallback, the 3rd request in a day ROUTES TO THE PAID leg (proactive skip, not a 402);
  reset the day → free leg is used again; a free leg with NO paid fallback at ceiling is KEPT (sole-viable),
  logged. Revert the should_skip wiring → the 3rd request still hits the free leg → test fails.
