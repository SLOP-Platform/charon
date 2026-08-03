repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: feat/backlog-drain-plan
depends_on:
owns: fleet/state/BACKLOG-DRAIN-PLAN.md, fleet/checks/backlog-census.sh, fleet/tests/backlog-census.test.sh
serial_justified: |
  ONE census over ONE set of pools. Split lanes would each count a different subset with a
  different definition of "landed" and produce numbers that cannot be reconciled — which is the
  exact confusion this ticket exists to end.
substrate: N/A
substrate-novel: |
  Nothing external can answer "which of OUR work is finished but undelivered" — it is a join over
  our board, our branches, our PRs and our state markers. The counting substrate already exists
  and MUST be reused rather than rebuilt: fleet/checks/stranded-work.sh already computes five
  loss shapes (pushed-no-pr, closed-pr-unlanded, dirty-worktree, unpushed-branch, pr-no-checks)
  and fleet/pr-queue.sh already enumerates open PRs over REST+ETag at zero quota cost. The novel
  slice is the PRIORITISED DRAIN ORDER and the drain PROCESS — not another counter.
execution: |
  Off-Claude, SG tab. Use BARE model ids ONLY — never a provider-pinned id (`-ds`, `-go`, `-groq`). Pinning is what collapses a broker pool to one provider and caused the 2026-08-02 outage. Census + plan + a drain tool.
  Land NOTHING from the backlog in this ticket — this produces the ORDER and the MECHANISM; the
  manager executes the landings.
source: |
  Operator, 2026-08-02 - "Prioritize the Draft backlog, the PR backlog, the unlanded, the
  un-merged, work done, commits ... come up with a tool/process to start draining these pools NOW
  before we start any other work."
note: |
  ## WHY THIS IS THE TOP OF THE QUEUE
  The fleet's binding constraint is NOT building — it is DELIVERING. Measured 2026-08-02:
    - **~49 open DRAFT PRs** and ~11 non-draft, and the draft count ROSE 42 -> 52 in one prior
      session. `fleet-droid.sh` ends every ticket by opening a draft and never merges, so drafts
      grow MONOTONICALLY with throughput. A faster fleet makes this WORSE.
    - **211 `pushed-no-pr`** branches, **50 `closed-pr-unlanded`**, 3 dirty worktrees, 5 unpushed
      branches — 270 findings from `fleet/checks/stranded-work.sh`.
    - Repeatedly today, work was found FINISHED but UNDELIVERED - TOOL-COMPOSITION-LAYER
      (13KB research done, stuck in a draft, ticket marked DONE), GRADE-MODEL-PROVIDER-PAIR
      (SUBMITTED, blocked by a CI red that was infra), BROKER-BARE-TIER-LEGS (built, held for
      weeks, and its absence CAUSED a fleet-wide outage today).
  **Every one of those was finished work that nobody landed.** That is the pool to drain.

  ## THE CENSUS — count it ONCE, precisely, with agreed definitions
  Build `fleet/checks/backlog-census.sh` producing ONE table. REUSE stranded-work.sh and
  pr-queue.sh; do not re-implement their scans. Categories, each with a COUNT and a LIST:
    P1 open DRAFT PRs, split by CI state (all-green / red / no-checks)
    P2 open NON-draft PRs, same split
    P3 `pushed-no-pr` branches carrying unlanded commits
    P4 `closed-pr-unlanded` — a PR was closed while its branch still carries unlanded commits
    P5 tickets in `state/submitted/` with no merged PR
    P6 dirty worktrees / uncommitted work
  Use REST (`gh api repos/.../pulls`), NEVER GraphQL — REST is the free quota pool.
  SQUASH-merge repo - `git merge-base --is-ancestor` is a WRONG merged-ness test here; use PR state.

  ## THE PRIORITISATION — this is the deliverable, not the census
  Rank the ENTIRE backlog into a drain order. Ranking inputs, in order of weight:
    1. **Unblocks others** — a PR that other tickets depend on outranks a bigger isolated one.
       BROKER-BARE-TIER-LEGS is the worked example: 3 lines, held for weeks, and its absence took
       the fleet down.
    2. **Green and ready** — all checks pass, no conflicts. These are FREE throughput; land first.
    3. **Cheap to make landable** — only needs `update-branch`. Distinguish from a real conflict.
    4. **Age/rot** — an old branch conflicts worse every day. Rot is compounding cost.
    5. **Supersededness** — CLOSE it with evidence. Closing IS draining, and a superseded draft is
       noise that hides the real queue.
  Output an ORDERED list with, per item - number, category, verdict (LAND / REFRESH-THEN-LAND /
  CONFLICT-NEEDS-WORK / CLOSE-SUPERSEDED), and the one-line reason.

  ## THE DRAIN PROCESS — mechanize the repeatable half ONLY
  Distinguish what is MECHANICAL from what needs JUDGEMENT and never blur them.
  MECHANICAL (safe to automate): census; `update-branch` refresh of a stale base; classify by CI
  state; detect superseded-by-a-later-branch; report before/after counts.
  JUDGEMENT (stays human/reviewer): merge; close; resolving a real conflict; reviewing a diff.
  **Never `gh run rerun` to clear a stale-base red** — rerun replays the CACHED merge ref and
  reproduces the same failure, which reads as flake. Refresh via `update-branch` instead.
  ACCEPTANCE OF THE PROCESS ITSELF: report the backlog count BEFORE and AFTER each batch. **If
  the count does not FALL, say so plainly rather than reporting activity.**

  ## KNOWN TRAPS, measured today — do not rediscover these
    - `rig-ci` was RED on effectively every PR because a stray `.worktrees/` GITLINK (mode 160000,
      no `.gitmodules`) broke every CI checkout with `git exit 128`. FIXED on master 2026-08-02
      (`9f5a743`). Any red older than that fix must be RE-EVALUATED, not trusted.
    - A PR's `head.sha` can be STALE versus the branch ref; `update-branch` then 422s. Read the
      sha from `git/ref/heads/<branch>`, not from the PR object.
    - `mergeable` sits at `null`/`unknown` while GitHub computes; poll, do not conclude.
accept: |
  a. `fleet/checks/backlog-census.sh` emits the P1-P6 table with counts AND lists, reusing
     stranded-work.sh and pr-queue.sh rather than re-scanning. REST only.
  b. Deterministic - two runs with no repo change produce identical output.
  c. `fleet/state/BACKLOG-DRAIN-PLAN.md` carries the FULL ordered drain list with a verdict and a
     reason per item. An item with no reason is not ranked, it is guessed.
  d. The drain PROCESS is written as a runnable sequence, with the mechanical/judgement split
     explicit and the before/after count requirement built in.
  e. Fail-on-revert on the census - seed a fixture with a known draft/stranded branch and prove
     the census FINDS it; remove it and prove the count drops.
  f. Anti-false-positive - a clean fixture yields zero findings.
  g. Distinct exit codes - 0 clean, 1 findings, 8 could-not-check. "Could not check" must never
     read as "backlog is empty" — a quota outage that looks like a drained queue is the exact
     confusion that bit this rig twice on 2026-08-01.
scope: |
  Census, prioritisation and the drain mechanism. Lands, closes and merges NOTHING — the manager
  executes the plan. Does not modify review-pool.sh or pr-queue.sh.

## Dependencies & Sequence

- **depends_on: none.** Every input exists today.
- **RUNS FIRST, ahead of new feature work** (operator-directed 2026-08-02). Delivery is the
  binding constraint; building more while the delivery pool grows makes the problem worse.
- Complements, does not duplicate - `PR-QUEUE-DRIVE` DRIVES the open-PR queue to verdicts;
  this ticket produces the ORDER and the MECHANISM it should drive in. `PRIORITY-DROPOUT-AUDIT`
  finds work missing from the LIST; this finds work finished but UNDELIVERED.
- NEVER PIN A PROVIDER. Operator, 2026-08-02 - "DO NOT PIN ANYTHING, that is how we get into trouble, the Broker doesn't need anything pinned." If the broker routes to a drained provider, the fix is PARK-REARM-FUNDED-PROVIDER (park it), never a pin in the caller.
