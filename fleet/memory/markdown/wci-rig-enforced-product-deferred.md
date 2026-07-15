---
description: "DECISION 2026-06-27 — WCI mechanized+enforced at RIG level now (hard-gate static, advise semantic); PRODUCT-level WCI parked until Charon is production-ready, and when built must be opt-in-orchestrator-only + advisory/override for users"
metadata: 
name: wci-rig-enforced-product-deferred
node_type: memory
originSessionId: 6a15dd76-f504-4a39-bf2c-48d8ef5bf755
type: project
tags: [build-rig, ci, decomposition, product, wci]
last_referenced: 2026-07-13
---
WCI (work-composition intelligence) is the enshrined scheduling method. **Operator decision 2026-06-27:**

1. **RIG level — mechanize + enforce NOW.** A fleet-board enforcer that runs on board mutations: **hard-gate the deterministic checks** (false-blocking deps = a `depends_on` between disjoint-owns tickets that isn't a declared real build-dep; owns-collisions within a wave; redundancy/contradiction between ready tickets), and keep any **semantic/LLM judgment advisory-only** (never wedges the board). Hard-gating is acceptable here because it's our build-rig and we accept the discipline.

2. **PRODUCT level — PARKED.** WCI-MVP in `src/charon` is deferred: "no time now; focus is getting Charon to a fully working production-ready state." Revisit after production-ready.

3. **Blast-radius constraint for when product WCI is eventually built** (operator raised this): it must apply **ONLY within the opt-in orchestrator/engine path** — never imposed on gateway-only or single-task fresh-install use (that would violate [[charon-vision-gateway-first]] orchestrator-opt-in and [[charon-production-readiness-mindset]] fresh-install-must-just-work). For product users it should be **advisory-with-override, NOT hard-gating by default**; hard-gating stays a rig-only choice.

**Why:** mechanizing WCI on our own backlog stops the manual per-pass scheduling reasoning and enforces minimal-blocking/sane-concurrency automatically; deferring the product side keeps the team focused on release-readiness and avoids shipping an opinionated scheduler that could block a stranger's install. Links: [[charon-work-composition-intelligence]], [[product-vs-build-rig-boundary]], [[disjoint-owns-not-no-dependency]], [[charon-own-work-engine]].
