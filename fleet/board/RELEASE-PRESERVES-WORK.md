repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: fix/release-preserves-work
depends_on:
owns: fleet/release.sh, fleet/tests/release-preserves-work.test.sh
substrate: N/A
substrate-novel: |
  REUSES the `fleet/state/needs-push/` mechanism that ALREADY EXISTS and already works —
  `INERT-INSTANCE-DETECT` is sitting in it right now with its claim correctly held and surfaced
  for landing. fleet-droid.sh already honours it ("committed-but-unlanded work — NOT re-running;
  keeping claim"). Nothing new is invented; `release.sh` simply never learned about it.
serial_justified: |
  One guard in an 11-line script plus its proof.
source: |
  Operator, 2026-08-01: multiple tabs doing the same work, and completed work left stranded —
  "NOT GOOD". Both symptoms trace to this one defect.
note: |
  ## THE DEFECT — RELEASE THROWS AWAY FINISHED WORK
  `fleet/release.sh` is 11 lines and drops the claim **unconditionally**. It never checks whether
  the branch has unlanded commits (`grep -nE "unlanded|rev-list|needs-push|commit|branch"` -> no
  hits).

  ## THE LOOP IT CREATES (this is the duplicate-work engine)
  1. Droid completes the work and COMMITS to its branch.
  2. It hits an owns/scope conflict at the end and self-releases per the brief
     ("if you hit a true blocker you cannot resolve: run release.sh").
  3. `release.sh` drops the claim. The commits stay on an unpushed branch.
  4. Ticket returns to **READY**.
  5. Another pool tab claims the SAME ticket and redoes the work from scratch.
  6. Repeat.

  Caught live 2026-08-01 — the second droid on SHARED-NAMESPACE-CONTENTION wrote:
  *"the prior droid also said this file was written ... My session just started."*
  Operator observed **3 tabs on SHARED-NAMESPACE-CONTENTION and 2 on LOOP-GUARD-REASON-WIRE**.
  Four tickets finished their work and reported READY: LOOP-GUARD-REASON-WIRE (1 commit),
  RETIRE-FINAL-E2E-REVIEW (2), SHARED-NAMESPACE-CONTENTION (1), DEADCODE-TOOLS-WIRE (1) —
  all with green gates and passing tests, none pushed.

  This burns model spend, wastes wall-clock, and risks two droids racing the same branch.

  ## THE FIX — RELEASE MUST NOT DISCARD COMMITTED WORK
  Before dropping a claim, `release.sh` checks the ticket's branch/worktree for unlanded commits
  or a dirty tree. If ANY exist:
    - do NOT drop the claim;
    - write `fleet/state/needs-push/<id>` (the existing marker fleet-droid.sh already honours);
    - print the exact recovery command loudly.
  If there is genuinely nothing to lose (no commits, clean tree), release as it does today —
  that path is correct and must keep working.

  **Fail-safe direction matters:** when the branch/worktree cannot be resolved, treat it as
  HAVING work and refuse to release. Losing a claim is cheap; losing finished work is not.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture repo:
    a. release on a ticket whose branch has >=1 unlanded commit -> claim RETAINED, needs-push
       marker written, recovery command printed. Revert the guard -> RED. **This is the case that
       cost four tickets.**
    b. release on a ticket with a DIRTY worktree but no commits -> also retained (uncommitted work
       is still work).
    c. release with genuinely nothing to lose -> claim dropped exactly as today (ANTI-OVER-BLOCK —
       do not turn every release into a permanent claim).
    d. unresolvable branch/worktree -> fail SAFE, refuse to release, say why.
    e. a ticket left in needs-push is NOT re-offered by claim.sh, so no second tab can redo it.
       This is the assertion that closes the duplicate-work loop — prove it.
  Then dogfood: run against the four real stranded tickets and show each retained.

## Dependencies & Sequence
  - Depends on: nothing. `release.sh` is uncontended.
  - Pairs with BRANCH-GATE-DIFF-SCOPE (that one makes stranded branches pushable again; this one
    stops work being stranded in the first place). Independent.

  ## BLAST RADIUS — WIRE BOTH ENDS OF needs-push (measured 2026-08-01)
  `needs-push` is already a real, honoured mechanism — but it leaks at both ends.

  **ALREADY WIRED (do not rebuild):** written by fleet-droid.sh (4 sites), submit.sh (4),
  leak-guard.sh, reap-orphans.sh (6), branch-reaper.sh, dark-work-check.sh. Surfaced by
  preflight.sh (16 refs), board.sh, status.sh, stranded-work.sh. Recovered by land-needs-push.sh.

  **MISSING WRITERS — in scope here:**
  - `release.sh` — the defect above.
  - **`land.sh` / `land-push.sh` on REFUSAL.** They refused four branches tonight and recorded
    NOTHING. A refused push is committed-but-unlanded work by definition; it must leave a
    needs-push marker so the work is tracked instead of relying on a human to remember.
    (Those files are contended — if editing them collides, SURFACE it and ticket it separately
    rather than reaching outside `owns:`.)

  **MISSING READERS — surface these, do not let them die at session end:**
  - **`fleet/handoff.sh` has ZERO needs-push references.** Anything in needs-push does not reach
    the next session. `INERT-INSTANCE-DETECT` is in needs-push RIGHT NOW and no handoff carries
    it. This is how committed work goes missing between sessions.
  - `fleet/report.sh` has zero — needs-push is absent from the canonical fleet report.
  Both are surfacing-only additions (read the marker dir, print it). If either file is contended,
  ticket it rather than colliding.
