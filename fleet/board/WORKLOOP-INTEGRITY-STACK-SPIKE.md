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
  ⛔ RE-BRIEF (2026-07-23 — the first attempt, closed PR #161, was BOUNCED): it was a source/docs audit,
  not a RUN, and it defaulted 3/4 verdicts to hand-roll. Both are now hard-blocked by landed doctrine —
  EVAL-REGISTRY.md AP-12 (source-reading is NOT a valid trial for a RUNNABLE candidate) and
  HAND-ROLL-IS-NEVER-THE-DEFAULT. This attempt MUST satisfy:
    • EXECUTED TRIALS ON REAL HOSTS. We have them — 4-LOM (10.0.1.60, `ssh -i ~/.ssh/4lom stack@…`; Docker
      usable non-root, 12 cores / 11GB free), plus BB-8, Rocinante, LO-LA59. "Couldn't run it hands-on" is
      NOT available. Each layer's verdict receipt MUST include the ACTUAL host + commands run + observed
      output/errors (a transcript), NOT a file:line source citation. Source-reading may confirm an ABSENCE
      (e.g. "no gitea/ adapter dir") but can NEVER stand in for the make-or-break RUN.
    • ADOPT-FIRST RANKING. A REJECT's "next-best" MUST LEAD with an ADOPT candidate; a hand-roll may be
      named ONLY after EVERY adopt option has been EXECUTED and adversarially disproven. Ranking hand-roll
      first, or "~N LOC we own" as the recommended path, is auto-rejected drift (AP-5/AP-7).
    • BUILD ON, don't redo, the closed PR #161 doc's CONFIRMED facts (git-topology reframe; Databricks
      authorship) — cite them as evidence; the RUNS (ao/Omnigent/Windmill/Archon) are what must actually happen.
    • COMPLETION SELF-CHECK: if any verdict on a runnable tool lacks an executed-trial transcript, the
      deliverable is INCOMPLETE — do not submit it as done.

  A hands-on spike (NOT doc-reading) producing, for EACH layer, an adopt / reject / adopt-with-caveats
  verdict + an EVAL-REGISTRY row, plus one integrated "adopt this stack, wired in this order" recommendation
  (or a reasoned reject-with-next-best). Run the make-or-break integration test for real:
    1. **agent-orchestrator ("ao") — LEAD, do FIRST**: does it drive OUR git topology (Gitea-primary +
       GitHub-mirror) or is it GitHub-API-coupled? Point it at the local gateway. If ao doesn't fit the
       git topology, the whole wrap-incrementally plan shifts — so this gates the rest.
    2. **Omnigent**: does it actually speak our local gateway (OpenAI base_url) with NON-Claude models?
       Assess the alpha-maturity risk with a real run, not the README.
    3. **Windmill** (n8n already REJECTED — no checkpoint/resume): express ONE DoD stage as a git-synced
       flow; assess real solo-operator ops burden (Postgres + workers).
    4. **Archon**: does its YAML validation/approval-gate engine COMPOSE on top of ao's glue loop, or
       conflict on worktree/merge-lifecycle ownership?
  Also record which methodology PATTERNS to implement-not-install: GitHub merge queue (NOTE: needs a paid
  plan for the private rig; free on the public product repo), trunk-based two-gate DoD (machine CI + human
  review), and the K8s-style reconciliation loop (desired-vs-actual) as the auto-retire / catch-unwired
  mechanism. Each adopt verdict lands its EVAL-REGISTRY row in a SEPARATE commit (provenance).
  DELIVERABLE = fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md (the verdicts + integrated adoption plan)
  for OPERATOR REVIEW before any build. Do NOT mass-adopt; each subsequent adoption is its own one-lens ticket.
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
