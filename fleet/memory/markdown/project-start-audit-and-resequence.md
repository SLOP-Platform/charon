---
description: "MECHANIZED — at the start of each project/major wave, launch a code-confirmed audit of its tickets (built/partial/stub, file:line) + re-order the sequence on facts BEFORE building"
metadata: 
name: project-start-audit-and-resequence
node_type: memory
originSessionId: a95dc541-223e-4053-8197-6848f0322d6b
type: feedback
tags: [audit, hygiene, project]
last_referenced: 2026-07-13
---
DIRECTIVE (2026-07-11): at the START of each project — and each major wave — **mechanically launch a code-confirmed AUDIT before building**, exactly like the Router Wave 3 audit:

- For each ticket in the wave: confirm **BUILT / PARTIAL / STUB / NOT-STARTED with file:line** by reading the real code — NOT board status, NOT the plan, NOT docstrings (a docstring can lie). See [[confirm-dont-trust-documentation]].
- Surface: already-built work, false blockers, and **pull-up candidates** from other waves / the Backlog.
- Then **RE-ORDER the wave on facts** and adversarially spot-check the "already-built" claims before trusting them.
- **Never start building a wave on an inferred sequence.**

**Why:** the Router Wave-3 plan was inference-based and wrong on nearly every point — balance poll-adapters already built; R15 free-tier-order already shipped; R12 NOT a real prereq for R11; `balance_tracker` never wired into gateway config so R4's `record_spend` was dead code. The audit caught all of it; the plan (and even a passing adversarial review) had not.

**How to mechanize (the ask):** a fleet `project-audit.sh <project>` that enumerates the next wave's tickets and fans out per-ticket code-confirmed fact-cards on NW; a preflight/kickoff gate that BLOCKS starting a project's build until its fact-based audit + re-sequence exists. Enshrined in MANAGER-OPERATING-RULES so it loads every session.
