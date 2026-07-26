repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: design/branch-sprawl-root-cause
depends_on:
owns: fleet/state/BRANCH-SPRAWL-ROOT-CAUSE.md
serial_justified: |
  ONE root-cause investigation producing ONE ruling. Owns no code deliberately: the fix is unknown
  until the cause is known, and every previous response to this problem has been another cleanup pass.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded sample: record into fleet/model-scorecard.tsv. One checkout, one agent — its OWN worktree.
source: |
  Operator directive 2026-07-26, immediately after the third large reap: "investigate why we have so
  many worktrees/branches that we are having to constantly reap."
note: |
  ## THE SYMPTOM WE KEEP TREATING
  Measured 2026-07-26 AFTER a reap that removed 27 product worktrees, 27 product branches, 6 rig
  branches and 5 rig worktrees:
    rig branches:      164
    product branches:   90
    rig worktrees:      57  (was 62)
    product worktrees:  16  (was 44)
  Reaping is now a recurring operator action item (#3 this session, and it is not the first). Each
  reap is manual, needs per-item verification, risks real work — the SECRET-HOTROTATE near-miss the
  same day proved the risk is not theoretical: 11 implementations existed ONLY inside worktrees queued
  for deletion.

  **A cleanup that must be repeated is not a fix.** This ticket is explicitly NOT another cleanup —
  it is forbidden from deleting anything. Its job is to find why the rate of branch/worktree creation
  exceeds the rate of retirement, and to propose the mechanism that closes that gap
  [[fix-root-cause-never-workaround]].

  ## QUESTIONS TO ANSWER WITH DATA, NOT OPINION
  - What CREATES them? Attribute the current 164+90 branches to their creators (dogfood-eval runs,
    fleet-droid launches, manual sessions, salvage/rederivation). Give counts per source. The 27
    dogfood worktrees in one batch suggest one automated source dominates — confirm or refute.
  - What is supposed to RETIRE them, and why doesn't it? `fleet/retire-done.sh` archives tickets on a
    done-marker; is there any equivalent for branches/worktrees? If a reaper exists, why did 62 rig
    worktrees accumulate? If none exists, say so plainly.
  - Where does the LIFECYCLE break? A branch created by an automated run should have a defined end.
    Name the exact point where that ownership is dropped.
  - Why do branches "land by re-derivation" (content identical, SHA different)? 16 rig branches are in
    that state — see RIG-BRANCH-16-DEEPDIVE. Is that a normal consequence of the landing flow or a
    defect in it? This may be the single largest contributor.
  - Is the WORKTREE count driven by the BRANCH count, or independently?

  ## METHOD
  Use the owned tooling, not ad-hoc greps: `git for-each-ref` with committerdate/author, the fleet
  scripts' own logs, `fleet/state/` markers. A zero-hit search is not evidence of absence — read the
  scripts that create and remove these things. Cite `file:line` for every mechanism claim.
accept: |
  DONE-CONTRACT:
  - `fleet/state/BRANCH-SPRAWL-ROOT-CAUSE.md` exists containing: attribution of current branches and
    worktrees to their CREATING mechanism with counts; the retirement mechanism for each (or an
    explicit "none exists"); and the named breakage point(s) in the lifecycle, each cited file:line.
  - A ranked list of causes by VOLUME — what actually produces the most, not what is most annoying.
  - A proposed mechanism per top cause, each stated as: what it automates, what it would have
    prevented in the 2026-07-26 reap specifically, and its risk of deleting real work.
  - An explicit answer to: "would this mechanism have deleted the SECRET-HOTROTATE diffs?" A proposal
    that would have destroyed that work is REJECTED regardless of how much it cleans up.
  - NON-VACUOUS: an investigation that examines zero branches is RED.
  - **DELETES NOTHING.** No branch, worktree, or file removal. A diff that deletes refs is out of
    contract — findings become tickets.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately**, fully concurrent — owns one new state file.
- **Related (do not duplicate):** RIG-BRANCH-16-DEEPDIVE investigates the re-derivation cohort
  specifically; this ticket owns the GENERAL cause. Read its findings if it lands first; cite rather
  than re-derive.
- **Blocks:** any future automated reaper — building one before knowing the cause repeats the pattern.
- **Wave:** parallel lane, P0.
