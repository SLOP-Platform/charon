repo: charon-private
tier: strong
difficulty: 3
priority: 1
work_class: bugfix
branch: feat/reconcile-board-pr-done
owns: fleet/checks/reconcile-board-pr-done.sh, fleet/tests/reconcile-board-pr-done.test.sh
serial_justified: The check and its fail-on-revert test are one invariant — a reconciler
  shipped without its own RED-on-revert fixture is exactly the built-but-inert class this gate
  exists to catch. Splitting orphans the contract; they land together or not at all.
depends_on:
source: fleet/state/UNIFIED-RECONCILIATION-GATE-DESIGN.md §1.1 (design PR #178, RANK-0 LEAD)
work_class_note: bugfix — the AMBIGUOUS exit-1 wedge in reconcile-merged.sh (the merged-but-not-
  retired / false-done class) is a live defect; this ticket resolves the wedge deterministically
  instead of the current silent bail.
note: |
  §1.1 — the board↔PR↔done reconciler. desired-source = each ticket's tier:/branch:/owns:/done:
  in fleet/board/*.md + archive/*.md. actual-source = GitHub PRs whose head branch matches a
  ticket branch: and whose mergeStateStatus is MERGED, cross-referenced with done.sh proof
  records (merged:#pr / --merged-sha). drift-algorithm = set-diff/bidirectional (KS29 leg) over
  (merged-PR-set, open-ticket-set) joined branch↔ticket-branch.

  REUSE-FIRST (do NOT rebuild): compose fleet/reconcile-merged.sh — its branch-index / owns-index
  (reconcile-merged.sh:130-180), its ticket_for_pr() fan-in, and the CREATION-PR GUARD
  (reconcile-merged.sh:194-222: a merged PR that adds the ticket's OWN board/<id>.md but delivers
  none of its owns: is a creation, not a completion). This ticket wraps + extends that indexing;
  it does not re-implement PR/branch joining. It does NOT decide what `done` means (that is
  done.sh + the merged: proof field) and does NOT enforce review (that is RECONCILE-REVIEW-GATE).

  DETERMINISTIC DISAMBIGUATION (root fix for the AMBIGUOUS wedge, reconcile-merged.sh:165/177):
  when a merged PR's file-set is owns:-owned by N>1 tickets, resolve by ORDERED PROOF, never a
  silent bail — (1) branch↔ticket match (primary, unique); (2) PR-title / merge-commit-subject
  ticket-id substring match (secondary — the documented escape hatch for shared-owned files, via
  gh pr view --json title,body + git log -1 --format=%s); (3) merged-sha proof recorded by the
  operator in fleet/state/reviewed/<id>, matched on the next pass. Until adjudicated the PR stays
  STATUS=NEEDS-MANUAL-ADJUDICATION (never auto-close on a hash guess).
revisions_baked_in: |
  REVISION-1 (fail CLOSED, #182): the AMBIGUOUS / unknown / unresolvable case defaults to RED
  (NEEDS-MANUAL-ADJUDICATION), NEVER pass. A merged PR that resolves to no unique ticket is a
  deterministic RED-with-instruction, not a silent exit-0. Unknown branch → treated as drift, not
  as "probably fine."
  REVISION-2 (timer-wireable today, #182): this check IS wireable now — it runs standalone
  (`bash fleet/checks/reconcile-board-pr-done.sh`, exit 0 clean / non-zero on RED) and is designed
  to be inserted into (a) fleet/preflight.sh:841 scan chain immediately after reconcile-merged.sh,
  (b) fleet/land.sh pre-merge pre-condition, and (c) fleet/foreman-cadence.sh `cadence` dispatch
  (the existing interval-gated timer, foreman-cadence.sh:87-102) — all three firing layers exist
  today. The wiring itself is owned by RECONCILE-WIRING (shared-file). This ticket only delivers
  the standalone check + test; it is NOT inert on merge because RECONCILE-WIRING depends_on it.
accept: |
  - fleet/checks/reconcile-board-pr-done.sh: standalone, composes reconcile-merged.sh's indexing;
    emits R-A (open ticket whose branch: matches a merged-but-not-done PR → RED, action:
    done.sh --merged-sha), R-B (merged PR matching no ticket branch AND touching no board/*.md →
    RED "create ticket or revert"), R-C (open ticket, stale branch, no open PR → WARN, not RED —
    liveness is judgment not drift). Exit non-zero on any R-A/R-B; exit 0 clean.
  - The AMBIGUOUS ladder is deterministic (branch → title/commit id → merged-sha ledger →
    NEEDS-MANUAL-ADJUDICATION). It NEVER auto-closes on ownership overlap without a unique signal.
  - fail-on-revert test (fleet/tests/reconcile-board-pr-done.test.sh), modeled on the existing
    fleet/tests/reconcile-merged.test.sh: (a) a merged PR with no ticket → R-B RED; (b) an open
    ticket whose branch: matches a merged PR → R-A RED, then done-marker present → GREEN;
    (c) an N>1-owner overlap with no branch/title/sha match → NEEDS-MANUAL-ADJUDICATION (RED),
    NOT auto-closed; revert the disambiguation ladder → the test goes RED.
  - Cite the stass-allie WLS-7 validation (implement-as-pattern is the sanctioned hand-roll:
    K8s/Terraform desired-vs-observed; no external tool reconciles Charon's own state).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Rig-only. Resolves the AMBIGUOUS exit-1 wedge (the class that wrote §1.1). Blast radius: every
  reconcile pass + every land that reads done-markers. drift-primitive: set-diff/bidirectional
  (KS29). No product change.
ds: |
  ## Dependencies & sequence
  Wave-1, no build prereq — independent of the other three reconcilers (disjoint owns:, each
  self-contained; parallelizable). RECONCILE-WIRING depends_on THIS (it wires the check into
  preflight/land/timer). Compose reconcile-merged.sh; do not rebuild PR/branch joining.
