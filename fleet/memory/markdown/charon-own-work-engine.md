---
description: "Operator decision — Charon will own the work-engine in-tree (ADR-0007 D10), sooner rather than later; not external-tooling-forever"
metadata: 
name: charon-own-work-engine
node_type: memory
originSessionId: 04b7358b-67d3-40fe-ad36-24ab7cb15864
type: project
tags: [charon, engine]
last_referenced: 2026-07-13
---
2026-06-26 operator decision: Charon should **own the work-engine in-tree** (the ADR-0007 D10 deferred engine: board + atomic claim/lease + spawn-to-demand scheduler, plus the `WorkerBackend` port for headless `claude -p`/droid/remote workers), **sooner rather than later** — NOT kept as external operator-tooling forever.

This reframes ADR-0007's engine from "deferred behind tripwires, maybe never" to "deferred but on the roadmap." The `build-rig/fleet/` bash rig (board.sh/claim.sh/done.sh/fleet-droid.sh) is the working reference implementation to promote into `src/charon`, while honoring D11 anti-dilution (the engine must never bloat the gateway-first request path / install footprint).

Build-order context: ADR-0008 Phase 1 (human-gated intake→ticket-plan front door) has NO tripwire and is the highest-leverage near-term build; it also captures the top-level product acceptance that N4's `validate.py` (D12) currently stubs at unit-level. Still deferred pending data/triggers: D5 auto-land, AIMD capacity, scanner matrix, ADR-0008 Phase 2 auto-run.

**CRITICAL DISTINCTION (operator, 2026-06-26): the dev-box build harness ≠ Charon's product worker model.** The `build-rig/fleet/` rig runs `claude -p` droids — that is ONLY how we BUILD Charon in this dev box ([[charon-build-via-fleet]]). **Charon's engine will NOT use `claude -p`; its workers are ACP agents.** So we port the rig's COORDINATION design (board/claim/scheduler) but NOT its worker-execution model. Consequences: ACP agents are **warm-poolable** (reuse subprocess + `session/new` + fresh per-unit worktree) per ADR-0007 D7 — no cold-start-per-unit drain; the existing `AgentBackend`/`AcpBackend` + `parallel.py` ThreadPool already IS the worker-execution substrate; the `WorkerBackend` port + headless-CLI adapter (ADR-0007 D10-2 / ADR-0010 D2) was premised on non-ACP out-of-process workers the PRODUCT won't have → defer it (ACP is blocking-drivable today). Liveness = ACP-deadline + checkpoint-kill (D8); no process-group/zombie machinery needed. ADR-0010 D2/build-sequence needs correcting (it baked in the dev-rig's headless-CLI worker as a product adapter — my error).

Conflict-rate evidence so far (D10-C gate): ~8 parallel-unit PRs merged conflict-free across today's waves (N1/N2/T8/N4/T7/N5 + ratify). Record ongoing in REVIEW-LOG as the data that gates Phase 2 / auto-land.

Related: [[charon-perf4-next-session]] [[remaining-work-includes-designed-not-built]] [[charon-vision-gateway-first]] [[charon-build-via-fleet]]
