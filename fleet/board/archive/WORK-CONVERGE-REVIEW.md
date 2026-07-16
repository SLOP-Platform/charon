tier: frontier
difficulty: 4
work_class: design-review
branch: docs/work-converge-review
depends_on:
owns: /home/stack/charon-private/fleet/state/WORK-CONVERGE-DESIGN.md
accept: |
  A REVIEW + DESIGN-OF-RECORD (no build) that answers: how is SLOP (mediastack) work done TODAY vs how
  is CHARON (fleet rig) work done, and should the SLOP way be REPLACED with the Charon way — taking the
  BEST parts of BOTH. Deliverables in fleet/state/WORK-CONVERGE-DESIGN.md:
  (1) side-by-side of both processes (intake -> decompose -> assign -> build -> review -> land -> handoff),
  (2) best-of-both extraction (what Charon's fleet rig does better, what SLOP does better),
  (3) a design for ONE MODULAR, PORTABLE "get-work-done" tool applicable to ANY future project — clear
      interfaces, what is PORTABLE (the engine) vs PROJECT-SPECIFIC (config/adapters), so we never again
      have multiple ways of doing work,
  (4) an explicit recommendation + migration plan for moving SLOP onto it.
  This FEEDS B5 (obol-adr-0008, portable orchestration store) and B6 (work-engine-d10) — reconcile with
  those designs, do not duplicate them.
requirements: |
  OPERATOR VISION (2026-07-10) — the modular tool = the Charon manager pattern AS WE RUN IT NOW,
  productized. The design MUST cover, as first-class modules:
  1. COORDINATOR — a high-level manager model that works EXTREMELY smartly, minimizing its own token
     use as optimally as possible. MODEL-AGNOSTIC: Claude Opus OR any equal frontier model can BE the
     manager; the process must not depend on which. [[coordinator-token-economy-doctrine]]
  2. AUTOMATIC — the process runs mechanically, not on manager memory/recall (hooks/gates/launchers/
     preflight do the enforcing). A fresh session of any capable model just works.
  3. WORK QUALITY TRACKING — model scorecard, rank by REAL outcomes (not synthetic benchmarks),
     detect+down-rank models that self-report false success. [[benchmark-not-a-valid-ranker]]
     [[document-model-self-report-lies]]
  4. CHARON WORK ROUTING — route sub-work through the Charon gateway to the best-fit model/provider
     (off the Claude limit), review only packets+diffs. [[route-work-to-charon-not-claude]]
     [[charon-headless-review-loop]]
  5. THE BRAINS (work-composition intelligence) — schedule for max concurrency, no redundancy/
     contradiction, dependency-minimizing decomposition; decomposed-by-design. [[charon-work-composition-intelligence]]
     [[decomposed-by-design-not-reactive]]
  6. PROVIDER / POOL / MODEL / TIER management — the capability engine that drives BOTH gateway
     routing AND fleet work-assignment; funding-class drain-then-park; free-tier-first. [[charon-pools-redesign]]
     [[charon-drain-then-park-provider-class]] [[charon-free-tier-routing]]
  Modularity is the through-line: a portable ENGINE (1-6) + thin PROJECT-SPECIFIC config/adapters, so
  ANY future project plugs in and gets the same disciplined process — never a second way of working.
scope: |
  Operator ask (2026-07-10): the "get work done" process should be a MODULAR TOOL reusable across
  projects; converge SLOP + Charon so there is ONE way. Related: [[charon-own-work-engine]],
  [[charon-portable-orchestration-store]] (obol), [[decomposed-by-design-not-reactive]].
ds: Cross-project (SLOP + Charon) but REVIEW/DESIGN only — no build, no file collisions. A dedicated
    review session. Sequence BEFORE building B5/B6 (it sets their requirements).
