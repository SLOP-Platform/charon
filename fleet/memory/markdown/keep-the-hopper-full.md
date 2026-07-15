---
description: DIRECTIVE — always maximize concurrent collision-free work; idle build/review capacity is waste; fan out up to review capacity
metadata: 
name: keep-the-hopper-full
node_type: memory
originSessionId: e0bdd97c-13d3-457c-9f6d-fdab97e90cc2
type: feedback
tags: [hopper]
last_referenced: 2026-07-13
---
DIRECTIVE (2026-07-12): **keep the hopper full.** Idle capacity is waste — whenever builds/reviews have slack, fan out MORE independent work rather than waiting. Standing rule for every session.

**Why:** the operator drives hard on wall-clock + concurrency; a single serial job while independent work sits idle is a defect.

**How to apply:**
- Fan out independent work streams in parallel — different repos / git worktrees / disjoint files (never two writers per file). CG opencode-headless builds + Claude review sub-sessions run concurrently.
- Before fanning out a big project WAVE, run the project-start audit + re-sequence first ([[project-start-audit-and-resequence]]) so concurrent chunks are truly collision-free, not colliding on shared substrate (e.g. KEYSTONE lenses depend on the KS29 registry / KS31 adapter substrate — audit before fanning).
- The real bottleneck is **manager REVIEW capacity** (every CG build needs an independent adversarial review before merge — self-reports lie). Balance fan-out against how many reviews can be turned around; don't launch so many that verdicts pile up unreviewed.
- **KEYSTONE** (24+ designed lens/component tickets KS8–KS32) is the largest idle pool — default hopper-filler once sequenced.
- Respect HARD project priority (ROUTER > BRIDGE > FLEET > SECURITY > BACKLOG) when choosing, but concurrency means many can run at once. See [[optimize-execution-wallclock-tokens]].
