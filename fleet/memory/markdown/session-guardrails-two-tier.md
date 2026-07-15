---
description: DTC-approved design for process-discipline guardrails — CI required-check (real enforcement) + land-push gate + MANAGER-RULES SSOT; git pre-push hook REJECTED; gateway-inject deferred
metadata: 
name: session-guardrails-two-tier
node_type: memory
originSessionId: e2478a55-c53f-48cc-9378-5c328f54aa8f
type: project
tags: [guard, guardrail, session, tier]
last_referenced: 2026-07-13
---
**Design of record (2026-07-11, DTC-reviewed + operator-approved 5-decision walkthrough).** Doc: `fleet/PROPOSAL-SESSION-GUARDRAILS.md`. Problem: sessions keep repeating 4 process-discipline mistakes — (a) build without scanning existing work, (b) merge key work unreviewed, (c) verification mistakes (piped `$?` false-green), (d) trust docs over code — across BOTH Claude Code and opencode/CG harnesses. Native Claude hooks bind Claude sessions only, NOT CG.

**Rejected wholesale:** Qodo / awman / ghost-in-the-loop / Guardrails-ai/NeMo (wrong layer/shape); addyosmani/agent-skills = BORROW 1-2 skills only.

**Approved architecture:**
1. **CI required status check = the real enforcement** — `charon.cli gate` as a required branch-protection check: repo-bound, un-bypassable, reaches CG+human identically, and CI *re-runs* the verification so false-green is truly defeated (the one place). Cost: mostly a branch-protection setting (CI gate already exists).
2. **Gate in `land-push.sh`** (the manager's push lever, lives in the private rig so it can read board/reviews/project-audit WITHOUT product-leak) — fast local gate on the manager-landing path; require a review record for money-path, `--override` escape.
3. **Fold the 4 disciplines into `MANAGER-OPERATING-RULES.md`** (single SSOT already SessionStart-loaded); JOIN-PROMPT + CG AGENTS.md REFERENCE it, don't duplicate.

**REJECTED by DTC (do not revive):** the git `pre-push` hook — would brick every push (`project-audit.sh` exit-2 = "prior work exists" is the normal state at push time), adds ZERO CG reach (CG never pushes; land-push already the CG-landing chokepoint), and leaks `~` private paths into the public product repo. My "refine land-push → git hook" was wrong; land-push was right.

**Deferred:** gateway contract-injection — see [[charon-gateway-contract-inject-deferred]] (wake-trigger cg-drift.sh, ≥2/30d).

**Hard limits (solo setup):** reviewer≠builder is UNVERIFIABLE (single git identity Nnyan) — gates can require "a review record exists," not enforce independence. Related: [[product-vs-build-rig-boundary]], [[adversarial-review-default-for-droid-prs]], [[confirm-dont-trust-documentation]].
