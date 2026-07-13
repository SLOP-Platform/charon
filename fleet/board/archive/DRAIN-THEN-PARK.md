tier: frontier
difficulty: 5  # auto-seeded from tier (D1 hybrid); refine when purpose is fresh
work_class: money-path
branch: feat/drain-then-park
depends_on: R46-BALANCE-WIRE
real-dep: R46-BALANCE-WIRE build — ADR-0016 (docs/adr/0016-demand-driven-capability-match.md) makes this the
  authoritative serial predecessor: R46 CONSTRUCTS the BalanceTracker from provider config (un-inerts
  record_spend + the modeled/advisory balance) which drain-then-park's park lifecycle reads, and R46 owns the
  SAME gateway.py + balance.py god-files. Genuine shared-file + sensor build prereq (ADR §Build decomposition:
  gateway.py/balance.py contention axis → F29-REGISTRY-SLICE → R46-BALANCE-WIRE → R11-DRAIN-THEN-PARK, strictly
  serial). Supersedes the old METER-MODEL-PROVIDER / DRAIN-ROUTING framing: ADR-0016 confirms the per-(model,
  provider) meter is ALREADY BUILT+WIRED (proxy.py record folds cost; forwarder passes provider=route.label),
  so the missing link is R46's tracker construction, not a fresh meter/drain build.
owns: src/charon/balance.py, src/charon/gateway.py, tests/test_drain_then_park.py
accept: PYTHONPATH=src python3 -m pytest tests/test_drain_then_park.py -v -q
  # FAIL-ON-REVERT (invariants): (1) a class-3 (drain-then-park) provider whose balance reaches
  # ~0 is AUTO-PARKED (marked unavailable; routing skips it, no fail-churn) and RE-ARMS to active when
  # topped up; (2) SOLE-LEG GUARD — a provider that is the ONLY remaining leg of any pool is NEVER
  # auto-parked at 0 (kept/alerted instead of orphaning the pool). Reverting either the park trigger
  # or the sole-leg guard fails the corresponding assertion.
  # (3) REACTIVE SIGNAL IS THE AUTHORITATIVE PARK TRIGGER (verified 2026-07-12 — OPENCODE-GO-USAGE.md;
  #     EXHAUSTION-PARK-TICKETS.md need (A)). Park on the upstream EXHAUSTION RESPONSE, not the modeled
  #     balance. Both signals are ALREADY classified→failover at master (proxy.py:207 _is_billing_error,
  #     _EXHAUSTION_STATUSES={429,402,503}, _EXHAUSTION_BODY_PATTERNS incl "insufficient_balance") but are
  #     NOT yet PARKED — so a drained provider is retried + re-pollutes failover every request (the deepseek
  #     "all_providers_exhausted" churn). Verified signals to PARK on: 401 whose body is CreditsError /
  #     "Insufficient balance" (opencode-zen AND opencode-go — ONE shared prepaid pool, identical 401 on both
  #     bases), OR 429 (nanogpt weekly-quota exhaustion). Modeled balance (starting_usd − spend, from R46) is
  #     ADVISORY/predict-early ONLY — it drifts and there is NO opencode balance endpoint to reconcile it.
  # (4) FUNDING-CLASS RE-ARM TABLE — park + re-arm is PER FUNDING CLASS, not one flag. Cover ≥3 verified classes:
  #     (a) opencode-zen/-go — PREPAID single shared pool; signal 401 CreditsError; re-arm = OPERATOR TOP-UP
  #         ONLY (no periodic refresh — stays parked until topped up / auto-reload fires).
  #     (b) nanogpt — WEEKLY quota; signal 429; re-arm = AUTOMATIC on the weekly reset (park, wait out the
  #         window, a health probe re-arms — no operator action).
  #     (c) neuralwatt — TIERED: primary plan (drained, operator NOT renewing) + secondary OVERAGE pool (credit
  #         remains). Do NOT park when the primary tier exhausts — fall through to overage; park ONLY when the
  #         LAST pool hits zero; re-arm = top-up / none. (Live neuralwatt signal UNVERIFIED locally — key only
  #         on the .60 gateway; confirm signal there before wiring its park.)
  #     Fail-on-revert: a 401-CreditsError provider parks + re-arms-on-topup; a 429-weekly provider parks +
  #     auto-re-arms after the reset window; a tiered provider is NOT parked while any secondary pool has credit.
  #     Revert any class's policy → its assertion RED. (Class-1 nanogpt periodic-reset overlaps FREE-TIER-QUOTA-
  #     SPILL/R10 — this ticket owns the SHARED reactive-park + re-arm mechanism both classes consume.)
prompt: /home/stack/charon-private/prompts/drain-then-park.md   # author at activation
scope: >-
  Operator feature directive (memory charon-drain-then-park-provider-class, 2026-07-09). Model
  providers by FUNDING CLASS and add a first-class drain-then-park lifecycle for CLASS-3 finite
  prepaid credit (OpenRouter ~$9.90, NeuralWatt $22 PAYG, opencode-zen prepaid, DeepSeek $9.99,
  Together $9.83). Taxonomy (cheap-first): (1) free-tier recurring quota, (2) flat subscription
  ($0 marginal), (3) DRAIN-THEN-PARK finite prepaid, (4) true PAYG. Class 3 = drain the finite
  balance first, then AUTO-PARK (deactivate) at ~0 so it stops erroring / failing over, and RE-ARM to
  active on top-up (console toggle — surface in RFL-4). HARD SAFETY GUARD (operator, non-negotiable):
  auto-park must NEVER park a provider that is the sole/only remaining leg of any pool — check pool
  membership before parking; if last leg, keep it (or alert), never orphan the pool. RESOLVED
  ordering: credit (class 3) drained BEFORE flat-fee (class 2) once the credit legs are un-blocked
  (NORMALIZE-CASE-QUANT-FIX + OPENROUTER-FLAKINESS-FIX must land first, else credit-first just
  fail-churns); interim = flat-fee-first. Optional per-provider `expires` field later.

## Dependencies & sequence
depends_on: METER-MODEL-PROVIDER (real balance sensor), DRAIN-ROUTING (funding-class + balance model).
real-dep: both (see above) — genuine correctness prereqs, not merge-order.
couples-with: FREE-TIER-QUOTA-SPILL — these are TWO faces of ONE resource-availability eligibility
  mechanism (mark-unavailable + skip/spill): FREE-TIER handles class-1 quota exhaustion, DRAIN-THEN-PARK
  handles class-3 balance-zero. They share the SAME gateway.py routing-skip surface and the same
  predict-and-switch-at-boundary timing. MANAGER DECISION FLAG: consider FOLDING these into one
  eligibility ticket (fewer serial gateway.py waves, one reviewed money-path surface). If kept
  separate, sequence DRAIN-THEN-PARK immediately after FREE-TIER-QUOTA-SPILL on gateway.py.
wave: WAVE 7 (if kept separate) — after FREE-TIER-QUOTA-SPILL on the gateway.py single-writer chain.
concurrency: co-owns gateway.py with the whole cost chain -> NOT parallel-safe with any of
  DRAIN-ROUTING / COST-RANK-AUTO / POOLS-SIMPLIFICATION / FREE-TIER-QUOTA-SPILL / CAPABILITY-ENGINE;
  co-owns balance.py with METER (before). Disjoint from RFL-*, PFF-P2, bench track.
recommended-model: frontier (Claude Opus 4.8) — money-path lifecycle with the sole-leg safety guard
  and balance-zero edge cases; design-sensitive. ADVERSARIAL review before merge (safety guard is
  where a regression orphans a pool).
note: PARKED — ADR-0016 step #4, staged behind R46-BALANCE-WIRE on the gateway.py/balance.py serial chain
  (exactly as R46 is staged behind F29-REGISTRY-SLICE). UN-PARK THE MOMENT R46-BALANCE-WIRE LANDS. Held parked
  now (not made live) BY DESIGN: un-parking today would RED validate_board — it owns gateway.py (live serial
  chain F29→PROVIDER-PROBE-FIX→PRICING-LIMITS-CHECKER) and balance.py (live GRACEFUL-DEGRADE), both UNSEQUENCED
  relative to it while R46 itself is still parked; and it is premature (its dep R46 is not built). At un-park:
  drop/rewrite the stale prompt field (prompts/drain-then-park.md was never authored — the accept above is
  self-contained), and re-sequence after the then-current gateway.py/balance.py owners. Filed 2026-07-09 (WCI
  designed-work plan); re-pointed to the ADR-0016 serial chain 2026-07-12.
