# WORK-CONVERGE-REVIEW — Review Fragment

**Date:** 2026-07-12
**Ticket:** WORK-CONVERGE-REVIEW (B7)
**Class:** design-review
**Verdict:** DESIGN-OF-RECORD delivered

## Scope

This ticket produced a REVIEW + DESIGN-OF-RECORD (no build) converging the embedding host project's and Charon's (build rig) work processes into ONE modular, portable "get-work-done" tool. The design is the operator-requested authority document that feeds B5 (obol-adr-0008) and B6 (work-engine-d10).

## Charge

SIDE-BY-SIDE comparison of both processes, BEST-OF-BOTH extraction, MODULAR TOOL design (6 first-class modules with portable ENGINE + thin project-specific ADAPTERS), and MIGRATION PLAN for the host project onto the converged engine.

## Key Decisions

1. **Charon's engine is the destination.** Its stdlib-only, ports-and-adapters architecture, epoch-fenced claims, fenced execution, and diff-scope guard make it the right substrate. The host project's strengths (DToC, per-finding review reconciliation, gated session lifecycle, self-policing team, file-size ratchets) are ADOPTED as adapters or separate modules, not as competing engines.

2. **Modular boundary = ports + config.** The portable engine is 6 modules (Coordinator, Automatic, Quality Tracking, Work Routing, WCI Brains, Provider/Pool/Model/Tier Management) over the obol orchestration store. A project adapter implements 5 ports (AgentBackend, Reviewer, GateRunner, TicketSource, TicketSink) + one project config file.

3. **Six-phase migration for the host project.** Phase 1 (obol ships, parallel run) → Phase 2 (its ticket DB mirrors to obol) → Phase 3 (its workers claim via obol) → Phase 4 (it adopts fenced execution) → Phase 5 (model unification via capability engine) → Phase 6 (consolidation: retire the legacy ticket DB, unified session bridge). Each phase is SLA-bounded.

4. **The coordinator doctrine v2 is mechanized into the coordinator module.** All 13 rules, including the must-read-full carve-outs C1-C7 and the anti-rubber-stamp citation requirement, become mechanical checks in the engine — not model judgment.

5. **WCI (Work Composition Intelligence) is intake-time decomposition** with 3 mechanized pillars: deduplicate (no redundancy), maximize concurrency (collision-free wave packing), minimize deps (file-level ownership over feature-level). The decomposed-by-design gate catches god-file candidates at claim time.

## GROUND

- Charon build-rig process: verified by code-reading `src/charon/cli.py`, `src/charon/intake.py`, `src/charon/coordinator.py`, `src/charon/engine/board.py`, `src/charon/engine/claim.py`, `src/charon/engine/scheduler.py`, `src/charon/land.py`, `src/charon/ledger.py`, `src/charon/decompose.py`, `src/charon/router.py`, `src/charon/pools.py`
- Host-project process: verified by code-reading its full mailbox suite (worker loop, join prompt, team protocol, work-claim, end-session, heartbeat, warden + warden-tick, tier routing, note-work, subtask), its ticket-DB query tool, and its review-log, core-rules, and ticket-work onboarding docs
- Coordinator doctrine v2: sourced from the build rig's coordinator-doctrine v2 document (APPROVED 2026-07-08, 4-lens adversarial review, 21 decision narrowing, 13 rules, 6 open decisions)
- obol v2 design: sourced from the build rig's portable-orchestration-store plan (7 consensus blocker-fixes, 3 operator rulings, full schema + architecture)
- ADR-0010 (work-engine substrate): sourced from `docs/adr/0010-native-work-engine-substrate.md` (D1 building-native, D2 components, D3 propose-default, D5 what-stays-gated)
- ADR-0016 (demand-driven capability match): sourced from `docs/adr/0016-demand-driven-capability-match.md` (live/sourced/reactive matrix, fail-loud contract, 5-layer selection order)
- Operator visions: sourced from memory facts `charon-work-engine-vision`, `coordinator-token-economy-doctrine`, `benchmark-not-a-valid-ranker`, `document-model-self-report-lies`, `route-work-to-charon-not-claude`, `charon-headless-review-loop`, `charon-work-composition-intelligence`, `decomposed-by-design-not-reactive`, `charon-pools-redesign`, `charon-drain-then-park-provider-class`, `charon-free-tier-routing`, `charon-own-work-engine`, `charon-portable-orchestration-store`

## Unverified / Open

- 6 open decisions deferred to operator (Section 7): engine package name, engine home repo, obol daemon lifecycle, the host project's worker-loop future, coordinator model floor, KSF adoption scope
- The migration plan SLA estimates are rough; actual cadence depends on B5/B6 build velocity and operator resource allocation
- The `DToCReviewer` adapter is conceptual only — a real adapter requires the DToC engine (`debate-to-consensus.js`) to be callable as a protocol-compliant reviewer
- The `ClaudePBackend` adapter is conceptual only — wrapping `claude -p` inside a fenced worktree with escape detection is novel engineering
