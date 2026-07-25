repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 2
branch: fix/inert-wiring-enforcement-durable
depends_on:
owns: fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md
work_class_note: |
  OPERATOR-ESCALATED (2026-07-22): built-but-not-wired / partially-wired code keeps recurring DESPITE
  multiple audits (R43 WIRING-AUDIT, ON-DEMAND-TOOL-AUDIT, GAP-AUDIT) and fixes that "don't work over
  time." This ticket is DESIGN-FIRST — do NOT build another gate before explaining WHY the prior ones
  decayed, or it repeats the failure. [[gates-must-actually-run]] [[detection-ticketed-never-built]]
  [[dynamic-tools-never-on-demand]] [[audit-hand-rolled-vs-best-in-class]]
accept: |
  Deliverable: fleet/state/INERT-WIRING-ENFORCEMENT-DESIGN.md containing —
  1. INVENTORY (evidence, file:line): every anti-inert / wiring / freshness gate across BOTH repos and
     its ACTUAL enforcement state — orphaned (no caller) | advisory (runs, non-blocking) | required
     (merge-blocking). Seed facts already confirmed 2026-07-22 (verify + extend, don't re-derive):
       - PRODUCT (SLOP-Platform/charon, PUBLIC → CAN require checks): check_inert_code.py IS wired —
         src/charon/gate_runner.py calls it, run by `charon.cli gate` in .github/workflows/ci.yml. So
         the product inert gate is enforceable/required. VERIFY it is actually a REQUIRED status check.
       - RIG (Nnyan/charon-private, PRIVATE on a FREE plan → CANNOT make any check REQUIRED): this is a
         STRUCTURAL enforcement hole — branch protection can't force any gate. graphify-freshness.sh is
         ORPHANED (0 callers; its own header claims preflight wiring that doesn't exist → the product
         code map drifted 2 days stale, re-mapped manually this session). rule-coverage.sh IS wired into
         preflight.sh (but preflight isn't merge-blocking on the rig).
  2. ROOT CAUSE: why fixes decay. Test these hypotheses with evidence: (a) rig can't require checks
     (free plan) so rig gates are always bypassable; (b) audits are point-in-time SNAPSHOTS, not
     ratchets — they find inert code once but nothing prevents the next; (c) the anti-inert gates are
     themselves un-wired (the cure has the disease); (d) NO meta-gate asserts the gates STAY wired.
  3. DURABLE MECHANISM (pick ONE, state its explicit ANTI-DECAY property): e.g. a WIRING MANIFEST +
     meta-gate that runs INSIDE the product's REQUIRED CI check (product is public → un-bypassable) and
     asserts every registered anti-inert gate is actually invoked by an enforcement point — so un-wiring
     any gate (or shipping a detector with no caller) FAILS the required check. Analogous to how
     COVERAGE-META-GATE/rule-coverage.sh classifies every rule mechanized|guidance|gap. Address the rig
     structurally: recommend rig-public-or-paid (to enable required checks) vs enforce-only-via-land-push
     (+ no-raw-push discipline) — quantify the trade.
  4. BUILD BACKLOG: the concrete wiring fixes this design spawns (wire graphify-freshness; any other
     orphans found), each as a follow-up ticket with a wiring-assertion test.
  This is a design/eval doc for OPERATOR REVIEW — do NOT self-approve and mass-build; land the design,
  then the operator greenlights the build tickets.
scope: |
  Root-cause the recurring built-but-not-wired CLASS (operator-escalated: prior audits/fixes decay) and
  design ONE decay-proof enforcement mechanism, with the rig's free-plan "no required checks" structural
  hole called out explicitly. Design-first; spawns the build backlog. [[gates-must-actually-run]]
ds: |
  ## Dependencies & sequence
  - depends_on: (none). Design/eval only — owns one design doc, no code, so no owns-collision (notably
    NOT fleet/preflight.sh, which is already contended by 5 live tickets — that contention is itself a
    data point for the design).
  - spawns: per-orphan wiring build tickets (graphify-freshness wiring, etc.) + possibly a
    product-CI wiring-meta-gate ticket, after operator review of the design.
