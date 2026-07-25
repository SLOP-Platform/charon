repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 2
branch: feat/droid-lifecycle-reap
owns: fleet/fleet-droid.sh, fleet/reap-orphans.sh, fleet/tests/test_droid_reap.sh, fleet/foreman.sh
serial_justified: One cohesive droid-lifecycle safety change — the cleanup path + its out-of-band reaper + the shared preserve-committed-work guard all touch the same claim/worktree invariant; splitting orphans the contract.
depends_on: FLEET-DEMAND-DRIVEN-ROUTING, TICKET-MAP-GATE
real-dep: both edit fleet/fleet-droid.sh (FLEET-DEMAND rewrites 131 lines of the claim/resolve path); LIFECYCLE-REAP must sequence onto FLEET-DEMAND's LANDED version to avoid clobbering it.
real-dep: TICKET-MAP-GATE also edits fleet/fleet-droid.sh (a ten-line guard-branch anchor at :375, before p0_worktree_setup at :408) and is ALREADY BUILT+PUSHED at b784de1; merge order = built work anchors first, so LIFECYCLE-REAP sequences onto its LANDED version rather than clobbering the dispatch-time lease gate. Added 2026-07-24 with TICKET-MAP-GATE's boarding.
dep-kind: build
work_class_note: lifecycle-safety + data-safety; treat as money-adjacent (a bad reaper deletes work).
note: |
  OBSERVED 2026-07-16 (manager session): a frontier tab was Ctrl-C'd / terminal-closed. Its claim
  record (frontier-11931) PERSISTED and its worktree PERSISTED — the in-process `cleanup` trap
  (fleet-droid.sh:164-168) either didn't fire (SIGKILL / terminal-close bypasses a bash trap) or
  fired but never removes the worktree. Consequences:
    1. THUNDERING-HERD CHURN: with one hot claimable ticket + many idle same-tier tabs, each re-claims
       the same ticket; a dead droid's orphaned worktree then makes every subsequent `git worktree add`
       fail on the existing path -> claim-release churn (looked like "3 tabs on one ticket"; claiming is
       actually atomic — 1 record, 1 worktree — but the CHURN is real).
    2. STALE-CLAIM STARVATION: a SIGKILL-orphaned claim blocks the ticket forever (no in-process trap to
       release it) until a manager hand-releases it.
    3. DATA-LOSS TRAP: manually cleaning an orphaned worktree/branch is dangerous — a Claude session in
       this very session `git branch -D`'d a branch that had 2 committed work commits (recovered by SHA).
       Any automated cleanup MUST preserve committed work.
    4. **SEVERITY-P0 — WORKTREE-CREATE FORCE-RESETS AN EXISTING BRANCH:** fleet-droid.sh's worktree
       creation recreates the ticket branch from origin/master (reflog: "Created from origin/master",
       equivalent to `git worktree add -B <branch> origin/master`). If that branch ALREADY EXISTS with
       unmerged commits (e.g. a prior droid's completed-but-unlanded work, or a manager mid-land rebase),
       the `-B`/recreate SILENTLY DISCARDS those commits. Observed twice this session on
       FLEET-DEMAND-DRIVEN-ROUTING (the switchboard work + auth fix), recovered by SHA both times. This is
       the most dangerous variant: NO human error needed — a routine re-claim destroys unmerged work.
accept: |
  - `cleanup()` (fleet-droid.sh) removes the ticket's worktree on stand-down, but NEVER with blind
    `--force` over unsaved work: commit-or-stash any uncommitted changes first; committed work stays on
    the branch (worktree removal keeps the branch). A branch with `origin/master..HEAD` commits is NEVER
    deleted by cleanup.
  - NEW `fleet/reap-orphans.sh`: scans `state/claims/*`, parses the owning droid PID from the `tier-<pid>`
    owner, and for any claim whose PID is DEAD (`kill -0` fails) releases the claim AND cleans its
    orphaned worktree — PRESERVING any branch that has unique commits (mark it submitted for manager land
    instead of dropping it). Idempotent; safe to run while live droids hold other claims.
  - Reaper is WIRED into foreman (cadence + SessionStart + post-stand-down trigger, per
    dynamic-tools-never-on-demand) — not a manual on-demand step.
  - fail-on-revert test `fleet/tests/test_droid_reap.sh`: (a) a dead-PID claim + orphaned worktree whose
    branch has a committed change -> reaper releases the claim, removes the worktree, and the branch's
    commit SURVIVES + ticket ends up submitted (not lost); (b) a LIVE-PID claim is left untouched.
  - **P0 (consequence #4): the worktree-creation path MUST NOT force-recreate/reset a branch that already
    exists with unmerged commits.** Before creating a worktree, if the ticket branch exists and has
    `origin/master..<branch>` commits, REUSE it (check it out into the worktree) rather than `-B`-resetting
    it from origin/master; if it must rebase, do so non-destructively and never drop commits. fail-on-revert
    test: a ticket branch pre-seeded with a commit -> a re-claim's worktree creation PRESERVES that commit.
  - `charon.cli gate` / rig gate GREEN.
scope: |
  Root-cause fix for the claim-release churn + SIGKILL-orphan starvation + the data-loss footgun the
  manager hit this session. Blast radius: every droid's lifecycle + work preservation — adversarial
  review REQUIRED before land (data-safety). Build-rig only (no product change).
ds: Now (rig-only, disjoint from product). High-value: unblocks reliable multi-tab operation.
