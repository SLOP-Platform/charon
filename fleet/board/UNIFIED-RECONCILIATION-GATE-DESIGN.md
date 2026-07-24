repo: charon-private
tier: frontier
difficulty: 4
work_class: design-review
priority: 0
branch: design/unified-reconciliation-gate
depends_on:
owns: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md
work_class_note: |
  RANK-0 LEAD (operator-approved 2026-07-23, stass-allie handoff action #1). The durable ROOT FIX for the
  whole "built/planned-but-not-wired, norm-exists-but-unenforced, merged-but-not-retired" class the operator
  has repeatedly escalated. Desired==actual reconciliation: desired = tickets/ADRs/roadmap/registries/owns;
  actual = code/wiring/startup/live-config/git-tracked; RED-on-drift; required-check + timer. Design-only
  deliverable for OPERATOR REVIEW; spawns one-lens build tickets on approval. [[gates-must-actually-run]]
  [[no-rig-as-product-adopt-dont-handroll]] [[decomposed-by-design-not-reactive]]
accept: |
  DELIVERABLE = fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md — a design doc for OPERATOR REVIEW (no
  product/rig code changes beyond the doc). Scope is OPERATOR-CONFIRMED (2026-07-23) — do NOT re-scope or
  re-confirm; draft to exactly this:

  ## v1 SCOPE (cheap, high-value reconcilers ONLY — defer the rest to v2, named explicitly)
  Three reconcilers, each = desired-set vs actual-set → RED on drift, with a named actual-vs-desired source:
    1. **board↔PR↔done** — a ticket's board state vs its PR/merge/done-marker reality (the merged-but-not-
       retired + false-done class). Today's LIVE failure to design against: `reconcile-merged` goes AMBIGUOUS
       when a merged branch's file is owned by N tickets (can't prove WHICH landed) — the design MUST give a
       deterministic disambiguation (e.g. branch-name↔ticket-branch match, PR-title/ticket-id, merged-sha
       proof via done.sh --merged-sha) so shared-owned files stop wedging reconciliation.
    2. **owns-tracked** — every ticket `owns:` path is git-TRACKED (not gitignored/untracked). Root class:
       `fleet/state/*` is a blanket gitignore, so durable design/state deliverables vanish untracked unless
       force-added. Design the reconciler that makes this RED instead of silent.
    3. **gate-declared-vs-actually-wired** — every declared gate/check is actually INVOKED in a real firing
       layer (preflight/CI/hook). Wired-but-never-run = RED. (This is R44/R45/KS22/KS24 collapsed.)

  ## FOLD-IN (from BLAST-TIER review, action #3): the review-gate + gate-blindness-ledger BELONG HERE, not a
  parallel build. Absorb A's review-gate as a reconciler axis (declared-review-required vs review-actually-
  happened). Fix the taxonomy to FAIL CLOSED (unknown path ⇒ treated as high-blast / needs-review, never
  tier-0-no-review). PARK the grading consumer (Consumer B) — grades.py returns 0 real-outcome grades today
  (eval substrate empty); no grade-substrate circularity in v1. [[eval-system-under-repair]]

  ## DEFER TO v2 (name them, do NOT design them now): R44 e2e observable-effects ("prove a feature is
  EXERCISED, not merely reachable"); ADR/roadmap/config-manifest/registry drift; the grading consumer.

  ## ENFORCEMENT
    - rig: `preflight` + `land.sh` required-path + a timer (cadence check).
    - public product: native required-check (branch protection / CI required).
    - ⚠️ The `land.sh` `git -C` bypass residual is closed PROPERLY only via a Gitea server-side hook once
      Gitea-primary lands — FLAG it as an open seam; do NOT fake-close it. [[detection-ticketed-never-built]]

  ## BUILD POSTURE — ADOPT-FIRST
    - The reconciliation LOGIC itself = implement-as-pattern (VALIDATED by the WORKLOOP spike: no external
      tool reconciles "Charon's own state"; K8s/Terraform desired-vs-observed is the pattern). This is the
      sanctioned hand-roll — cite the validation.
    - The glue/feedback-loop HARNESS stays an OPEN SEAM pending WORKLOOP-INTEGRITY-STACK-SPIKE's finalized
      ao/Windmill verdict — do NOT hard-couple to a harness. Proceed NOW independent of that spike.
    - For each reconciler, name the drift-algorithm primitive it uses (content-hash / set-diff bidirectional
      / subset-schema-conformance / graph-reachability / staleness-probe-TTL) — this is the KS29 registry-
      primitive's discovery/drift leg; design so future reconcilers are DATA rows, not new scripts
      (anti-accretion, KS20).

  ## COMPLETION SELF-CHECK
    - Doc contains: the 3 v1 reconcilers (each with desired-source, actual-source, drift-algorithm, RED
      condition), the folded review-gate axis + fail-closed taxonomy fix, the parked/deferred list, the
      enforcement wiring + the flagged git -C seam, and a decomposed one-lens-per-reconciler BUILD BACKLOG
      (so approval spawns tickets cleanly). If any of these is missing, it is INCOMPLETE — do not submit.
scope: |
  Draft the unified reconciliation-gate DESIGN (desired==actual, RED-on-drift, required-check + timer) — the
  durable root fix for the built-but-not-wired / merged-but-not-retired / norm-unenforced class. v1 = 3 cheap
  reconcilers (board↔PR↔done, owns-tracked, gate-wired) + folded review-gate (fail-closed) + parked grading.
  Design-only, for operator review; spawns one-lens build tickets on approval.
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Design/eval only — owns ONE design doc, no code, no owns-collision.
  - informed-by (NOT blocked-by): WORKLOOP-INTEGRITY-STACK-SPIKE only informs the harness seam; proceed now.
  - supersedes-scope: R44 (dogfood-gate), R45 (inert-startup), KS24 (lens-drift), board-trust/auto-retire,
    owns-untracked/gitignore class, BLAST-TIER's review-gate + gate-blindness-ledger — all fold into this
    ONE design (do NOT build them piecemeal).
