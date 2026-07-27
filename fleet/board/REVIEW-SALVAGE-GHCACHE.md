repo: charon-private
tier: strong
difficulty: 3
work_class: design-review
priority: 0
branch: review/review-salvage-ghcache
depends_on:
owns: fleet/handoff-notes/ADVREVIEW-SALVAGE-GHCACHE.md
prompt: /home/stack/charon-private/prompts/REVIEW-SALVAGE-GHCACHE.md
serial_justified: |
  ONE review batch producing ONE verdict file. Owns no code — the deliverable is a per-branch
  disposition so the operator can land or discard with evidence rather than guesswork.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. READ-ONLY.
source: |
  Landing sweeps 1-4, 2026-07-26: 50 branches triaged, 34 LAND-READY landed on executed-test
  evidence. These were flagged NEEDS-REVIEW precisely because triage could NOT establish that
  evidence. Batching them with the rest is how an unreviewed money-path commit reached master today.
note: |
  ## SCOPE — salvage/preflight-verify-merged-ghcache-wip (6 commits, 50 files, +443/-4173)
  salvage/preflight-verify-merged-ghcache-wip
## WHY THIS ONE IS ALONE AND P0
**4,173 deletions across 50 files.** That is by far the largest destructive diff in the unlanded set,
on a branch literally named `salvage/...-wip` — work-in-progress that was rescued, not finished.
Landing it blind could remove large amounts of live rig machinery.
**Establish FIRST whether those deletions are real or a diff artifact.** A branch far behind master
shows master's additions as deletions under a two-dot diff. Use the three-dot form and say plainly
which it is — that single question decides everything else.
accept: |
  DONE-CONTRACT:
  - A per-branch verdict (LAND / REWORK / ABANDON / UNSAFE-TO-JUDGE) with the evidence behind it.
  - For any LAND verdict: the tests you RAN and their exit codes. Claims from commit messages are
    not evidence.
  - For any branch adding a gate/check: an EXTERNAL break attempted, with the result.
  - Content-vs-ancestry stated correctly — a squash-merged branch reports unlanded commits forever.
  - NON-VACUOUS: fewer verdicts than branches assigned is incomplete.
  - READ-ONLY: no edits, commits, landings or deletions.
## Dependencies & sequence
- **Depends on: NOTHING.** Read-only; owns one report file. Runs fully parallel with the other
  review batches and with all other work.
- **Wave:** review lane, P0.
