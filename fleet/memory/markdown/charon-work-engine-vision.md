---
description: "North-star — productize the Charon manager pattern into ONE modular, model-agnostic, automatic work engine"
metadata: 
name: charon-work-engine-vision
node_type: memory
originSessionId: 96433b6d-311d-4b89-aff5-8b7f8f3e8d4d
type: project
tags: [charon, engine, vision]
last_referenced: 2026-07-13
---
Operator vision (2026-07-10): the "get work done" process should be a MODULAR TOOL reusable across ANY
project — the Charon manager pattern AS RUN NOW, productized, so there is never more than one way to work.

Required first-class modules (a portable ENGINE + thin project-specific config/adapters):
1. **Coordinator** — high-level manager model that works EXTREMELY smartly, minimizing its own token
   use optimally. MODEL-AGNOSTIC: Claude Opus OR any equal frontier model can be the manager. [[coordinator-token-economy-doctrine]]
2. **Automatic** — runs mechanically via hooks/gates/launchers/preflight, not on manager recall; a fresh
   session of any capable model just works.
3. **Work-quality tracking** — scorecard, rank by REAL outcomes not synthetic benchmarks, down-rank
   models that self-report false success. [[benchmark-not-a-valid-ranker]] [[document-model-self-report-lies]]
4. **Charon work routing** — route sub-work to the gateway / best-fit model off the Claude limit;
   review packets+diffs. [[route-work-to-charon-not-claude]] [[charon-headless-review-loop]]
5. **The brains (WCI)** — max concurrency, no redundancy/contradiction, dependency-minimizing
   decomposition; decomposed-by-design. [[charon-work-composition-intelligence]] [[decomposed-by-design-not-reactive]]
6. **Provider/pool/model/tier management** — one capability engine driving gateway routing AND fleet
   assignment; drain-then-park by funding class; free-tier-first. [[charon-pools-redesign]] [[charon-own-work-engine]]

Tracked as ticket WORK-CONVERGE-REVIEW (B7) → feeds obol/B5 + work-engine-d10/B6. [[charon-portable-orchestration-store]]
