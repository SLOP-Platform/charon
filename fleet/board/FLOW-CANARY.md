repo: charon-private
tier: strong
difficulty: 4
work_class: money-path
priority: 0
branch: feat/flow-canary
owns: fleet/flow-canary.sh, fleet/tests/flow-canary.test.sh
depends_on:
substrate: N/A
substrate-novel: |
  No external synthetic-monitoring tool (blackbox_exporter, uptime probes, curl-based
  smoke) can assert Charon's OWN internal observable effects — X-Charon-Provider routing,
  free-first funding_class ordering, the observer meter DELTA, and parked/drained
  exclusion (#188). Those are Charon-specific semantics, readable only from the gateway's
  own /charon/status snapshot + `charon tier ranks`. This canary ADOPTS those live
  surfaces (it does not re-implement the meter or the tier SSOT); the novel slice is the
  assertion composition that turns them into a RED-on-silent-break gate. A generic HTTP
  monitor asserts reachability — the exact R44 anti-pattern this ticket exists to replace.
serial_justified: one coherent canary (runner + its assertions + the e2e-dogfood harness that proves it catches a seeded fault) is a single vertical slice; splitting ships a runner with no assertions or assertions with no proof.
build_status: |
  Thin slice BUILT 2026-07-23 (feat/flow-canary). fleet/flow-canary.sh asserts all four
  observable-effect stages against the LIVE 4-LOM gateway (v0.6.0); verified GREEN live
  (served-by openrouter fc1 free-first, meter cost-delta 2.78e-05, huggingface parked-and-
  excluded). fleet/tests/flow-canary.test.sh is the fail-on-revert dogfood: 18 assertions,
  hermetic fake gateway, every fault class (mis-route / free-first / inert-meter #167 /
  parked-served + parked-attempted #188 / stray-standard / unserved-model) proven RED then
  GREEN on revert. Wired into CI_SUITES. Widen-to-matrix (economy+frontier, per-provider
  legs) + scheduled cadence are follow-ons. Awaiting adversarial review + land (reviewer≠builder).
work_class_note: |
  Operator-approved 2026-07-23. The PROACTIVE umbrella over the whole silent-break class. Every issue this
  session was found by LUCK: stray `standard` tier, silent loop-guard quarantine, dead-no-op cooldown (#188),
  V4-Pro mis-route, funding_class-inert, 0-grades, unclaimable P0. A scheduled canary that runs the REAL
  flow per tier/provider/model and asserts OBSERVABLE EFFECTS turns "found by luck" into "caught every run".
  IS R44 dogfood-gate extended across the tier×provider×model matrix; feeds the reconciliation-gate;
  consumes CLAIM-LADDER-HEALTH. [[gates-must-actually-run]] [[monitored-preflight-failure-attribution]]
  [[charon-strategy-outcome-graded-gateway]] [[latency-is-a-failure-class]] [[no-rig-as-product-adopt-dont-handroll]]
accept: |
  Build a THIN VERTICAL SLICE first (one tier chain end-to-end), designed to widen to the full
  tier×provider×model matrix. `fleet/flow-canary.sh` sends a REAL canary request through the LIVE gateway
  (4-LOM) for the tier's chain and ASSERTS OBSERVABLE EFFECTS at each stage — the R44 crux is "prove
  EXERCISED, not merely reachable":
    1. **Route:** the request reaches the EXPECTED provider/model for that tier (assert `X-Charon-Provider`
       + resolved model), free-first ordering respected (a funded free leg is hit before paid).
    2. **Meter:** the per-request spend actually advances the ledger by the priced amount (assert the
       BalanceTracker/meter DELTA — not just that a call happened).
    3. **Funding-class / park:** a drained/parked provider is actually excluded (assert the exclusion fires,
       the #188-class check — a config that's a no-op in prod must go RED here).
    4. **Config sanity:** the tier is canonical (economy/strong/frontier), the model is served, the provider
       has a key — surface drift (the stray-`standard` class).
  **E2E DOGFOOD (mandatory, GREEN-IS-NOT-PROOF):** SEED a fault (e.g. break a funding_class, point a model at
  a dead provider, inject a mis-route) and PROVE the canary goes RED on it, then GREEN when fixed. A canary
  that only passes the happy path is worthless — it must demonstrably catch a real seeded break.
  **CADENCE:** wire it to run on a schedule (session-start + a timer) and surface RED loudly.
  **ADVERSARIAL REVIEW REQUIRED before merge** (reviewer≠builder) — money-path + it's the proactive guard,
  so a canary that fakes-green is worse than none.
  COMPLETION SELF-CHECK: if the canary can't demonstrably catch a seeded fault, or asserts reachability
  instead of an observable effect, it is INCOMPLETE.
scope: |
  A scheduled flow-canary that runs the real gateway flow per tier/provider/model and asserts observable
  effects (route reached, meter delta, park/funding-class fires, config canonical) — RED on any silent
  break. Thin slice first (one tier), widen to the matrix. Extends R44 dogfood-gate; e2e-dogfood-proven.
ds: |
  ## Dependencies & sequence
  - depends_on: none for the slice. Reuses the live gateway + meter + funding_class (all live now) + the
    canonical tier set (`charon tier ranks`). Widen-to-matrix + the fleet-claim-flow leg (CLAIM-LADDER-HEALTH
    covers claim-side) are follow-ons.
  - MONEY-PATH + proactive-guard: adversarial review by default; never fake-green.
