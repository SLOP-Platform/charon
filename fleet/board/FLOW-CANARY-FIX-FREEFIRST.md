repo: charon-private
tier: strong
difficulty: 2
work_class: bugfix
priority: 0
branch: fix/flow-canary-freefirst
depends_on:
serial_justified: the canary fix and its dogfood rewrite are one unit — FIX-1 changes the assertion, FIX-2 changes the test that must prove it; splitting ships a fixed canary with a fake-green test or vice versa.
owns: fleet/flow-canary.sh, fleet/tests/flow-canary.test.sh
work_class_note: |
  Fix-forward from the RETROACTIVE adversarial review of FLOW-CANARY (which reached master unreviewed via
  the --commit-dirty sweep, [[commit-dirty-sweeps-subagent-wip]]). The canary's free-first stage encodes a
  policy the gateway does NOT implement → it would CRY-WOLF on normal operation. A proactive guard that
  false-REDs is worse than none. [[always-fix-catalog-mismatches]] [[gates-must-actually-run]]
accept: |
  Fix the flow-canary's free-first stage + its dogfood (verified by the retroactive review, verdict on file):
  - **FIX-1 (headline):** the free-first check hardcodes `fc∈{1,2}=free` — WRONG. Adopt the live SSOT
    `funding_class_order` / `order_chain_by_funding_class` (`_FUNDING_CLASS_ORDER = {1:0, 3:1, 2:2, 4:3}` →
    order 1<3<2<4; class-3 drain-then-park ranks SECOND, sanctioned). Assert the served leg is the
    highest-priority NON-parked/keyed leg in the pool per that order — NOT `fc∈{1,2}`. Do NOT reimplement
    the order; read the SSOT (reimplementation is what caused this).
  - **FIX-2:** rewrite the (R2) dogfood — it currently "proves" the canary catches a class-3-serving NON-fault
    by mirroring the canary's wrong model (fake-green). Seed a REAL violation instead (a lower-priority leg
    serving while a higher-priority non-parked leg was skipped, e.g. class-4 PAYG over an available class-1).
  - **FIX-3 (minor):** meter cost-delta `>=0` is near-un-failable (decorative) → assert `>0` for a draining
    leg, or drop it.
  - **FIX-4 (minor):** live park positive-GREEN must confirm the excluded provider was actually a CANDIDATE
    in the head-model pool, else the "EXCLUDED" claim is vacuous.
  PROVE IT: the free-first dogfood now goes RED on a REAL priority-order violation and GREEN when a class-3
  leg legitimately serves (no more cry-wolf). Fail-on-revert.
scope: |
  Fix the flow-canary free-first stage to adopt the funding_class_order SSOT (stop the class-3 cry-wolf) +
  rewrite the fake-green R2 dogfood to seed a real violation; tighten the decorative meter/park assertions.
ds: |
  ## Dependencies & sequence
  - depends_on: none. owns fleet/flow-canary.sh + its test (FLOW-CANARY retired/archived — no live co-owner).
