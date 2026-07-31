repo: charon-private
tier: strong
difficulty: 3
priority: 0
work_class: rig-meta
branch: feat/ticket-lifecycle-canary
owns: fleet/tests/ticket-lifecycle-canary.test.sh
real-dep: STUCK-TICKET-LOUD-VISIBILITY owns fleet/checks/stuck-ticket-loud.sh, which this canary's
  "unclaimable-P0 -> RED" seed depends on existing and being callable; the other two composed
  checks (fleet/checks/gate-parity.sh, fleet/reconcile-merged.sh) are already DONE/on master
  (GATE-PARITY-LAND-VS-LAUNCH is archived+done) so they need no depends_on entry.
real-dep: PLANE-CANARY-REGISTRY seeds this plane's registry row at the exact
  fleet/tests/ticket-lifecycle-canary.test.sh path this ticket owns — a genuine build prereq.
depends_on: PLANE-CANARY-REGISTRY, STUCK-TICKET-LOUD-VISIBILITY
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md Phase 3 "P2 control/ticket-lifecycle" spec +
  "PROPOSED TICKET LIST" row 6.
note: |
  GAP plane (design doc Phase 3, #2) — partial slices exist, no FULL hermetic lifecycle canary
  composes them. This ticket COMPOSES three existing/landing pieces into one
  mint -> claim -> build -> land -> retire canary; it does NOT re-own their logic:
  fleet/checks/gate-parity.sh (land >= launch gate, DONE/archived — GATE-PARITY-LAND-VS-LAUNCH),
  fleet/reconcile-merged.sh (merged-PR -> board auto-done by owns-overlap, already on master), and
  fleet/checks/stuck-ticket-loud.sh (STUCK-TICKET-LOUD-VISIBILITY, live, this ticket's real
  build-dep). Throwaway board + fake merged-PR-set fixtures, fully hermetic — no live board/PR
  state is ever touched by the dogfood. [[gates-must-actually-run]]
  [[detection-ticketed-never-built]]
accept: |
  - fleet/tests/ticket-lifecycle-canary.test.sh: builds a throwaway fixture board (a handful of
    fake .md tickets in a scratch dir) + a fake merged-PR set, then seeds three faults in turn:
      (a) a splittable-serial ticket with no serial_justified field, claimed and "launched" ->
          assert fleet/checks/gate-parity.sh (reused, not reimplemented) reports RED (the
          land >= launch violation it already detects).
      (b) a fixture branch marked merged in the fake PR set but never retired off the fixture
          board -> assert fleet/reconcile-merged.sh (reused) flags it RED / does not silently
          auto-close.
      (c) an unclaimable P0 fixture ticket (all deps dead / orphaned residue) -> assert
          fleet/checks/stuck-ticket-loud.sh (reused, from STUCK-TICKET-LOUD-VISIBILITY) fires
          LOUD, not silent.
    Correct each fixture in turn -> each composed check goes GREEN. This is the composition
    dogfood_test registered for the "lifecycle" plane (row already seeded by
    PLANE-CANARY-REGISTRY at this exact path).
  - fail-on-revert test: for each of (a)/(b)/(c), revert the seeded fix -> the corresponding
    composed check goes RED again (proving each leg is genuinely wired into this canary, not
    just imported-and-ignored).
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
  - ADVERSARIAL REVIEW REQUIRED before merge (reviewer != builder) — composes
    gate-parity.sh/reconcile-merged.sh/stuck-ticket-loud.sh into the ticket-lifecycle plane's
    acceptance proof; a false GREEN would mean the whole board's land/claim integrity looks
    proven when a composed leg is actually broken. Manager gates, PR does NOT merge on the
    builder's self-report.
scope: |
  Composition + fault-seed-proof only. Does not modify gate-parity.sh, reconcile-merged.sh, or
  stuck-ticket-loud.sh — reuses all three as-is. No new lifecycle-detection logic is invented
  here; if a genuine new detection gap is found while composing, it is fed back as a fold-in to
  the owning ticket (STUCK-TICKET-LOUD-VISIBILITY), not hand-rolled here.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-REGISTRY (registry row) and STUCK-TICKET-LOUD-VISIBILITY (real build
  prereq for seed (c) — that check does not exist on master yet). gate-parity.sh and
  reconcile-merged.sh are already done/on-master, no dep needed for them. Disjoint owns from
  every other gap-canary ticket in this wave — parallelizable once its one live prereq lands.
