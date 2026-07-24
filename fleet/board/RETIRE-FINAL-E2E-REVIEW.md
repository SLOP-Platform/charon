repo: charon-private
tier: economy
difficulty: 1
priority: 0
work_class: rig-meta
branch: chore/retire-final-e2e-review
owns: fleet/board/FINAL-E2E-REVIEW.md
real-dep: PLANE-CANARY-WIRE is what actually makes the suite run+RED-surface on every PR and on
  a cadence — this ticket's retirement claim ("a green plane-canary run IS the replacement e2e")
  is only true once PLANE-CANARY-WIRE lands; a genuine correctness prereq, not a merge-order
  preference.
depends_on: PLANE-CANARY-WIRE
source: fleet/state/DESIGN-PLANE-CANARY-SUITE.md EXEC SUMMARY point 4 + "PROPOSED TICKET LIST"
  row 10 ("this suite subsumes the phantom FINAL-E2E-REVIEW").
note: |
  fleet/board/FINAL-E2E-REVIEW.md is a live, unbuilt one-shot capstone review ticket (depends_on
  DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT). The design doc's verdict: "a green plane-canary suite
  run IS the comprehensive, always-on e2e that the one-shot capstone review only pretended to
  be" — a single manual review, even a thorough one, proves the pipeline worked ONCE, at review
  time; a wired+scheduled plane-canary suite (PLANE-CANARY-WIRE, this ticket's dep) proves it on
  EVERY PR and on a cadence, forever. This ticket retires the phantom, it does not run the
  capstone review itself. KNOWN COLLISION (flagged, not mechanically enforceable by
  validate_board.sh's owns-check, since FINAL-E2E-REVIEW.md's own `owns:` names its OWN
  deliverable doc fleet/state/FINAL-E2E-REVIEW.md, not the board ticket file): if a droid claims
  fleet/board/FINAL-E2E-REVIEW.md and starts the old capstone review in parallel with this
  ticket, the manager must land THIS ticket's retirement first (or explicitly re-confirm the
  capstone is still wanted) before that work proceeds — surfaced here so it is not silently
  raced. [[preexisting-issues-fold-into-current-work]]
accept: |
  - fleet/board/FINAL-E2E-REVIEW.md: rewritten to `parked: true`, with a note explaining it is
    SUPERSEDED by the plane-canary suite (cite PLANE-CANARY-REGISTRY/-WIRE + the per-plane canary
    tickets by id) and pointing at a green `fleet/plane-canary.sh run --live && ... reconcile`
    run as the durable replacement acceptance proof. Do NOT delete the file (git history is the
    audit trail per EVAL-REGISTRY's own append-only convention) — park + annotate.
  - Its depends_on chain (DECOMPOSE-DEFAULT-GATE, MODEL-PREFLIGHT) is left untouched (those
    tickets' own status is out of scope here) — only FINAL-E2E-REVIEW.md's own parked/note fields
    change.
  - fail-on-revert test: N/A build-code (this is a board-doc-only ticket, no script/logic to
    revert-test) — instead, bash fleet/validate_board.sh's PARK-2 check
    ("parked-note-only" — a ticket parked via note text alone with no explicit `parked: true`
    field is a validator RED) is the mechanized proof this ticket did the park correctly: run
    validate_board.sh before AND after this edit and confirm no new PARK-* RED appears.
  - bash fleet/validate_board.sh GREEN (modulo pre-existing unrelated board state).
scope: |
  Board-hygiene retirement of one phantom ticket. Does not touch DECOMPOSE-DEFAULT-GATE,
  MODEL-PREFLIGHT, or any plane-canary build ticket's own files.
ds: |
  ## Dependencies & sequence
  depends_on PLANE-CANARY-WIRE (the suite must actually be wired+running before the capstone
  ticket it replaces can be honestly retired — retiring it earlier would be declaring victory
  before the replacement is real, the exact FINAL-E2E-REVIEW-phantom anti-pattern this whole
  suite exists to close). Last in the plane-canary wave's dependency graph.
