repo: charon-private
tier: strong
priority: 1
difficulty: 4
work_class: design-review
branch: chore/pr-queue-drive
depends_on:
owns: fleet/state/PR-QUEUE-DRIVE.md, docs/review-log/PR-QUEUE-DRIVE.md
substrate: N/A
substrate-novel: |
  Everything mechanical here is ADOPTED and none of it is rebuilt: `gh pr list` / `gh pr checks`
  enumerate the queue and its CI state, GitHub's `update-branch` API refreshes a stale base, and
  fleet/land-push.sh is the one sanctioned landing path. This ticket writes no tool.
  What no external reviewer-bot does is the two checks the MEASURED bounce data says actually
  catch defects: grep the diff for the MECHANISM a safety claim asserts, and run the suite with
  the change REVERTED to see whether it can fail at all. Coverage tools measure lines executed and
  linters measure shape; neither can tell that an assertion is aimed at a MOCK of the very
  component under test, which is what a passing-on-revert suite means. That verification stance,
  applied per PR against the claim its own body makes, is the novel slice.
serial_justified: |
  One shared queue with one merge order. Two lanes landing into the same master would interleave
  refreshes and re-stale each other's bases — the refresh/land loop is inherently serial, and
  splitting it multiplies stale-base churn instead of reducing it.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. Land ONLY via fleet/land-push.sh. Never `--force`,
  never a raw `git push`, never a local `git merge` or `git rebase` of a PR branch — refresh
  through the GitHub `update-branch` API so the remote stays the source of truth.
source: |
  Measured on the live queue, 2026-08-01: of eight PRs bounced in one day, SIX failed on exactly
  two defect shapes. That is not a spread of unrelated mistakes; it is two reproducible patterns,
  and a review that does not look for them will keep passing them.
note: |
  ## THE JOB
  Drive the OPEN-PR queue to a verdict. For each open PR: refresh it against master, get CI green,
  review it adversarially, then LAND it or BOUNCE it with evidence. A PR that sits at neither
  outcome is the queue's actual failure state — it holds a review slot, ages its base, and blocks
  nothing visibly.

  ## THE TWO DEFECT SHAPES THAT ACCOUNT FOR 6 OF 8 BOUNCES
  These are MEASURED priors from today's queue, not general advice. Check BOTH on every PR.

  1. A SAFETY PROPERTY ASSERTED IN PROSE THAT THE CODE DOES NOT IMPLEMENT.
     The PR body, the ticket note, or a header comment states a guarantee ("never force-pushes",
     "fails closed", "refuses when it cannot determine"). The diff does not contain the mechanism
     that would make it true. The claim reads as verified because it is stated confidently and
     because the suite is green — the suite simply never tests it.
     THE CHECK: grep the diff for the CLAIMED MECHANISM by name — the flag, the guard clause, the
     exit code, the refusal branch. If the words that would implement the guarantee do not appear
     in the changed code, the guarantee is prose. Bounce it and quote both the claim and the
     absence.

  2. A SUITE THAT PASSES AGAINST A MOCK OF THE COMPONENT UNDER TEST.
     The tests stub the very thing the change modifies, so they assert the mock's behaviour rather
     than the code's. Such a suite is green before the change, green after it, and green with it
     reverted — it can never fail, which makes it worse than no suite because it looks like proof.
     THE CHECK: RUN THE SUITE WITH THE CHANGE REVERTED. If it still passes, the suite does not
     cover the change. Bounce it with the revert-run output attached. This is the same red-proof
     discipline the fleet already demands of new gates, applied at review time.

  ## THE REVIEW BAR — NON-NEGOTIABLE, EVERY PR
  * GREP FOR THE CLAIMED MECHANISM before believing any safety claim in a PR body.
  * RUN THE SUITE WITH THE CHANGE REVERTED before believing any green suite.
  Do neither and the review has confirmed nothing except that CI is running. "CI is green" is a
  statement about the runner, not about the change.

  ## ALREADY BOUNCED WITH REASONS — DO NOT RE-LAND BLIND
  #317, #320, #334, #342, #343, #346, #360, #371.
  Each carries a stated bounce reason. Before touching any of them, READ THE BOUNCE and confirm
  the specific defect is fixed in the CURRENT head. A re-land that does not name which bounce
  reason it resolves is a re-land that ignored the review, and it will bounce again on the same
  finding — which is how a queue turns into a loop.

  ## STALE BASE — REFRESH, DO NOT RERUN
  Refresh via the GitHub `update-branch` API. Do NOT reach for `gh run rerun`: rerun replays
  against the CACHED merge ref, so it re-runs the same stale merge and produces the same failure,
  which reads as flake and is not.

  ## SCOPE BOUNDARY
  Code fixes belong to the PR's OWN branch and its OWN ticket. This lane refreshes, verifies,
  lands or bounces; it does not adopt another ticket's implementation work. This ticket's own diff
  is its two evidence files and nothing else.

  ## DELIVERABLE
  `fleet/state/PR-QUEUE-DRIVE.md` — one row per open PR: number, verdict (LANDED / BOUNCED /
  BLOCKED-ON), and for every bounce the DEFECT SHAPE (1, 2 or other) plus the evidence: the grep
  that found no mechanism, or the revert-run that stayed green. Plus a short
  `docs/review-log/PR-QUEUE-DRIVE.md` fragment. A bounce with no evidence cell is an opinion.

## Dependencies & Sequence

- **depends_on: none.** This lane consumes the EXISTING open-PR queue. It builds nothing, imports
  no fleet module and changes no gate, so nothing has to land first.
- **Sequence: continuous, starting NOW.** The queue's cost is carrying cost — every hour a PR sits
  open its base ages, so the refresh work grows while nothing lands.
- **Concurrency safety — owns-collision: none.** Both owned paths are NEW files named after this
  ticket. No other live ticket owns `fleet/state/PR-QUEUE-DRIVE.md` or
  `docs/review-log/PR-QUEUE-DRIVE.md`. Verified against the live board before minting.
- **Runs in PARALLEL with `RESCUE-TRIAGE-RIG` and `RESCUE-TRIAGE-PRODUCT`, by construction.** This
  lane touches ONLY branches that ALREADY have an open PR; both rescue-triage lanes touch ONLY
  branches with NO PR. The branch sets are disjoint, so no two lanes can contend for one branch.
- **Hand-off, not a dependency:** any PR the rescue-triage lanes OPEN becomes input to a later
  pass of this one. That is merge-order, not a build prereq — none of the three blocks another.
- **SERIAL AGAINST ITSELF.** Exactly one lane drives this queue at a time. A second concurrent
  driver would re-stale the first one's freshly refreshed bases and double the merge-queue churn.
