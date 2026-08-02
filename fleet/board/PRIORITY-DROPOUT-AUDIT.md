repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/priority-dropout-audit
depends_on:
owns: fleet/state/PRIORITY-DROPOUT-AUDIT.md, docs/review-log/PRIORITY-DROPOUT-AUDIT.md
serial_justified: |
  One reconciliation across one pair of sources. Parallel lanes would each build a different
  notion of "on the list" and disagree, which is the defect under audit.
substrate: N/A
substrate-novel: |
  Nothing is adopted by this ticket - it is a read-only audit over THIS RIG'S OWN state, and no
  external tool can answer "which of our work items fell off our own list". ADOPT-FIRST applies to
  the FIX that follows, and the audit's own done contract (see the TOOL QUESTION in note:) forces
  that evaluation across the four tools we ALREADY own - validate_board.sh, stranded-work.sh,
  report.sh/ROADMAP.tsv and pending.sh - with a written rejection reason for each, and forbids
  proposing a new script unless every one is shown unsuitable. So the adopt-first discipline is
  enforced INSIDE the deliverable rather than skipped here. The novel slice is the reconciliation
  predicate itself - "live in git, absent from the list" - which no existing check computes.
execution: |
  Off-Claude. AUDIT lane - measure and report. Wire NOTHING in this ticket; the wiring is a
  follow-up sized by what the audit finds.
source: |
  MEASURED 2026-08-02. SHARED-NAMESPACE-CONTENTION is CLAIMED, carries 25 commits ahead of its
  remote (the largest unpushed body on the box) and is push-blocked by a gate defect - and it is
  absent from BOTH the numbered 1-16 priority queue in fleet/state/PRIORITY-TODO.md AND from
  fleet/state/ROADMAP.tsv. It appears only in a superseded 2026-08-01 section and as operator
  action #25. When the queue was rewritten on 2026-08-02 it did not carry forward. Operator -
  "one thing that keeps happening is that sessions get side-tracked and work doesn't get done ...
  you have to not let work get dropped and goals go stale."
note: |
  ## THE CLASS - "SILENTLY FELL OFF THE LIST"
  Not work that FAILED, and not work that was DEPRIORITISED on purpose. Work that was real, often
  in flight, and simply stopped being represented in the list the next session reads. It then
  cannot be scheduled, cannot be reported, and is discovered only by accident - which is exactly
  how SHARED-NAMESPACE-CONTENTION surfaced.

  ## WHY IT RECURS, MECHANICALLY
  There are at least FOUR competing "the list" surfaces and NOTHING reconciles them -
    1. `fleet/state/PRIORITY-TODO.md` - hand-authored, REWRITTEN each session. A rewrite is a
       lossy copy; anything not re-typed is silently gone. This is the proximate cause.
    2. `fleet/state/ROADMAP.tsv` - the canonical machine list behind `fleet/report.sh`.
    3. `fleet/board/*.md` + `fleet/state/claims|submitted|done` - the actual live work.
    4. `fleet/pending.sh` - operator actions only.
  A ticket can be LIVE and CLAIMED in (3) while absent from (1) and (2). Nothing detects that.

  ## FIND EVERY INSTANCE - this is the audit half
  Enumerate, do not sample. For EVERY board ticket, and every branch with unlanded commits -
  a. Is it in `ROADMAP.tsv`? Report every live/claimed/submitted ticket that is NOT.
  b. Is it in the current `PRIORITY-TODO.md` queue? Report every one that is NOT, and separate
     DELIBERATELY-parked from SILENTLY-dropped - a parked item has a stated reason; a dropped one
     has none. Do not conflate them; the whole point is to find the ones with no reason.
  c. Inverse direction - every `ROADMAP.tsv` row that is not `done` and has NO board ticket. A
     roadmap row with no ticket is a goal nobody can claim.
  d. Cross-check against work that EXISTS on disk - branches with unlanded commits, entries in
     `state/submitted/`, and `state/needs-push/` markers whose ticket appears on no list.
  e. For each finding, state WHEN it fell off if determinable (`git log` the two list files) - a
     drop that survived N session rewrites is worse than one that happened today.

  ## THE TOOL QUESTION - this is the half that stops it recurring
  Answer explicitly - which EXISTING tool should be wired or extended so this cannot recur?
  Evaluate at minimum, and reject with a reason rather than silently -
    - `fleet/validate_board.sh` - already walks every ticket and already emits RED findings.
      LEADING CANDIDATE - a board-to-roadmap reconciliation is a new predicate in an existing
      walker, and it already runs in the session flow.
    - `fleet/checks/stranded-work.sh` - already runs on a proven cron cadence and already reports
      work-loss shapes. "On disk but on no list" is arguably a sixth loss shape.
    - `fleet/report.sh` / `ROADMAP.tsv` - could render an UNRECONCILED section.
    - `fleet/pending.sh` - escalation surface once something is detected, not the detector.
  Do NOT propose a new script unless every one of these is shown unsuitable. A fifth list surface
  would ADD to the very problem this ticket is about [[no-rig-as-product-adopt-dont-handroll]].

  ## THE DEEPER FIX TO ASSESS
  State plainly whether `PRIORITY-TODO.md` should stop being hand-rewritten at all and instead be
  GENERATED from `ROADMAP.tsv` + board state, leaving only the human commentary hand-written.
  A hand-copied list will always be lossy; the recurring defect may be the format itself, not any
  individual session's diligence. Give a recommendation with gains and losses, not a preference.
accept: |
  DELIVERABLE `fleet/state/PRIORITY-DROPOUT-AUDIT.md` containing -
  a. A COMPLETE table of dropped items - id, where it still exists, where it is missing, live
     state (claimed/submitted/unlanded commits), and when it fell off if determinable.
  b. A count, stated plainly. If SHARED-NAMESPACE-CONTENTION is the only instance, say so - a
     one-instance class is a very different problem from a twenty-instance one, and reporting a
     scary number that is not real is its own failure [[document-model-self-report-lies]].
  c. Silently-dropped separated from deliberately-parked, with the evidence that distinguishes them.
  d. A TOOL VERDICT - the ONE existing tool to extend, the exact predicate to add, and a rejection
     reason for each other candidate. Include the shape of the fail-on-revert proof.
  e. A recommendation on generating PRIORITY-TODO.md from ROADMAP.tsv, with gains and losses.
  f. Every number reproduced by a command quoted in the report [[confirm-dont-trust-documentation]].
scope: |
  Read-only audit plus a written verdict. Wires nothing, edits no list, changes no tool. The
  follow-up wiring ticket is sized from finding (d).

## Dependencies & Sequence

- **depends_on: none.** Reads board, roadmap, git and state markers - all present.
- **Runs in PARALLEL with everything.** Read-only; owns two new files named after itself; contends
  with no live ticket.
- Its finding (d) SIZES a follow-up wiring ticket. Do not pre-mint that ticket - the audit decides
  whether it is one predicate in `validate_board.sh` or something larger.
- Related but distinct - `fleet/checks/stranded-work.sh` covers work that exists on disk and is
  unrepresented in GIT. This covers work that exists in GIT and is unrepresented in the LIST.
