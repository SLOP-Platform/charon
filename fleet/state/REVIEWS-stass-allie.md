# Independent adversarial reviews — stass-allie session (2026-07-23)

Durable capture of the two sub-session reviews the LEAD/next actions depend on (the live findings were
otherwise only in conversation + an ephemeral scratchpad). Referenced by SESSION-HANDOFF-stass-allie.md.

## WORKLOOP #172 (re-brief attempt 2) — VERDICT: BOUNCE (narrow)

Independent reviewer verified on 4-LOM (10.0.1.60). Deliverable: `feat/workloop-stack-spike-run:fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md`; PR #172 (draft, OPEN).

- **Executed trials: PASS — REAL, verified.** ao binary (23.99MB built), Omnigent `/v1/models`→464, Windmill images pulled, Archon built WITH a confirmed Gitea adapter (`packages/adapters/src/community/forge/gitea/*`). AP-12 satisfied for all four. DO NOT re-run trials.
- **Adopt-first ranking: VIOLATED 2/4 → auto-reject.** ao §1.3 ranks "Hand-rolled thin orchestrator (~200 LOC)" #1 above adnanh/webhook + Windmill; Archon §4.3 ranks "Hand-rolled Python approval gate (~200 LOC, no new dep)" #1 above pydantic/cerberus. Omnigent + Windmill verdicts ARE correctly adopt-led.
- **Reconciliation-loop (WLS-7): HOLDS UP** — legitimate implement-as-pattern (no external tool reconciles Charon's own state); genuinely the durable built-but-not-wired fix. This validates the reconciliation-gate LEAD.
- **Secondary:** EVAL-REGISTRY separate-commit provenance unmet; one cosmetic transcript-hygiene smell (claim verified TRUE, not fabrication).
- **Fix (narrow):** trial the demoted adopt options (adnanh/webhook; pydantic/cerberus), re-rank adopt-first (hand-roll only after adopt is executed-and-disproven), land EVAL-REGISTRY rows in separate commits.

## BLAST-TIER-ENFORCEMENT-DESIGN — VERDICT: NEEDS REVISION before build tickets

Deliverable: `fleet/state/BLAST-TIER-ENFORCEMENT-DESIGN.md` (landed). Reviewer ground-truthed against grades.py/assign.py/scorecard.

- **F1 (BLOCKER)** Consumer B builds on an EMPTY substrate: `grades.py` returns **0** real-outcome grades for all 6 models today — the EVAL-PROMOTION-GATE control-panel gate (`require_control_panel=True`) excludes every live row (needs a ≥3-row `strong-control` + ≥3-row `deepseek-v4-flash` split per ref; `strong-control` has 0 live rows; live refs are ~1 row each, 43 refs/46 rows). Grading + blast-tier routing PARK behind the eval-system repair. (Also: grades.py L651-654 docstring claims a "no-control→admit" fallback the code does NOT implement — a hard `continue`.)
- **F2 (BLOCKER)** Taxonomy self-contradicts + fails OPEN: §4 calls claim.sh "hot-path" but §0 maps `fleet/*.sh`→tier-1 tooling; tiers 2-4 key only on `src/charon/…` so no rig script can be high-blast, and an unknown `src/charon/new.py` matches nothing → tier 0 → no review. A security classifier MUST fail closed; this is gameable by PR-splitting.
- **F3 (MAJOR)** Review-gate loop not closed on the private rig: native branch-protection is paywalled (403), land.sh is a bypassable local script (`git -C` bypasses push guards; charon-ci runner still pending) → a direct merge escapes.
- **F4 (MAJOR)** "Independent reviewer" collapses to operator-forever (proven-model reviewers need Consumer-C grades, empty per F1 → operator does every hot-path review; autonomy goal blocked).
- **F5 (MAJOR)** Adopt-first consult INCOMPLETE — hand-rolled marker+land.sh without disproving ao/merge-queue, ignored WORKLOOP-RESEARCH's already-scoped stack (AP-5/AP-7 drift by our own rule). The gate-blindness-ledger + review-survived axis BELONG in the ONE reconciliation engine (R44/R45/KS24 same family), not a parallel build.
- **F6 (MODERATE)** "one home, no second copy" is aspirational across the 2-repo boundary (product blast_tier.py imported by rig via PYTHONPATH reproduces the hardcoded-dev-box-absolute coupling grades.py already has); adds a 4th taxonomy with no drift-guard.
- **F7 (MINOR)** Sequencing sane but tickets 4-6 are inert until F1, ticket 2 inert on private until F3 — would land "green" enforcing nothing (detection-ticketed-never-built).
- **Directive:** fix F1-F3, complete the F5 consult, FOLD the review-gate into the reconciliation-gate — before any build tickets.
