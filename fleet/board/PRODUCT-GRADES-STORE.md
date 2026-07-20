repo: charon
tier: strong
difficulty: 5
work_class: coding
branch: feat/product-grades-store
parked: true
note: |
  DRAFT — operator review only. `parked: true` so no droid auto-claims it. This is the BUILD
  PREREQUISITE that ADR-0017's MVP ("wire the outcome-graded brain into the gateway") silently
  assumed already existed but does NOT: the product gateway has NO outcome store and MUST NOT import
  the fleet's brain [[product-vs-build-rig-boundary]]. Sibling of WIRE-BRAIN-INTO-GATEWAY (that ticket
  depends_on THIS). UN-PARK only after the operator (a) confirms the two-ticket decomposition and
  (b) confirms the product file paths below (flagged as needing confirmation — see path-uncertainty).
  Created 2026-07-19 by a read-only scoping session; grounded against the live product tree.
depends_on:
owns: src/charon/capability/outcomes.py, src/charon/capability/grades.py, src/charon/routing_policy/grades_provider.py, src/charon/capability/grades_import.py, tests/test_outcomes_ledger.py, tests/test_grades.py, tests/test_grades_provider.py, tests/test_grades_import.py
path-uncertainty: |
  The exact filenames below are the SCOPING SESSION'S PROPOSAL, not confirmed operator layout — the
  builder must confirm before creating files (validator owns-check is WARN-only for non-existent paths,
  so a wrong guess would not fail RED — flagged here instead of guessed silently
  [[confirm-dont-trust-documentation]]):
    - `src/charon/capability/outcomes.py` — the outcome ledger. UNCERTAIN NAME: the old
      `capability/actuals.py` (ActualsLedger/ActualRow) was DELETED by PR #160 (DEDUP-ACTUALS-DELETE,
      confirmed absent from master), and `capability/__init__.py`'s module docstring STILL promises an
      "actuals ledger" that no longer exists (a dead ref beyond the three CAPABILITY-ACTUALS-DEADREF-
      CLEANUP tracks). Operator to decide: REVIVE the `actuals.py` name (and heal the __init__ docstring)
      OR use a fresh name like `outcomes.py`. This ticket assumes a fresh name to avoid resurrecting a
      deliberately-deleted module; flag for the operator.
    - `src/charon/routing_policy/grades_provider.py` — the routing-facing GradesProvider PORT. Placed in
      routing_policy/ beside its ONLY consumer (WIRE's brain_router.py, which READS it, never owns it);
      WIRE's ds sketched the provider under capability/. Either is defensible; operator to confirm the
      seam location. No owns-collision with WIRE either way (distinct filenames).
    - `src/charon/capability/grades.py` — grade-computation port (matches WIRE ds's named path).
    - `src/charon/capability/grades_import.py` — seed/import path.
serial_justified: |
  The owned files are ONE new module — a single-writer, from-scratch build — NOT independent legs:
  outcomes.py (the append-only real-outcome ledger), grades.py (the grade-computation contract over it:
  refuse-on-empty + source allow-list + control-split + MIN_N gate), grades_provider.py (the thin
  routing-facing port that answers `(candidate_ids, work_class) -> ordering | None`), and grades_import.py
  (the seed/import path). Splitting them per-file recreates the classic build-against-a-changing-API
  defect (the provider built before the ledger it queries) and violates touch-a-file-ONCE
  [[optimize-execution-wallclock-tokens]]. The four test files are the fail-on-revert proofs for that one
  module. Different skill + size than WIRE's forwarder edit, which is why it is a SEPARATE ticket, not a
  leg of WIRE.
accept: |
  WHAT THIS BUILDS (the load-bearing prerequisite ADR-0017 omitted): a PRODUCT-SIDE outcome ledger + a
  GradesProvider that answers `(candidate_model_ids, work_class) -> ordering | None` from REAL graded
  outcomes, with NO fleet import, plus a seed/import path so a fresh install is not inert on day one.

  GROUND TRUTH (confirmed against the live product tree — do NOT re-research, do NOT reinvent):
    - The REAL brain (grades.py + assign.py + model-scorecard.tsv, Wilson bounds, control-panel split,
      source allow-list, stage gate, taxonomy fold) lives in the FLEET repo (charon-private/fleet/
      capability/). The product gateway ships STANDALONE and MUST NOT import fleet code
      [[product-vs-build-rig-boundary]] — so PORT the CONTRACT, copy no fleet module.
    - The product side has NO outcome store today. `src/charon/capability/` holds only taxonomy.py
      (the deterministic classifier WIRE reuses) and scorecard.py — and scorecard.py is the WRONG store
      (a freeze-ring/last-known-good ONBOARDING artifact reader; ScorecardStore/ScorecardArtifact, gate_
      pass/LKG semantics; not a real-verdict outcome ledger). Do NOT overload it.
    - `capability/__init__.py`'s docstring references an "actuals ledger" whose module was DELETED
      (PR #160). `routing_policy/matrix.py` defines a `(model_id, work_class) -> Grade` SHAPE
      (CapabilityMatrix.get_grade/set_grade, in-memory only) whose own docstring says "the engine that
      populates and queries it from live observations lands in subsequent waves" — i.e. it is an inert
      schema with NO persistence, NO source allow-list, NO MIN_N. This ticket builds THAT engine's store.
      The provider MAY answer using matrix.py's WorkClass/Grade vocabulary, but persistence + gating are new.

  BUILD (compose the existing vocabulary; add only the store + gate + port):
    (a) OUTCOME LEDGER (outcomes.py): an append-only store of REAL outcome verdicts keyed per
        (model_id, work_class). Each admitted row is a genuine routed-work outcome (MERGE/BLOCK-class
        verdict) carrying source, stage, and control-panel-split fields — MIRROR the fleet grades.py
        contract, do NOT reinvent the thresholds. Admission is FAIL-CLOSED: only source=live +
        stage=active rows are admitted; everything else is refused. A gateway HTTP response
        (status/latency/cost/tokens — the shape quality.json already records) is a HEALTH signal, NOT an
        outcome, and MUST be refused (fabricated-outcome guard — this allow-list is the whole point).
    (b) GRADES (grades.py): compute a per-(model, work_class) grade/ranking from the ledger using the
        SAME refuse-on-empty + source allow-list + control-split + MIN_N (=4, defer to the fleet
        contract's value; do NOT invent a new N) gate. Below MIN_N for a key -> return None for that key.
    (c) PROVIDER PORT (grades_provider.py): `order(candidate_model_ids, work_class) -> ordering | None`.
        Returns the graded ordering ONLY over ids ALREADY in the candidate set (never introduces an
        unlisted id — mirror assign.py's --candidates guard), or None when no key in the set is gradeable.
        The load MUST be CACHED (no per-call ledger re-parse — WIRE consumes this on the request hot path).
    (d) SEED / IMPORT (grades_import.py): import a curated/benchmark scorecard into the ledger so routing
        has data ON INSTALL (the ONLY way a standalone install's ledger ever fills — see the live-outcome
        finding). Live GATEWAY traffic does NOT populate the ledger; real grades come from graded work
        runs (fleet dogfood) or this import. State that plainly.

  ACCEPTANCE TESTS (observable, fail-on-revert — ALL must go RED when the store is reverted):
    (1) EMPTY-LEDGER REFUSES: a fresh GradesProvider over an empty ledger returns None from
        `order(candidates, wc)` and grades(model, wc) == None for every candidate. Revert the refuse
        (make it return a default ordering) -> RED. This is the contract WIRE's cold-start depends on.
    (2) GRADES ONLY AFTER MIN_N REAL OUTCOMES: seed >= MIN_N (=4) source=live/stage=active outcome rows
        for (B,"coding") that out-rank A; assert `order({A,B},"coding")` returns B-first. With < MIN_N
        rows for the key, assert it STILL returns None (per-key gate). Revert the MIN_N gate or the
        ranking -> RED.
    (3) IMPORT SEEDS A QUERYABLE LEDGER: run grades_import on a curated/benchmark scorecard FIXTURE ->
        assert the ledger is then queryable and the provider returns a graded ordering with NO live
        traffic (proves day-one-not-inert). Revert the importer -> provider returns None -> RED.
    (4) SOURCE ALLOW-LIST / NO SELF-GRADING: attempt to admit a HEALTH-only row (HTTP status/latency/
        cost/tokens, source != live) -> assert it is REFUSED and changes NO grade (fabricated-outcome
        guard). Revert the allow-list -> the health row leaks a grade -> RED.
    (5) NO FLEET IMPORT (boundary): a static import-scan asserts none of the owned modules import from the
        fleet package (product ships standalone) — mirrors scorecard.py's own "must NOT import the rig
        grader" invariant. Revert to `import fleet...`/`from fleet...` -> RED.

  GREEN-IS-NOT-PROOF: a test that stubs the ledger and asserts "the provider was called" proves nothing.
  Test (2)'s attempt-ORDER after real seeded outcomes and test (1)'s empty-refuse are the minimum bar.
  Reviewer: confirm the provider load is CACHED (not a per-call parse) and that no test asserts against a
  pre-mocked ordering.
scope: |
  Build the PRODUCT-SIDE outcome ledger + a GradesProvider port that answers
  `(candidate_ids, work_class) -> ordering | None` from real graded outcomes, plus a seed/import path so a
  fresh install is not inert — PORTING the fleet grades contract (refuse-on-empty + source allow-list +
  control-split + MIN_N) WITHOUT importing fleet code [[product-vs-build-rig-boundary]]. Do NOT overload
  scorecard.py (wrong store) or matrix.py's inert in-memory shape; this is the persistence + gate engine
  those shapes were waiting on. Product code but NOT the request hot path (WIRE is the hot path); this is
  the store WIRE reads. Single-writer over a new module; the differentiator is invisible on day one
  unless the import path lands, so it is in-scope here, not deferred.
  [[confirm-dont-trust-documentation]] [[product-vs-build-rig-boundary]] [[charon-north-star-engine-mechanism]]
  [[scorecard-live-lane-is-the-ledger]] [[benchmark-not-a-valid-ranker]] [[standing-blast-radius-lens]]
ds: |
  ## Dependencies & sequence

  depends_on: NONE. This is the PREREQUISITE — the from-scratch product-side store that WIRE-BRAIN-INTO-
    GATEWAY consumes. It is claimable the moment the operator un-parks it (no upstream build gate).

  WIRE-BRAIN-INTO-GATEWAY depends_on THIS ticket (hard prereq). WIRE is the small bounded connection —
    the reorder-only forwarder edit — and it CANNOT be built until this store + GradesProvider exist,
    because it reads them. Land THIS first, then WIRE becomes claimable (same dep-gated pattern as
    GH-SEAM-CHOKEPOINT). Do NOT fold the two into one ticket: this is a new-module build (single-writer,
    different skill/size), WIRE is a hot-path edit to an existing file — folding hides a real sub-problem
    and forces WIRE to build against a changing API.

  reads-only (no owns claim): src/charon/routing_policy/matrix.py (WorkClass/Grade vocabulary — reuse the
    types, do not edit), src/charon/capability/taxonomy.py (WIRE's classifier — not touched here),
    src/charon/capability/scorecard.py (the WRONG store — read for shape reference, never overloaded),
    charon-private/fleet/capability/grades.py + assign.py (the CONTRACT to PORT — read for the source
    allow-list / control-split / MIN_N semantics, NEVER imported).

  boundary note: fleet-repo grades logic is the reference; ZERO fleet imports in product code (accept #5
    is the fail-on-revert proof). CAPABILITY-ACTUALS-DEADREF-CLEANUP (economy, difficulty 1) is a separate
    hygiene ticket for the surviving dead `capability.actuals` refs; NOT a dep of this ticket, but the
    builder should note `capability/__init__.py`'s docstring also still names the deleted "actuals ledger"
    and may heal it if reviving that name (see path-uncertainty).

  BLAST RADIUS: product code, NEW module, single-writer — NOT the request hot path (that is WIRE). Low
    live-blast: nothing consumes the provider until WIRE lands. The risk here is CORRECTNESS of the
    fail-closed admission contract (accept #4/#5): a leaky allow-list would let fabricated outcomes poison
    routing once WIRE goes live, so adversarial review of the admission gate is warranted.

  wave: DRAFT — un-park after operator confirms decomposition + the product file paths. repo: charon (product).
