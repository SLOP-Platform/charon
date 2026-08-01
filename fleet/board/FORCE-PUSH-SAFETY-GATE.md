repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: fix/force-push-safety-gate
depends_on:
owns: fleet/tests/force-push-safety.test.sh
substrate: N/A
substrate-novel: |
  REUSES what land-push.sh already does. `push-verify` already proves the post-state with
  `git ls-remote`, and the non-fast-forward refusal already caught the one real near-miss. The
  novel slice is making --force PROVE it destroys nothing BEFORE pushing, instead of relying on
  the operator's judgement. Nothing new is invented — one precondition on an existing flag.
serial_justified: |
  One precondition on one flag plus its proof.
source: |
  Operator, 2026-08-01: "we need to be VERY careful whenever you use --force — you need to
  VALIDATE you are not destroying work in a mechanized gate way."
note: |
  ## THE INCIDENT THAT MOTIVATES THIS (measured, same session)
  A manager used `land-push.sh --force` **19 times** to rescue stranded branches. Each was
  justified by reasoning ("master validates green; the RED is stale history the branch did not
  cause"). That reasoning was correct 19 times.

  **On the 20th it was WRONG and would have destroyed work.**
  `fix/shared-namespace-contention`:
    - LOCAL had 24 commits — all of them MASTER history (board-hygiene commits + merges); the
      worktree HEAD had drifted onto master content.
    - REMOTE had 1 commit — `63ece1f`, the ONLY copy of the real fix: **+905 lines** across
      `claim-jedi-name.sh`, `spawn-worker.sh`, and two test suites.
    - `--force` would have replaced the real work with master commits.
  It was stopped ONLY because the push was non-fast-forward and git refused. **The safety came
  from an accident of history shape, not from a check.** A fast-forward-shaped overwrite of real
  work would have gone straight through.

  ## THE RULE
  `--force` must PROVE it destroys nothing before pushing. Concretely: compute what exists on the
  remote ref and NOT in the local history being pushed (`git rev-list <local>..<remote>`).
    - **count == 0** -> nothing unique on the remote; force is safe; proceed.
    - **count > 0**  -> REFUSE by default. The remote holds commits this push would erase. Print
      them (sha + subject + diffstat) so the operator sees exactly what is at stake.
  An override for the genuine "I truly mean to discard that" case must be a SEPARATE, louder flag
  than `--force`, and must name what is being discarded in its own invocation.

  ## WHY THIS IS NOT JUST "BE CAREFUL"
  Careful is what produced 19 correct calls and 1 near-catastrophe. The failure mode is that the
  reasoning ("the RED is stale, the branch is fine") is about the BOARD, while the risk is about
  the REMOTE — two different things that happened to correlate 19 times. A gate does not need the
  operator to notice the difference. [[investigate-and-backup-before-data-loss]]

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline, fixture repo with a real remote (file:// bare repo is fine):
    a. **Reproduce the near-miss**: remote has 1 commit absent from local; `--force` is REFUSED
       and the commit is NAMED. Revert the check -> RED. This is the case that nearly cost 905 lines.
    b. remote has nothing unique -> `--force` proceeds exactly as today (ANTI-OVER-BLOCK; the 19
       legitimate rescues must still work, or this gate makes stranded work unrecoverable).
    c. the explicit discard override DOES proceed, and names what it discarded.
    d. the refusal message shows sha + subject + diffstat of every commit that would be lost —
       enough to decide without further digging.
    e. a normal non-force push is unaffected.
  Then dogfood: run against `fix/shared-namespace-contention` and show it refuses.

D&S — Deps & Sequence:
  - `fleet/land-push.sh` is owned by BRANCH-GATE-DIFF-SCOPE (MERGED 2026-08-01 as PR #338), so
    that contention is resolved. Confirm no live owner before editing; if one appears, sequence.
