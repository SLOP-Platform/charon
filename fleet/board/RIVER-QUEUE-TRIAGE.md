repo: charon-private
tier: strong
priority: 1
difficulty: 2
work_class: design-review
branch: docs/river-queue-triage
owns: docs/review-log/RIVER-QUEUE-TRIAGE.md
depends_on:
dep-kind:
work_class_note: design-review — read-only triage of an undocumented running service, feeding the
  durable-queue decision. It writes a review-log fragment and an EVAL-REGISTRY row, no product code.
note: |
  ## AN UNDOCUMENTED SERVICE IS RUNNING IN PRODUCTION
  Found 2026-08-04 while checking deployment state: a container named **`river-pg`
  (postgres:16)** has been UP on the gateway host since **2026-08-01** — created 3 days before it
  was noticed, by nobody-knows-who, and it appears in no handoff, no ticket, and no registry row.

  River is a **Postgres-backed durable work queue for Go**. That is not a coincidence: it is
  exactly the role LANE-C AXIS 2 category #1 says was NEVER SCORED. So somebody very likely started
  a durable-queue trial and dropped it — the D-007 pattern (research starts, nothing is filed).

  ## WHY THIS MATTERS MORE THAN A STRAY CONTAINER
  Three open decisions are all waiting on the durable-queue question:
    - **LANE-C AXIS 2** — the durable-queue role is its HIGHEST-priority unexecuted trial, and the
      ~6,000-LOC deletion target (work-lease.sh + lease-enqueue.sh + faktory/ + board-lock.sh +
      reconcile-stale-claims.sh + branch-reaper.sh + product engine/).
    - **D-008a** — explicitly BLOCKS the Go supervisor until the queue question is answered, because
      "if an engine is adopted, THE ENGINE IS THE SUPERVISOR".
    - **TAB-RELIABILITY** (operator-set HIGH priority) — inherits that same blocker.
  Answering "what is river-pg and did someone already trial it?" is therefore cheap and unblocks
  three things at once. Do it BEFORE scoring candidates from scratch.

  ## SCOPE — READ-ONLY TRIAGE, NOT AN ADOPTION
  1. Identify it: who created it, what (if anything) connects to it, whether it holds real data or
     is an empty scaffold, and whether any Go code in this estate imports River.
  2. Search the estate for an abandoned River trial — branches, worktrees, review-log fragments,
     EVAL-REGISTRY rows.
  3. **Decide and RECORD one of: (a) it is a live trial worth resuming — file the registry row it
     never got; (b) it is abandoned scaffolding — say so and STOP IT, do not leave an undocumented
     service running on the box that also runs the gateway; (c) it belongs to something else
     entirely — document what.**
  4. Feed the result into the LANE-C AXIS 2 durable-queue scoring (Restate / DBOS / Hatchet / River
     / Temporal / procrastinate) so that trial starts from evidence rather than a blank page.

  ⛔ DO NOT ADOPT ANYTHING FROM THIS TICKET. Per D-002 an adoption needs an EXECUTED trial with both
  sides at full strength (L6) and a report of what adopting DELETES (L2). This ticket only
  establishes what is already there.

  ACCEPTANCE: the review-log fragment answers "what is river-pg, who started it, is anything using
  it, and is it kept or stopped" with evidence, and either a filed EVAL-REGISTRY row or an explicit
  statement that none is warranted yet.
