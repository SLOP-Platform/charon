repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: rig-meta
branch: feat/reconcile-handoff-freshness
owns: fleet/checks/reconcile-handoff-freshness.sh, fleet/tests/reconcile-handoff-freshness.test.sh
depends_on: RECONCILE-GATE-WIRED
real-dep: RECONCILE-GATE-WIRED build/correctness prereq — this reconciler reuses the declared↔actual
  reconcile scaffolding RECONCILE-GATE-WIRED establishes (drift-join primitive); building the freshness
  axis before that substrate exists would fork a bespoke check the RCA §5.2 explicitly says to fold in.
source: scratchpad HANDOFF-FAILURE-RCA.md §5.2 (luminara-unduli stale-handoff RCA); fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.x (design PR #178)
note: |
  The GENERATED-STATE block's whole premise is "a session cannot hand-assert these facts — machine-
  queried at handoff time." It failed SILENTLY on 07-23: never re-invoked, so it stayed honestly stale
  (product HEAD db62c61, generated=2026-07-21) while origin moved ~30 commits — and NOTHING flagged it.
  handoff-check.sh's freshness check (handoff-check.sh:79-84) only greps for the literal "⚠ STALE"
  string that generation emits, so a document that never regenerated trivially passes. This is a pure
  desired-vs-actual drift — the exact shape the reconciliation gate generalizes — so it belongs there
  as a 4th v1 reconciler, NOT a bespoke check.
accept: |
  - fleet/checks/reconcile-handoff-freshness.sh: for the newest fleet/SESSION-HANDOFF-*.md (and/or any
    changed one), RE-DERIVE live origin/master SHAs (product via /home/stack/code/charon, rig in-tree)
    and DIFF against the `origin-master product = <sha>` / `origin-master rig = <sha>` lines that
    handoff-generated-state.sh already machine-prints INTO the file. Mismatch, OR a `generated=`
    timestamp older than N hours, => RED. Fail-closed: product checkout absent => product axis
    UNVERIFIED (≠ GREEN), never silently skipped. Exit non-zero on RED, 0 clean.
  - Reuse the reconciliation substrate from RECONCILE-GATE-WIRED (declared↔actual cross-reference /
    reconcile scaffolding); do NOT rebuild the drift-join. Wiring owned by RECONCILE-WIRING.
  - fail-on-revert test: a fixture handoff whose baked-in origin-master SHA != the live HEAD → RED;
    update the SHA to match → GREEN. A `generated=` timestamp older than the freshness window → RED.
    Revert the SHA re-derivation → test goes RED.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — critical reconcile/gate code;
    manager gates, PR does NOT merge on the builder's self-report. Fix root cause, not symptoms; any
    pre-existing red touched is fixed or ticketed, never stepped around.
scope: |
  Rig-meta drift reconciler (handoff-freshness ↔ actual-HEAD). Detector only; auto-wiring belongs to
  RECONCILE-WIRING. Complements HANDOFF-GATE-NONBYPASSABLE (that makes handoff-check.sh run; this adds
  the staleness signal it currently lacks).
ds: |
  ## Dependencies & sequence
  Wave-2: depends_on RECONCILE-GATE-WIRED (reuses its reconcile scaffolding + is wired by
  RECONCILE-WIRING). Sequence AFTER the reconcile-gate substrate lands — do NOT build in parallel as a
  bespoke check (RCA §5.2: fold in, don't hand-roll). Disjoint owns from NAME-ALLOCATOR + NONBYPASSABLE.
