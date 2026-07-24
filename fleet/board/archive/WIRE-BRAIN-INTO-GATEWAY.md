repo: charon
tier: strong
difficulty: 4
work_class: coding
branch: feat/wire-brain-into-gateway
parked: true
note: |
  SUPERSEDED 2026-07-21 (operator-approved) by GATEWAY-GRADE-ORDER-MVP, which wires the outcome-grade
  overlay into the ADOPTED litellm.Router routing decision instead of the hand-rolled forwarder /
  brain_router this draft assumed. Stays parked; do not build. Retained for reference only.
  DRAFT — operator review only. `parked: true` so no droid auto-claims it. This is ADR-0017's
  ratified MVP ("wire the fleet's outcome-graded brain into the gateway request router, with a
  cold-start fallback"), scoped honestly against the live code. UN-PARK only after the operator
  (a) confirms the decomposition below (this ticket has a REAL build prerequisite — see depends_on)
  and (b) confirms the crux resolution (single-default work_class + wire the EXISTING taxonomy
  classifier; no new predict-time classifier). Created 2026-07-19 by a read-only scoping session.
depends_on: PRODUCT-GRADES-STORE
real-dep: |
  PRODUCT-GRADES-STORE (sibling ticket, now on the board as a parked DRAFT at
  fleet/board/PRODUCT-GRADES-STORE.md — un-park after operator review; full spec there, stubbed in
  ds: below). THIS IS THE LOAD-BEARING FINDING. ADR-0017 calls the MVP a "bounded
  connection task," but there is NOTHING PRODUCT-SIDE TO CONNECT TO yet:
    - The real brain (grades.py + assign.py + model-scorecard.tsv, ~770 LOC: Wilson bounds,
      control-panel split, source allow-list, stage gate, taxonomy fold) lives in the FLEET repo
      (charon-private/fleet/capability/). The product gateway ships STANDALONE and MUST NOT import
      fleet code [[product-vs-build-rig-boundary]] — so "wire the fleet's brain in" is impossible as
      literally worded; it requires a product-side GradesProvider + outcome ledger.
    - The product side has NO outcome store. src/charon/capability/ holds only taxonomy.py
      (classifier) + scorecard.py (freeze-ring, the WRONG store). capability/__init__.py's docstring
      references an "actuals ledger" that DOES NOT EXIST as a file (dead ref — see
      CAPABILITY-ACTUALS-DEADREF-CLEANUP). routing_policy/matrix.py has a (model×work_class)->grade
      SHAPE but its own docstring says the engine that populates it from live observations "lands in
      subsequent waves" — it is inert re: outcomes.
  So the honest scope is TWO tickets: PRODUCT-GRADES-STORE (BUILD — establish the product-side
  outcome ledger + a GradesProvider port with the same refuse-on-empty contract) THEN this ticket
  (WIRE — small, the actual bounded connection). Do NOT build this ticket against a store that does
  not exist. See ds: for the full decomposition + prerequisite spec.
owns: src/charon/routing_policy/brain_router.py, src/charon/forwarder.py, tests/test_brain_router.py, tests/test_forwarder_brain_wiring.py
serial_justified: |
  The two owned source files are ONE seam, not two builds: brain_router.py is the reorder-only
  policy bridge, forwarder.py is the single call site that invokes it at the routing decision point.
  Splitting them recreates a build-against-a-half-wired-hook defect. The two test files are the
  fail-on-revert proofs for that one seam. This ticket does NOT own the grades store/provider — that
  is PRODUCT-GRADES-STORE's leg (consumed here, never edited).
accept: |
  CRUX RESOLUTION (baked into scope; the single most important design decision):
    An incoming OpenAI request carries NO work_class. Resolve it as follows (smallest honest option):
      - work_class comes from the EXISTING, already-built deterministic classifier
        src/charon/capability/taxonomy.py `WorkClassTaxonomy.classify_request(text)` — stdlib,
        regex/keyword, hot-path-safe, returns a known WorkClass or "unknown". This is NOT the
        forbidden predict-time DIFFICULTY router (that predicts hardness->tier; this predicts
        KIND->work_class, aligned VERBATIM with matrix.py `WorkClass` and the fleet brain's
        CANONICAL_WORK_CLASSES). Wiring an existing classifier is in-scope; building a new one is NOT.
      - "unknown" -> route via the safe default work_class (config; default "general"); do NOT block.
      - DEFERRED (say so explicitly): no LLM/semantic classifier, no per-work_class request tagging
        beyond the deterministic classifier + an optional X-Charon-Work-Class header override.
    TRIGGER (bounds the blast radius): the brain ENGAGES ONLY when the requested `model` is an
    abstract/capability id (a configured "auto"/pool id whose legs are DISTINCT models). For a
    CONCRETE model request the client already chose the model — brain is a NO-OP, byte-identical to
    today. (Confirmed: forwarder resolves `requested = body["model"]` -> srv.chain_for(requested);
    the brain only has a MODEL choice to make when that chain spans different models.)

  WIRING (policy-unchanged principle — REORDER ONLY, never add/drop):
    In brain_router.py, given the chain's candidate model ids + the resolved work_class, consult the
    product-side GradesProvider (from PRODUCT-GRADES-STORE) exactly as fleet assign() does with
    `--candidates` + `--print-model`: return the graded-cheapest ordering, or None (refuse) when the
    provider has no gradeable data. In forwarder.forward_with_failover, insert ONE guarded call at
    the routing decision point (~L547, after order_by_cooldown, alongside the quality-scorer pass):
    if the trigger fires AND the bridge returns an ordering, use it; on None/any error, leave the
    existing ordering untouched (fail-open — mirror the "all excluded -> fall back, warn" pattern
    already used 4x in this function). The brain may only reorder ids ALREADY in the configured
    chain; it may never introduce an unlisted model id (mirror assign.py's --candidates guard).

  COLD-START (concrete):
    Empty ledger -> provider.grade(model,wc) returns None for every candidate -> bridge returns None
    -> forwarder keeps its existing static cheapest-capable ordering, unchanged. Transition is
    PER-(model,work_class) and AUTOMATIC: the provider (per PRODUCT-GRADES-STORE) admits a grade only
    once real outcomes accrue for that key (source=live + stage=active + control-panel split;
    MIN_N=4). The gateway MUST NOT reinvent N or the thresholds — it defers entirely to the
    provider's refuse. Each work_class flips to graded routing independently as its key fills.

  ACCEPTANCE TESTS (observable, fail-on-revert — ALL must go RED when the wiring is reverted):
    (1) SEEDED-LEDGER ROUTES BY GRADE: with a fixture provider seeded so model B out-grades model A
        at work_class "coding", a request to the auto/pool id whose legs are {A,B}, classified
        "coding", is tried B-first. Prove by asserting the ORDER the forwarder attempts, not that a
        function was called. Revert the wiring -> order reverts to static -> RED.
    (2) EMPTY-LEDGER FALLS BACK: with an empty fixture provider, the SAME request keeps the exact
        static cheapest-capable ordering (assert byte-identical to the no-brain path). Revert the
        fallback (make refuse throw/strand) -> RED.
    (3) NEVER-STRAND / FAIL-OPEN: brain_router raising an exception leaves the chain intact and the
        request still forwards (assert non-empty ordering + 2xx path). Revert the try/except ->
        exception escapes -> RED.
    (4) CONCRETE-MODEL NO-OP: a request to a concrete model id is byte-identical to today (brain
        never engages). Revert the trigger guard -> brain reorders a concrete request -> RED.
    (5) NO NEW MODEL INTRODUCED: assert the reordered set == the input candidate set (no id the
        configured chain didn't already contain). Revert the guard -> RED.

  GREEN-IS-NOT-PROOF: a test that stubs the provider and asserts "brain_router was called" proves
  nothing. Test (1)'s attempt-ORDER and test (2)'s byte-identical-fallback are the minimum bar.
  Reviewer: confirm the grades load is CACHED (not a per-request TSV/JSON parse on the hot path) and
  that no test asserts against a pre-mocked ordering.

  LIVE-OUTCOME-SIGNAL FINDING (must be honored in scope, not silently dropped): the gateway CANNOT
  grade its own traffic. grades admit ONLY source=live rows = real routed-ticket MERGE/BLOCK verdicts
  with a per-ref control-panel split; a live API response yields only HTTP-status/latency/cost/tokens
  (exactly what quality.json already records). So this ticket wires a READ-ONLY consumer: the gateway
  reads grades produced OUT-OF-BAND (fleet dogfood / imported scorecard); it writes nothing back to
  the grades ledger. quality.json stays the health/failover signal, orthogonal. Do NOT add a
  gateway->grades write path here (it would be a fabricated outcome — the ledger's fail-closed
  allow-list exists to prevent exactly that).
scope: |
  Wire a product-side outcome-grades brain into the gateway request router as a REORDER-ONLY policy,
  keyed on a work_class resolved by the existing deterministic taxonomy classifier, engaged only for
  abstract/auto model ids, with a fail-open static-ordering fallback on an empty/insufficient ledger.
  Read-only consumer of grades produced out-of-band; no gateway->ledger write path. Compose the
  existing seams (taxonomy.classify_request, the forwarder reorder chain, the assign() --candidates
  refuse-contract); build only the thin bridge. Hot path — adversarial review + never-strand invariant
  required.
  [[confirm-dont-trust-documentation]] [[product-vs-build-rig-boundary]] [[no-stiff-single-provider-tools]]
  [[gates-must-actually-run]] [[standing-blast-radius-lens]] [[charon-north-star-engine-mechanism]]
ds: |
  ## Dependencies & sequence

  DECOMPOSITION (recommended: TWO tickets — this is NOT one bounded task as ADR-0017 frames it):
    - PRODUCT-GRADES-STORE (BUILD, prerequisite, difficulty 5, now a parked DRAFT on the board —
        un-park after operator review):
        owns NEW files under src/charon/capability/ (e.g. actuals.py + grades.py) + tests.
        Establish the product-side outcome ledger (resolve the dead "actuals ledger" ref in
        capability/__init__.py; see CAPABILITY-ACTUALS-DEADREF-CLEANUP) and a GradesProvider that
        reads it and returns a per-(model,work_class) grade or None, with the SAME fail-closed
        refuse-on-empty + source-allow-list + control-split contract the fleet grades.py uses
        (PORT the logic — do NOT import fleet code; product ships standalone). Also: an importer so a
        user/fleet can seed the ledger (the ONLY way a standalone install's ledger ever fills — see
        the live-outcome finding). This is the real ~30% build; the "connection" is trivial without
        it.
    - WIRE-BRAIN-INTO-GATEWAY (THIS ticket, WIRE): the bounded connection — small once the store
      exists. Depends_on PRODUCT-GRADES-STORE.
    Rationale: the store is a from-scratch module build (single-writer on new files, different skill
    + size than the forwarder edit); folding it into the wire ticket hides a real sub-problem and
    forces the wire to build against a changing API. Splitting the wire itself (bridge vs forwarder
    call site) is NOT justified — see serial_justified.

  depends_on: PRODUCT-GRADES-STORE — hard prereq (the provider this ticket consumes). BLOCKED until it
    lands. This ticket is claimable the moment it does (same dep-gated pattern as GH-SEAM-CHOKEPOINT).

  ADOPT-SUBSTRATE-01 / LiteLLM: NOT a hard dep, but a real coupling to flag. ADR-0017 marks LiteLLM
    ADOPT behind a flag (default stdlib). This ticket edits the stdlib forwarder path. If LiteLLM
    later replaces forwarder wholesale, deep forwarder wiring is throwaway. MITIGATION: keep
    brain_router.py substrate-NEUTRAL (a pure `(candidate_ids, work_class) -> ordering|None` policy
    function); the forwarder call is the only substrate-specific line, and the same policy re-hooks
    into a LiteLLM custom-router callback. Build the policy to survive the substrate swap.

  reads-only (no owns claim): src/charon/capability/taxonomy.py (classify_request — wired, not
    edited), src/charon/routing_policy/matrix.py (WorkClass vocabulary), src/charon/quality_scorer.py
    (orthogonal health signal, untouched), the PRODUCT-GRADES-STORE GradesProvider (consumed).

  BLAST RADIUS: forwarder.forward_with_failover is THE request hot path (money path) — every gateway
    request flows through it. REORDER-ONLY + fail-open + trigger-guarded + latency-bounded (cached
    load). REQUIRES adversarial review by default [[adversarial-review-default-for-droid-prs]] and
    the never-strand invariant test (accept #3). A regression here degrades every request.

  wave: DRAFT — un-park after operator confirms decomposition + crux. repo: charon (product).

verdict-note: |
  HONEST VERDICT on ADR-0017's "bounded connection task": HALF TRUE. The forwarder connection IS
  bounded and small. But it is bounded only AFTER a real prerequisite build that ADR-0017 does not
  name: a product-side grades store + GradesProvider, because the actual brain lives in the fleet
  repo the product cannot import and the product-side outcome store does not exist. The crux
  (request -> work_class) is genuinely cheap (an existing deterministic classifier, not the forbidden
  predict-time router). The reshaper is the live-outcome finding: the gateway cannot grade its own
  traffic, so "outcome-graded gateway" means "gateway that CONSUMES outcomes graded in the fleet path
  / imported" — a standalone install's ledger never fills from its own requests. That is not a
  blocker, but it must be said plainly or the fresh-install differentiator is inert exactly where the
  north-star user meets it.

PRUNED 2026-07-24 (operator-approved, review-grounded): superseded by GATEWAY-GRADE-ORDER-MVP which hooks the overlay into the adopted litellm.Router, not the hand-rolled brain_router/forwarder this draft assumed.
