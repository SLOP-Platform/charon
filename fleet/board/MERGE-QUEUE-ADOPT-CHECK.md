repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: design-review
branch: eval/merge-queue-adopt-check
depends_on:
owns: fleet/state/MERGE-QUEUE-ADOPT-CHECK.md, docs/review-log/MERGE-QUEUE-ADOPT-CHECK.md
serial_justified: |
  One question against one repo's settings. Nothing to parallelise, and two lanes would race on
  the same repo-settings reads.
substrate: |
  This ticket IS the substrate check, and it is the ADOPT-FIRST gate standing in front of a
  proposed hand-rolled PR-refresh cadence. GitHub ships a native MERGE QUEUE and a native
  auto-merge, both of which already do the two mechanical things the cadence would otherwise
  hand-roll — refresh a stale base against the target branch, and land the PR once required
  checks pass. Mergify is the equivalent third-party product. If native merge queue works on
  these repos, most of the proposed cadence must NOT be built at all; it shrinks to a triage
  report. Determining that BEFORE writing the cadence is the whole point of this ticket.
execution: |
  Off-Claude. EVAL lane — measure and report. Wire NOTHING, enable NOTHING, change no repo
  setting. The deliverable is a verdict with evidence, not a configuration change.
source: |
  Handoff and prior sessions assert "auto-merge won't enable" with NO recorded reason
  [[confirm-dont-trust-documentation]]. An unexamined blocker is not a finding. A prior instance
  of skipping exactly this check produced fleet/review-pool.sh — 383 lines plus a 451-line suite,
  merged via PR #250, which has never run in CI and whose queue was never populated. Under
  ADOPT-FIRST, hand-rolling carries significant negative weight and a REJECT must PROVE no sane
  adopt option exists.
note: |
  ## THE QUESTION, STATED PRECISELY
  Can GitHub's native merge queue (and/or native auto-merge) do the MECHANICAL half of draft-PR
  drain on `Nnyan/charon-private` and `Nnyan/charon`? The mechanical half is exactly two things -
  refresh a stale base, and land when required checks pass. It explicitly EXCLUDES all judgement
  (review verdicts, closing superseded drafts), which stays with the reviewer and the manager per
  the standing decision in `fleet/board/PR-QUEUE-DRIVE.md`.

  ## WHAT TO ACTUALLY CHECK — each is a command, not an opinion
  1. Is auto-merge ALLOWED on each repo?
     `gh api repos/Nnyan/charon-private --jq '.allow_auto_merge, .allow_update_branch'`
     If false, that is the whole answer to "won't enable" and it is a one-flag fix, not a blocker.
  2. Is a merge queue available and configured on the default branch? Read the branch-protection
     and rulesets endpoints. Merge queue requires a ruleset or protection rule on `master`.
  3. Does the plan/visibility tier permit merge queue? Merge queue availability differs for
     private repos on some plans. `charon-private` is PRIVATE and `charon` is PUBLIC, so the two
     repos MAY differ — answer for BOTH, do not generalise from one.
  4. What are the REQUIRED checks today? A merge queue with no required checks lands unverified
     work — that is strictly worse than the current manual gate. Enumerate them.
  5. Does merge queue interact safely with SQUASH merging? This repo squash-merges, which is why
     `git merge-base --is-ancestor` is a WRONG merged-ness test here [[F3 measurement traps]].

  ## THE DISQUALIFIERS — any ONE of these means DO NOT ADOPT, and say so plainly
  - It would land a PR without the two review checks the standing decision requires (grep the
    diff for the CLAIMED MECHANISM; run the suite with the change REVERTED).
  - It cannot be restricted to PRs that a human/reviewer has already approved.
  - It requires giving a third party write access to a PUBLIC repo.
  - It cannot be turned off quickly if it starts landing wrong work.

  ## THE ANTI-REQUIREMENT
  Do NOT enable anything. A verdict that silently switches on a merge queue is a change to the
  landing path — the highest blast-radius surface in the rig — made by an eval lane that was
  asked only to look. Report, do not wire.
accept: |
  DELIVERABLE `fleet/state/MERGE-QUEUE-ADOPT-CHECK.md`, one section per repo, containing:
  a. The literal output of each of the 5 checks above, per repo, with the command that produced it.
  b. A VERDICT for the mechanical half - ADOPT NATIVE / ADOPT MERGIFY / HAND-ROLL, and if
     HAND-ROLL, which specific disqualifier forced it. "Ours already exists" is NOT a reason.
  c. The one-line answer to "why won't auto-merge enable" - the actual cause, or the statement
     that it DOES enable and the claim was stale.
  d. If ADOPT - the exact settings that would need to change, listed but NOT applied, plus the
     rollback for each.
  e. If HAND-ROLL - the MINIMAL residual cadence that native tooling cannot cover, so the build
     that follows is as small as the evidence allows.
scope: |
  Read-only investigation of repo settings, branch protection, rulesets and required checks.
  Changes no setting, enables no feature, writes no cadence, and touches no PR.

## Dependencies & Sequence

- **depends_on: none.** Reads live repo settings only.
- **BLOCKS the PR-draft triage cadence.** Operator-decided 2026-08-02 (option B2): answer this
  BEFORE building any cadence, precisely so we do not hand-roll around adopted substrate.
- Narrower than and complementary to `PR-AUTOMATION-EVAL`, which scores pr-agent/aider for the
  REVIEW half. This ticket covers only the MECHANICAL half. Disjoint owns; either order; both P0.
- Uses REST endpoints, not GraphQL — REST is the free bucket [[F5]].
