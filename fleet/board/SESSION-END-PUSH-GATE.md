repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
priority: 2
branch: feat/session-end-push-gate
depends_on: HANDOFF-GOTCHA-VERIFIABLE
real-dep: HANDOFF-GOTCHA-VERIFIABLE — shared fleet/end-session.sh surface. That branch
  (fix/handoff-gotcha-verifiable) is BUILT and one commit from landing; it adds 3 lines to
  end-session.sh's generated handoff FIXTURE so the fixture still satisfies handoff-check.sh's now
  non-vacuous [claims] gate. This ticket rewrites end-session.sh's CLOSE-REFUSAL logic — a different
  function, so the two edits COMPOSE in this order but would clobber in the other. Merge-order only;
  costs no schedule time (this ticket is not started). Added 2026-07-24 by the board repair that
  ticketed that branch.
owns: fleet/end-session.sh, fleet/tests/end-session-push.test.sh
accept: |
  GAP found 2026-07-15 (cere-junda): end-session.sh commits ONLY the handoff FILE and NEVER pushes or checks for unpushed
  work; handoff-check.sh doesn't check origin. Result: 6 session commits (doctrine/board/roadmap) sat LOCAL-ONLY while the
  handoff PASSED — a fresh next session pulling origin would have MISSED all of it (the stale-origin / strand-work disease this
  whole session fought). DO: extend end-session.sh to REFUSE to print CLOSED unless (a) the working tree is clean (ALL session
  work committed, not just the handoff) AND (b) local HEAD is not ahead of origin/master — push via the sanctioned land-push
  (autonomous-gated) or refuse LOUDLY with the exact command. Sibling of BASE-INTEGRITY-GATE (same unpushed-local disease, exit side).
  FAIL-ON-REVERT (fleet/tests/end-session-push.test.sh): a repo with an unpushed commit OR a dirty tree -> end-session REFUSES
  to close (revert the check -> closes with work stranded -> RED).
investigate-first: |
  Operator directive (cere-junda): the next session INVESTIGATES before wiring auto-push — scope the edge cases first:
  (1) only auto-push housekeeping/handoff commits on the base branch (master); NEVER auto-push unreviewed feature branches
      (those go through land.sh review). (2) On a DIVERGED base (origin ahead of local), REFUSE loudly — never force-push.
  (3) Gate the push on the AUTONOMOUS lever: lever ON -> push; lever OFF -> refuse with the exact copy-paste command.
  (4) Never push if the public-clean / secret-scan gate is red. Decide the push-vs-refuse policy, THEN wire it into end-session.sh.
