repo: charon-private
tier: strong
difficulty: 2
priority: 1
work_class: rig-meta
branch: feat/stale-claim-reconcile
owns: fleet/reconcile-stale-claims.sh, fleet/tests/reconcile-stale-claims.test.sh
depends_on:
source: CLAIM-INTEGRITY-EVAL T2 (operator-approved 2026-07-24, eeth-koth). The 5 current stale claims are LIVE instances of leak #2/#3.
note: |
  MECHANIZE the stale-claim hygiene (not a one-off manual action). A reconciler that, for each file
  in state/claims/: (1) if the claim's droid PID is dead (reap-orphans.sh kill -0 semantics) AND the
  ticket's work is merged (done.sh merge-proof passes) → writes the terminal done marker; (2) if dead
  AND work is NOT merged (e.g. REJECTED / unpushed) → leaves the claim OR flags LOUD, never silently
  releases into a re-claimable void (that would CAUSE leak #3 on next pool start). Current live cases:
  KSF-VENDOR-GATES (HEAD 1e6d174, done once pushed+merged), FAKTORY-TRIAL (eval done),
  EGRESS-KEY-CANARY (REJECTED — needs rebuild, do NOT retire), RECONCILE-OWNS-TRACKED, REPO-DECL-CENTRAL.
  Run BEFORE CLAIM-LEASE-EXACTLY-ONCE lands so the Faktory migration starts from a clean board.
  See [[claim-integrity-no-reclaim-red-line]].
accept: |
  - Idempotent reconciler; dead-PID + merged → terminal marker; dead-PID + unmerged → HOLD + LOUD, never
    a bare release.
  - fail-on-revert: a claim whose work is unmerged is never released into a claimable state.
  - After a run on the current board, the 5 stale claims are each either retired-with-proof or
    HELD-with-reason (no silent void).
scope: |
  Stale-claim reconciliation tool + test. Interim class-fix until CLAIM-LEASE-EXACTLY-ONCE makes the
  whole marker scheme obsolete (ack = atomic retire). Cheap hygiene, no substrate.
ds: |
  ## Dependencies & sequence
  P1, no prereq. Sequence-FIRST (before FAKTORY-ADOPT / CLAIM-LEASE-EXACTLY-ONCE) to clean the board.
