repo: charon
tier: frontier
difficulty: 4
work_class: money-path
branch: feat/graceful-degrade
depends_on: ROUTER-CORE
owns: src/charon/router.py, src/charon/failover.py, src/charon/balance.py
serial_justified: the 3 behaviors share ONE park/degrade state machine spanning all 3 files —
  ALERT (behavior 2) fires off the same park state THROTTLE (behavior 1) sets, and AUTO-RECOVER
  (behavior 3) re-arms that same park state; parallel workers editing the shared state contract
  across router.py/failover.py/balance.py concurrently would race on that contract itself.
substrate: LiteLLM — WRAP-AS-PLUGIN candidate, verdict UNRESOLVED and it must be resolved before any hand-rolled park state machine is built, because its Router cooldown and allowed_fails health logic covers most of the retry and degrade mechanics this ticket would otherwise reimplement from scratch
substrate-retest: |
  RE-TEST THE FRAMING THE PRIOR EVAL SKIPPED — plugin-wrap separability, which is the exact gap
  the registry's reason column names. Concretely, and each step is a RUN not a read:
  1. `pip install litellm` into a scratch venv and `import litellm.router` ALONE. Record whether it
     transitively drags fastapi / prisma / uvicorn — the prior rejection ASSERTED it does and never
     executed the import to check.
  2. If it imports clean, instantiate `Router` with two fake deployments and drive a cooldown cycle
     (force allowed_fails, observe the deployment drop out and re-arm). Record the API surface we
     would actually depend on.
  3. Compare against the in-tree `ReviewerCircuitBreaker` (`src/charon/failover.py:73-142`) on the
     three behaviours this ticket needs — throttle, alert, auto-recover.
  4. APPEND a fresh EVAL-REGISTRY row with alignment `aligned` and this evidence, superseding the
     drifted 2026-07-13 row, in a SEPARATE EARLIER commit than this ticket's own.
  A REJECT is a legitimate outcome — but per the registry's own AP-12 rule it requires an EXECUTED
  trial, not a dependency-weight argument.
substrate-detail: |
  NOTE the shape above is dictated by the gate, which matches the FIRST LINE of `substrate:`
  against the EVAL-REGISTRY tool column verbatim — parenthetical scope in that line makes the
  lookup MISS. Recorded here because it is a live example of the registry fragility that
  EVAL-REGISTRY-DERIVE is chartered to fix.
  LiteLLM (Router cooldown / allowed_fails / health) — WRAP-AS-PLUGIN candidate, UNRESOLVED — this
  ticket must NOT treat it as settled in either direction. EVAL-REGISTRY.md carries a row for
  exactly this scope dated 2026-07-13 with verdict UNRESOLVED and alignment DRIFTED, because the
  prior rejections argued "full embed = wrong stack (FastAPI/Postgres/Redis)" and then jumped
  straight to hand-rolling, never testing the plugin-wrap middle option this rig already uses for
  Presidio and OpenTelemetry. The registry's own rule forbids citing a DRIFTED row as closed. So
  before building the park/degrade state machine by hand, answer the one question nobody has:
  is `litellm.Router`'s cooldown logic cleanly separable from the import-monolithic package? If
  yes, wrap it; if no, record WHY with evidence and build the novel slice only.
  Also in scope to check, and cheaper: `tenacity` for the retry/backoff half, and the EXISTING
  in-tree `ReviewerCircuitBreaker` (`src/charon/failover.py:73-142`) which already implements a
  breaker — reuse before rebuild [[adopt-substrate-build-only-novel-slice]].
substrate-novel: |
  What no external library models is Charon's BALANCE-AWARE degradation: parking a provider on
  funding-class + remaining-balance signals, and AUTO-RE-ARMING it when a free-tier window reopens.
  Generic breakers trip on error rate alone and know nothing about money. That coupling of routing
  to balance state is the genuinely novel slice; the retry/backoff/cooldown mechanics are not.
accept: |
  The router's North Star (fleet/state/ROUTER-DESIGN.md §North Star) — three behaviors, each fail-on-revert:
  1. RATE-LIMIT AS BACKPRESSURE: when the only remaining viable provider is rate-limited, the session is
     THROTTLED (queued/slowed) to that provider's limit instead of erroring. Test: with all-but-one
     provider exhausted and that one at its RPM, a burst is throttled+served, NOT failed.
  2. ALERT ON IMPACT: when routing degrades (throttled last-resort, OR a prepaid leg hits zero), the
     operator is NOTIFIED — "performance impacted; refill <provider>". Test: drive a leg to zero -> a
     degradation notice with the provider-to-refill is emitted.
  3. AUTO-RECOVER ON REFILL: after a refill, a health CHECK/probe re-arms the parked provider and routing
     returns to it automatically. Test: park on exhaustion, restore credit, probe passes -> next request
     routes back to it with no manual reconfig.
  RECONCILE 2026-07-12 (EXHAUSTION-PARK-TICKETS.md need (A)): the PARK trigger for behaviors 2/3 is the
  REACTIVE upstream exhaustion response (401 CreditsError body [opencode-zen/-go] OR 429 [nanogpt weekly]),
  NOT the modeled balance — already classified→failover at master (proxy.py:207) but not yet parked; modeled
  balance (R46) is advisory. AUTO-RECOVER is FUNDING-CLASS-AWARE (shared taxonomy owned by R11 DRAIN-THEN-PARK):
  prepaid (opencode-zen) re-arms only after operator TOP-UP; periodic (nanogpt) re-arms AUTOMATICALLY after the
  weekly reset window; tiered (neuralwatt: primary drained + overage remaining) is NOT parked until the LAST
  pool hits zero. Fail-on-revert: each class's re-arm path (topup-probe / window-auto / last-pool-only) asserted.
scope: |
  Operator North Star (2026-07-10): "I don't want to worry about pools/exhaustion IF I have a viable
  option; if the last option is rate-limited, throttle the session; tell me when performance is impacted
  and to refill; on refill, auto-route back to a better provider after a check." Composes with R2
  router-core (invisible failover + throttle), R10 free-tier-quota-spill, R11 drain-then-park (re-arm).
  [[charon-drain-then-park-provider-class]] [[charon-work-engine-vision]]
ds: money-path; sequence AFTER R2 router-core. PROJECT ROUTER.

retired: |
  Park-half SUPERSEDED by live funding_class/drain-then-park (2026-07-23); PR #172 closed. Residual
  alert-on-impact salvaged to DEGRADE-ALERT (P1).
