---
description: "pools redesign design-of-record — ~4 tier-pools + benchmark-fed grades table; one capability engine shared by gateway routing + fleet ticket-assignment; phased, grades gated"
metadata: 
name: charon-pools-redesign
node_type: memory
originSessionId: fbcc2b18-3ba9-4057-b3fd-af8c3e6ffb84
type: project
tags: [charon, design, pool, routing]
last_referenced: 2026-07-13
---
**Problem:** ~50 hand-maintained per-model pools, **82% boilerplate** ({zen,go,nanogpt,or} per family), priority is an **implicit list-order hack** (`cost_rank` inert since SR-6), 3 unlinked model-lists. Origin: Opus DESIGNED the abstraction well (ADR-0004) but the DATA was hand-populated one-curl-per-model, and `cost_rank` was built INERT by BLOCK-grade glm-5.2/deepseek-v4-pro work (see [[charon-build-methodology]]).

**Decision (operator-approved 2026-07-07):** ~4 **tier-pools** (Frontier/Strong/Capable/Basic, each just a SET of models) + a `model→{tier, per-work-class grades}` table; pools **DERIVED not enumerated**. Design-of-record = `fleet/POOLS-REDESIGN-ADR-v2.md` (v1 + adversarial review at `POOLS-REDESIGN-ADR.md`/`POOLS-REDESIGN-REVIEW.md`, verdict REWORK → resolved in v2).

**Adversarial-review key fix = SEQUENCING (grades are inert on today's data: 4/201 scored, all ~100):**
- **Phase 1** = structural tier-collapse + REAL cost/health routing — the elegant simplification, NO benchmark dependency, ships alone (this is what satisfies "not 40 pools").
- **Phase 1.5** = fleet ticket-assignment (#14) on today's `model-scorecard.tsv` signal.
- **Phase 2** = benchmark-fed per-work-class grades, GATED behind a **decision-differentiation gate** (ships only if it CHANGES the pick for ≥X% of requests — not field-populated; kills the SR-6 inert trap).
- **Phase 3** = destructive schema cleanup, split from the reversible routing-flip.

**Tiers SEEDED** from `model_catalog.py` (15) + reputation for all ~57 families; benchmark REFINES, never gates. Per-work-class grades come ONLY from benchmark-v2's own S0–S6 (public benchmarks don't map — false bridge; they seed coarse tier only). Work-class crux: declared-header → Arch-Router self-host classifier → GENERALIST default.

**UNIFICATION (the big idea):** the grades table has TWO consumers — gateway **request-routing** AND fleet **ticket→best-agent auto-assignment** (WCI, rig-level, task #14). Assignment has usable signal TODAY (scorecard discriminates agentic work) → de-risks "inert." Both share the work-class taxonomy + the session-bridge for availability/claim. Rig-level; product WCI parked ([[wci-rig-enforced-product-deferred]]). Prior art borrowed (self-hostable, no runtime dep): RouteLLM, Arch-Router, Unify two-signal, RouterBench.

**Prereqs/risks:** locate the models.dev→`cost_rank` pricing injection point (unlocated, HANDOFF L53); benchmark coverage; split destructive migration. Mechanization gates: decision-differentiation (anti-inert), DRY/boilerplate detector, commit+SHA+adversarial-review per phase.

**STATUS: design complete; BUILD not started (gated on operator kickoff).** Relates [[charon-work-composition-intelligence]], [[charon-own-work-engine]].
