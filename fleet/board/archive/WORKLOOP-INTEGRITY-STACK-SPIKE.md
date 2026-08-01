repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 0
branch: feat/workloop-stack-spike-run
depends_on:
owns: fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md
work_class_note: |
  R0 LEAD LENS (operator 2026-07-22). Adopt-first eval of the work-loop-integrity STACK that durably
  fixes the built-but-not-wired / stale-board / gate-decay class (supersedes piecemeal INERT-WIRING +
  board-trust tickets — the reconciliation-loop pattern below IS the durable board-trust/auto-retire
  fix). Evidence base: fleet/state/WORKLOOP-INTEGRITY-RESEARCH.md (deep-research, 23 sources, verified
  real). POSTURE: solution-seeking — adopt where it fits; reject only with strong hands-on evidence and
  name the next-best. [[research-posture-solution-seeking]] [[adopt-substrate-build-only-novel-slice]]
accept: |
  ⛔ RE-BRIEF ATTEMPT 3 (2026-07-23 → fresh session — attempt 2, PR #172, was BOUNCED NARROW): the EXECUTED
  TRIALS are REAL and VERIFIED on 4-LOM (ao binary built 23.99MB; Omnigent /v1/models→464; Windmill images
  pulled; Archon built WITH a confirmed Gitea adapter at packages/adapters/src/community/forge/gitea/*).
  AP-12 is SATISFIED for all four — ⛔ DO NOT RE-RUN the ao/Omnigent/Windmill/Archon trials; cite the
  attempt-2 transcripts (on branch feat/workloop-stack-spike-run's deliverable doc) as evidence.
  The bounce is for ONE reason: **2 of 4 verdicts VIOLATE adopt-first ranking** →
    • ao §1.3 ranked "Hand-rolled thin orchestrator (~200 LOC)" #1 ABOVE adnanh/webhook + Windmill.
    • Archon §4.3 ranked "Hand-rolled Python approval gate (~200 LOC)" #1 ABOVE pydantic/cerberus.
  Ranking a hand-roll #1 before EVERY adopt option is executed-and-disproven = auto-reject drift
  (AP-5/AP-7, HAND-ROLL-IS-NEVER-THE-DEFAULT). Omnigent + Windmill verdicts are already correctly
  adopt-led — LEAVE THEM. This attempt is NARROW: do ONLY these three, then re-submit.
    1. **ao seam — EXECUTE the demoted adopt `adnanh/webhook`** (the webhook-glue candidate §1.3 skipped):
       run it on 4-LOM (10.0.1.60, `ssh -i ~/.ssh/4lom stack@…`; Docker non-root ok), wire a trial
       CI-fail→re-trigger hook against a scratch repo, capture the transcript (host + commands + observed
       output/errors). Re-rank ao's seam ADOPT-FIRST: adnanh/webhook (or Windmill) LEADS; the ~200-LOC
       hand-roll may appear ONLY as the after-adopt-disproven fallback, with the executed evidence that
       disproves it. If adnanh/webhook genuinely can't drive the seam, name the NEXT adopt (not a hand-roll).
    2. **Archon approval-gate seam — EXECUTE the demoted adopt `pydantic` (and/or `cerberus`)** as the
       YAML/DoD validation+approval engine: a real trial validating a sample DoD spec AND rejecting a
       malformed one, transcript captured. Re-rank ADOPT-FIRST: pydantic/cerberus LEADS; hand-roll only
       after-disproven with evidence.
    3. **EVAL-REGISTRY provenance**: land each (now adopt-led) ao-seam and Archon-seam verdict row in a
       SEPARATE commit (the attempt-2 secondary miss). Windmill/Omnigent rows unchanged.

  HARD RULES (unchanged): a REJECT's "next-best" MUST LEAD with an ADOPT candidate; a hand-roll may be
  named ONLY after EVERY adopt option has been EXECUTED and adversarially disproven with a transcript.
  "~N LOC we own" as the recommended path = auto-reject. COMPLETION SELF-CHECK: if the ao-seam or
  Archon-seam verdict still lacks an executed adopt-candidate transcript that PRECEDES any hand-roll
  mention, the deliverable is INCOMPLETE — do not submit.
  DELIVERABLE = fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md (attempt-2 verdicts, with ao §1.3 + Archon
  §4.3 re-ranked adopt-first on executed evidence) for OPERATOR REVIEW before any build. Do NOT mass-adopt;
  each subsequent adoption is its own one-lens ticket.
scope: |
  R0 lead lens: spike the adopt-first work-loop-integrity stack (ao first, then Omnigent, Windmill,
  Archon) to a per-tool adopt/reject verdict + one integrated adoption plan — the durable fix for the
  built-but-not-wired/stale/gate-decay class. Design-first; spawns one-lens build tickets on review.
  [[gates-must-actually-run]] [[no-rig-as-product-adopt-dont-handroll]]
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Design/eval only — owns one verdict doc, no code, no owns-collision.
  - internal sequence: ao FIRST (foundation + make-or-break git-topology test); Omnigent/Windmill/Archon
    follow; Archon's verdict depends on ao's (compose test). One coherent lens = the STACK decision.
  - supersedes-scope: the reconciliation-loop finding here is the durable form of board-trust/auto-retire;
    the manual retire (#154) + any quick sweep remain the interim stopgap until this lands.
