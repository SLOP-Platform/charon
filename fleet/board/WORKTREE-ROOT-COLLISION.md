repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/worktree-root-collision
depends_on:
owns: fleet/repo-registry.sh, fleet/checks/worktree-root-consistency.sh, fleet/tests/worktree-root-consistency.test.sh
serial_justified: |
  ONE resolver, ONE root convention. Two lanes each picking a root is literally the defect.
substrate: N/A
substrate-novel: |
  Nothing to adopt — `git worktree` is the adopted substrate and works correctly. The bug is OUR
  path resolution choosing a root that belongs to a different repo, plus the absence of any check
  that a ticket's worktree lives under the root matching its `repo:` field. That reconciliation
  is the novel slice.
execution: |
  Off-Claude, SG droid tab. BARE model ids only.
source: |
  Diagnosed 2026-08-02 as a cause of ZERO-COMMIT-SPIN, then re-observed causing a SECOND distinct
  failure the same day. The manager said it would mint this ticket roughly SIX times across the
  session and never did — recorded because the dropped-commitment pattern is itself the failure
  the operator called out.
note: |
  ## THE DEFECT — two roots, and tickets land under the wrong one
  Worktrees exist under BOTH conventions simultaneously:
    /home/stack/code/charon-fleet-<ID>      (what repo-registry.sh resolves)
    /home/stack/charon-wt/<ID>              (legacy; 10 PRODUCT worktrees live here)
    /home/stack/charon-private-wt/<ID>      (rig)
  TWO separate failures were MEASURED from this on 2026-08-02:

  **(a) Permanent claim spin.** The launcher resolved
  `/home/stack/code/charon-fleet-SPEND-METRIC-TRUSTWORTHY` while the branch was ALREADY checked
  out at `/home/stack/charon-wt/SPEND-METRIC-TRUSTWORTHY`. git refuses
  (`fatal: '<branch>' is already used by worktree at ...`), `p0_worktree_setup` FATALs, the claim
  is released and loop-guard counts a zero-commit spin. **It never self-clears** — every retry
  reproduces it identically, so the ticket is quarantined for a reason that is not the model's
  fault. 13 FATALs across 3 tickets. This is a root cause of ZERO-COMMIT-SPIN.

  **(b) Rig files committed into the PRODUCT repo.** `FT-LIMITS-GROQ-RECONCILE` and
  `MISSING-CLASS-DETECTORS` are both `repo: charon-private`, but their worktrees were created
  under the PRODUCT root — so `fleet/checks/class-detectors.sh` and
  `fleet/state/FREE-TIER-LIMITS.tsv` were staged inside `/home/stack/code/charon`. The product's
  boundary gate correctly REFUSED the commit (`rig path "fleet/"`), which is the only reason it
  was caught. The work had to be preserved as patches under
  `fleet/state/wip-backup-20260802-misplaced/`.

  ## WHY IT KEEPS BITING
  Nothing checks that a ticket's worktree root MATCHES its `repo:` field, and nothing detects a
  branch already checked out at a different root before attempting to create one. The existing
  worktree-leak guard covers a DIFFERENT shape ("do not work in a repo ROOT") and does not see
  this at all.

  ## WHAT TO BUILD
  1. **ONE canonical root per repo**, derived from `repo:` in `repo-registry.sh`. Decide the
     convention and state it. Legacy-root worktrees are MIGRATED or explicitly registered — not
     left to race.
  2. **Pre-create check:** before `worktree add`, ask whether the branch is already checked out
     ANYWHERE (`git worktree list --porcelain`). If it is, REUSE that worktree if its root is
     correct, or FAIL LOUD naming both paths if it is not. Never FATAL with a message that reads
     like a model failure.
  3. **Root/repo consistency check** (`fleet/checks/worktree-root-consistency.sh`): every live
     worktree's root must match its ticket's `repo:`. Report mismatches with both paths.
  4. **Classify (a) as INFRA to loop-guard.** A worktree-create FATAL must pass
     `--reason launcher-refused` so it never counts toward quarantine — it is not model quality.
     (`LOOP-GUARD-REASON-WIRE` landed the wiring; confirm this call site uses it.)
accept: |
  a. One canonical root per repo, documented, with existing legacy worktrees migrated or
     registered. State which and why.
  b. RED-PROOF, each SEEN to fail then pass: a branch already checked out at another root is
     REUSED-or-refused-loudly, never FATAL-and-quarantine; a worktree whose root mismatches its
     ticket's `repo:` is reported.
  c. ANTI-FALSE-POSITIVE: a correctly-rooted worktree set yields ZERO findings.
  d. A worktree-create failure records loop-guard with `--reason launcher-refused` — prove the
     ticket is NOT quarantined by it.
  e. Suite registered in the LITERAL `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh`.
  f. Triage `fleet/state/wip-backup-20260802-misplaced/` — land those two patches into their
     CORRECT repo or close with evidence.
  g. `bash fleet/validate_board.sh` GREEN.
scope: |
  Worktree root resolution, the pre-create check, the consistency check, and the loop-guard
  reason at that call site. Does NOT change `git worktree` usage elsewhere or the existing
  repo-root leak guard in `spawn-worker.sh`.

## Dependencies & Sequence

- **depends_on: none.**
- Removes a CAUSE of `ZERO-COMMIT-SPIN`; pairs with `BOARD-VIEW-MISMATCH` (which makes exclusion
  visible). Either order.
- Related but distinct from `WORKTREE-LEAK-TUI-PATH` (working in a repo ROOT) — that guard
  landed at `c9aa586` and does not cover this shape.
