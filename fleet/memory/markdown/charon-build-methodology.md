---
description: How the user wants Charon (cross-vendor agent orchestrator) built — autonomous tier-by-tier with adversarial review gating every decision
metadata: 
name: charon-build-methodology
node_type: memory
originSessionId: 836ec640-6ff1-4e4a-952a-35ae5258992b
type: feedback
tags: [build-rig, charon, methodology]
last_referenced: 2026-07-13
---
For the Charon project (`/repo/charon`), the user wants fully
autonomous tier-by-tier building (proceed through every ADR tier without pausing
unless a true hard-stop), with **adversarial review gating every decision**:

- **Low-impact decisions** → one focused adversarial reviewer each, in parallel
  (multiple per area is fine). Lenses are read-only `Explore` subagents.
- **Very significant / impactful decisions** → a **DTC** (Decision-Theoretic
  Committee): a multi-agent `Workflow` of N independent competing proposals,
  judged by M adversarial lenses, then a high-effort synthesis that reconciles
  **against physics, not by vote**.
- The author (me) reconciles every finding in `docs/REVIEW-LOG.md` — accept /
  reject / re-scope with the reasoning, before writing code. Reviewers are
  XREF-class: they flag, they do not veto.
- **CHECK THE DECISION REGISTER FIRST (`docs/DECISIONS.md`).** Every DTC /
  adversarial review must consult it before deliberating; a charge that contradicts
  a `Settled` row is flagged "contradicts Dxxx" and surfaced — never silently
  re-decided. `OP`-owned decisions reopen only with the operator's explicit
  re-confirmation ([[adversarial-review-must-not-silently-override-operator]]);
  `AI`-owned are evidence-revisable. New decisions append to the register as part of
  the ADR/REVIEW-LOG flow. Lens prompts must embed this check. This register exists
  because a review once silently inverted an operator decision (the engine-ownership
  call) and it propagated across sessions.

**Why:** the user runs a derive-or-verify, structural-over-honor-system shop; the
review log + proven-red tests are the proof, not the claim. Recurrent winning
themes the reviews enforce: **thinness/YAGNI**, **don't build ahead of the
consumer**, **sunset durability** (the git+JSON Ledger outlives Charon), and
**honest disclosure** (the Mode-B container is the only real agent boundary; the
in-process fence only detects).

**How to apply:** each tier = draft `PLAN-tierN.md` → launch reviewer(s)/DTC →
reconcile in REVIEW-LOG → build the reconciled scope with proven-red tests → keep
ruff+mypy+pytest+boundary green → commit per tier. Re-scope freely before code
(cheapest place to change direction); record any walk-back. See
[[charon-project-state]] for what is built vs deferred.
