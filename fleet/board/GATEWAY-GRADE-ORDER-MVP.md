repo: charon
tier: strong
difficulty: 5
work_class: routing
branch: feat/gateway-grade-order-mvp
parked: false
depends_on: GATEWAY-LITELLM-ADOPT
real-dep: GATEWAY-LITELLM-ADOPT the overlay hooks into litellm.Router's routing decision, which does not exist until the adopt lands; building it against the deleted hand-rolled forwarder is throwaway
seq_reason: sequenced behind GATEWAY-LITELLM-ADOPT (hard build prereq, see real-dep); claimable once the adopt lands. LIVE (un-parked 2026-07-21).
note: |
  LIVE 2026-07-21 — operator-APPROVED (2026-07-21), UN-PARKED. Sequenced behind GATEWAY-LITELLM-ADOPT
  (its build prereq). This is the SECOND (and genuinely NOVEL) leg of the gateway MVP: the outcome-grade
  overlay + a NEUTRAL product-side grade store/format, wired into litellm.Router's routing decision.
  Adopt the commodity plane FIRST (GATEWAY-LITELLM-ADOPT), build ONLY this novel ~30% here. Basis:
  scratchpad/GATEWAY-MVP-ADOPT-VS-BUILD.md + docs/adr/0017-outcome-graded-gateway.md + §0. Supersedes /
  reframes the parked PRODUCT-GRADES-STORE + WIRE-BRAIN-INTO-GATEWAY drafts (which assumed a hand-rolled
  forwarder attach point); this ticket attaches to the ADOPTED litellm.Router instead.
owns: src/charon/capability/product_grades.py, src/charon/routing_policy/grade_order.py, tests/test_product_grades.py, tests/test_grade_order.py
serial_justified: |
  The owned files are ONE novel seam: product_grades.py is the NEUTRAL product-side grade store/format
  (the differentiator's data), grade_order.py is the ordering overlay that reads it and reorders the
  litellm.Router candidate set at the routing decision. Splitting them recreates the build-against-a-
  changing-API defect (overlay built before the store it queries). The two test files are the
  fail-on-revert proofs for that one seam.
accept: |
  WHAT THIS BUILDS (the genuine novel slice — the whole differentiator): (a) a NEUTRAL PRODUCT-side
  grade store/format — its OWN product format, NOT the fleet `model-scorecard.tsv` (no rig->product
  leak [[product-vs-build-rig-boundary]]) — and (b) a grade-ordering overlay wired into litellm.Router's
  routing decision, keyed by the EXISTING deterministic taxonomy classifier
  (src/charon/capability/taxonomy.py `classify_request`), FAIL-OPEN to today's order when no grades file
  exists.

  GROUND TRUTH (confirmed against the live product tree — do NOT reinvent):
    - `CapabilityMatrix.get_grade` (routing_policy/matrix.py) is currently called NOWHERE; the matrix is
      built EMPTY at gateway.py:484 — the grade path is inert today. This ticket is what makes it live.
    - Pre-adopt, the forwarder reorder/attach points were forwarder.py:388 (order-by-cooldown) and
      forwarder.py:556 (routing decision). AFTER GATEWAY-LITELLM-ADOPT those move to the litellm.Router
      routing callback — wire the overlay THERE, not into the deleted forwarder (this is the D&S reason
      it sequences after the adopt).
    - The grade store is a NEUTRAL product format authored HERE. It PORTS the fleet grade CONTRACT
      (refuse-on-empty, keyed per (model, work_class)) but imports NO fleet code and reads NO
      model-scorecard.tsv — a fresh install seeds it via its own importer, not the rig ledger.

  ACCEPTANCE TESTS (observable, fail-on-revert — BOTH are the minimum bar):
    (1) FAIL-ON-REVERT / GRADE ORDERS: with a fixture grade store where a grade-A model that is the
        2nd-CHEAPEST out-ranks a grade-F CHEAPEST model, a request whose litellm.Router candidate set is
        {cheapest-F, 2nd-cheapest-A}, classified by taxonomy into its work-KIND, is ordered A-FIRST
        (grade beats raw price). Prove by asserting the ORDER the Router attempts, not that a function
        was called. Revert the overlay -> order reverts to cheapest-first (F-first) -> RED.
    (2) BYTE-IDENTICAL COLD START: with NO grades file present, the SAME request keeps the EXACT
        litellm.Router ordering it would have with no overlay at all (assert byte-identical to the
        no-overlay path). FAIL-OPEN: a missing/empty/unparseable grades file -> overlay is a no-op, the
        Router's own order stands, request still forwards. Revert the fail-open (make missing-file
        throw/strand) -> RED.

  KEYING: work-KIND comes from the EXISTING deterministic classifier taxonomy.py `classify_request`
  (stdlib, hot-path-safe) — NOT a new predict-time difficulty router. "unknown" -> safe default
  work_class, never block. The overlay may ONLY reorder ids already in the Router's candidate set; it
  may never introduce an unlisted model id.

  GREEN-IS-NOT-PROOF: a test that stubs the store and asserts "grade_order was called" proves nothing.
  Test (1)'s attempt-ORDER and test (2)'s byte-identical cold-start are the bar. Reviewer: confirm the
  grade load is CACHED (no per-request file parse on the hot path) and that no test asserts against a
  pre-mocked ordering.
scope: |
  Build the NOVEL outcome-grade slice: a neutral product-side grade store/format (NOT the rig
  model-scorecard.tsv) + a grade-ordering overlay wired into litellm.Router's routing decision, keyed by
  the existing taxonomy work-KIND classifier, FAIL-OPEN to the Router's own cheapest-capable order when
  no grades file exists. This is the differentiator ADR-0017 names and that is inert today
  (CapabilityMatrix.get_grade called nowhere; matrix built empty at gateway.py:484). Depends on the
  commodity-plane adopt so it wires into litellm.Router, not the deleted forwarder. Hot path —
  adversarial review by default + never-strand invariant required.
  [[charon-strategy-outcome-graded-gateway]] [[adopt-substrate-build-only-novel-slice]]
  [[product-vs-build-rig-boundary]] [[scorecard-live-lane-is-the-ledger]]
  [[benchmark-not-a-valid-ranker]] [[confirm-dont-trust-documentation]]
  [[charon-north-star-engine-mechanism]] [[standing-blast-radius-lens]] [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence

  depends_on: GATEWAY-LITELLM-ADOPT — HARD BUILD PREREQ (real-dep, see marker). The overlay hooks into
    litellm.Router's routing callback; that Router does not exist until the adopt lands, and the
    pre-adopt forwarder attach points (forwarder.py:388/:556) are DELETED by the adopt. BLOCKED until
    GATEWAY-LITELLM-ADOPT is done; claimable the moment it lands (same dep-gated pattern as
    GH-SEAM-CHOKEPOINT). This is why the dep is a genuine build/correctness prereq, not merge-order.

  SEQUENCE RATIONALE (adopt-first, per §0): adopt the commodity plane FIRST, then build ONLY this novel
    ~30% on top of it. Wiring the overlay before the adopt would attach it to the hand-rolled forwarder
    that the adopt then deletes — pure throwaway.

  NEUTRAL-FORMAT BOUNDARY (load-bearing): the grade store is a PRODUCT-OWNED neutral format authored in
    product_grades.py. It does NOT read the fleet `model-scorecard.tsv` and imports NO fleet code
    [[product-vs-build-rig-boundary]] — a rig->product leak is forbidden. It PORTS the grade CONTRACT
    (refuse-on-empty, per-(model,work_class) key) only. A standalone install seeds it via its own
    importer; live gateway traffic does NOT self-grade (a health/latency/cost response is not an outcome).

  reads-only (no owns claim): src/charon/capability/taxonomy.py (classify_request — wired, not edited),
    src/charon/routing_policy/matrix.py (WorkClass/Grade vocabulary — reuse the types), the
    litellm.Router routing callback surface from GATEWAY-LITELLM-ADOPT (hooked, not owned).

  supersedes (coordination, not owns-collision — all parked): PRODUCT-GRADES-STORE + WIRE-BRAIN-INTO-
    GATEWAY are the 2026-07-19 drafts that assumed a hand-rolled forwarder attach point. This ticket is
    the operator-approved 2026-07-21 reframe onto the ADOPTED litellm.Router. Distinct owned filenames
    (product_grades.py / grade_order.py vs their grades.py / brain_router.py) so no collision even if a
    stale draft is later un-parked; the operator should retire the superseded drafts when un-parking this.

  BLAST RADIUS: grade_order.py sits ON the request hot path (the litellm.Router routing decision) —
    REORDER-ONLY + fail-open + cached-load + never-introduce-unlisted-id. REQUIRES adversarial review by
    default [[adversarial-review-default-for-droid-prs]] + the never-strand invariant (accept #2's
    fail-open). A regression degrades every graded request. product_grades.py is a new module
    (single-writer), lower live blast until grade_order consumes it.

  wave: DRAFT — un-park after GATEWAY-LITELLM-ADOPT lands. repo: charon (product). SECOND (novel slice)
    in the gateway-MVP sequence.
