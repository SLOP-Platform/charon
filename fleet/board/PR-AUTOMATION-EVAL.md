repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: design-review
branch: eval/pr-automation
depends_on:
owns: fleet/state/PR-AUTOMATION-EVAL.md
serial_justified: |
  One comparative evaluation. The candidates only rank against each other measured in one pass
  against the same real PRs.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. EVAL lane — measure and report. Wire NOTHING.
source: |
  Operator, 2026-08-01: review Aider-AI/aider and The-PR-Agent/pr-agent for automating PRs.
note: |
  ## WHY NOW — the measured bottleneck is MERGING, not building
  Evidence from 2026-08-01:
  - Session opened with **46 open PRs**, many >370h old.
  - The blast-radius audit found the **top 3 unblock levers are all MERGES, not builds**:
    SYNC-SCHEDULE (PR-open ~194h, unblocks 7), GITHUB-LIMITS-HARDENING (unblocks 7),
    BENCH-OOB-GRADING (unblocks 7).
  - 26 tickets are blocked; **13 of the 14 hard-blocked are gated on work already BUILT and
    sitting in an open PR.**
  15 build lanes run in parallel and the queue still grows. More building does not help.

  ## THE UNCOMFORTABLE QUESTION — ANSWER IT HEAD-ON
  We HAND-ROLLED a reviewer pool: `fleet/review-pool.sh` (383 lines) + `review-pool.test.sh`
  (451 lines), merged via #250. It has never run in CI and its queue has never been populated.
  Attempt #1 was rejected for 4 blockers including a `reviewer != builder` guard that was a
  structural no-op, and a prompt-injection hole where a PR diff could steer its own approval.
  **`pr-agent` is the best-known off-the-shelf tool for exactly this.**
  So: did we hand-roll ~830 lines of something an adopted tool does better, and does pr-agent
  already solve the specific blockers we had to fix by hand? Under the ADOPT-FIRST directive
  hand-rolling carries significant negative weight — a REJECT of pr-agent must prove no sane
  adopt option exists, not merely that ours exists already. Sunk cost is NOT a reason to keep it.

  ## THE TWO CANDIDATES ARE DIFFERENT SHAPES — do not conflate them
  - **The-PR-Agent/pr-agent** — PR review/description/improve automation. Direct overlap with
    review-pool.sh. This is the primary candidate.
  - **Aider-AI/aider** — an AI pair-programming CLI that writes code and commits. Overlaps with
    our BUILD path (fleet-droid.sh -> charon-run.sh -> opencode), NOT the review path. Judge it on
    whether it beats `opencode` as the work client, and on whether it closes PRs faster end-to-end.
    Do not score it as a review tool.
  Add any other serious candidate you find (e.g. CodeRabbit, Greptile, Danger, Reviewpad,
  Sourcery, GitHub's own review automation) — the brief is a floor, not a ceiling.

  ## HARD RULES
  1. **ADOPT-FIRST.** Hand-rolling is the LAST choice. "We already built ours" is sunk cost, not
     an argument [[no-rig-as-product-adopt-dont-handroll]].
  2. **Verdicts land in `fleet/state/EVAL-REGISTRY.md`** as rows, long-form in the owned file.
     A verdict not in the registry gets paid for twice.
  3. **Corrected lens.** Ask what each FILLS that we lack — "what does this replace?" is blind to
     gaps. **Size / stars / dependency count are NOT rejection criteria.** Judge on: maintenance
     liveness · fit-without-bending · control direction (a library we CALL vs a framework that
     CALLS us — we must stay agent- and provider-agnostic) · exit cost · ops burden.
  4. **MCP-first** is the preferred integration shape — check every candidate for an MCP server.
  5. **NO HARDCODED PROVIDER OR MODEL** [[charon-modular-agent-and-provider-agnostic]]. A tool
     that only speaks to one vendor's API is a serious mark against it. Ours must route through
     the Charon gateway (`charon/<model>`), so BYO-model / OpenAI-compatible-endpoint support is a
     hard requirement, not a nice-to-have. State plainly whether each candidate can be pointed at
     an arbitrary OpenAI-compatible base URL.
  6. Every leverage claim names a MEASURED incident it would have prevented.

  ## TEST AGAINST THESE REAL INCIDENTS (all from 2026-08-01)
  - **#313 CI-SUITES-CANARY**: the test suite re-implemented the logic it claimed to test
    (`mk_canary_runner` with its own `CANARY_WINDOW_DAYS=14`). Mutating the REAL file moved no
    test. Caught only by a manager running a manual mutation. **Would either tool catch a
    fixture-bypass like this?** This is the sharpest test in the list — most review tools comment
    on style and miss "green over a path no test runs".
  - **REVIEWER-TAB-POOL B1**: a guard comparing disjoint namespaces — structurally unable to fire.
  - **#188 dead-no-op**, cited as ground truth by the REVIEWER-TAB-POOL ticket.
  - 46 PRs rotting: does the tool actually reduce time-to-merge, or just add comments to PRs that
    still nobody merges? **Comment volume is not throughput.**

  ## DELIVERABLE
  1. Per candidate: MCP? arbitrary OpenAI-compatible endpoint? self-hostable? control direction?
     exit cost? ops burden? what it FILLS vs what we have?
  2. **The head-to-head:** pr-agent vs our `review-pool.sh`, feature by feature, against the 4
     blockers we hand-fixed (reviewer!=builder, fail-closed, real+wired test, prompt-injection).
     Which does each better, with evidence.
  3. A RECOMMENDATION: adopt / wrap / reject — and if adopt, whether `review-pool.sh` should be
     RETIRED. An honest "keep ours, here is why" is fine but must be argued against the adopt
     option, not from sunk cost.
  4. EVAL-REGISTRY rows.

D&S — Deps & Sequence:
  - Depends on: nothing. Pure measurement, owns one doc, collision-free.
  - Feeds REVIEWER-TAB-POOL: if pr-agent wins, that ticket is re-scoped or retired.

## SCOPE GAP 2026-08-02 (operator-directed): THE MERGE/LIFECYCLE HALF IS NOT EVALUATED

Operator: "I WANT a tool that will handle draft PR/PR in the BACKGROUND AS THEY ARE GENERATED.
I want this researched as this can NOT be unique to us." Correct — it is a solved product
category, and this eval currently covers only HALF of it.

WHAT THIS EVAL COVERS TODAY: PR **REVIEW** automation — pr-agent, aider, CodeRabbit, Greptile,
Danger, Reviewpad. Verdict ADOPT-pr-agent-wrapper is sitting in **OPEN DRAFT PR #391**.

WHAT IT DOES NOT COVER: the **MERGE QUEUE / PR LIFECYCLE AUTOMATION** category — tools whose entire
job is "react to PR events in the background: when CI is green and approvals are satisfied, merge;
batch, retry, rebase, and report". NONE of these has an EVAL-REGISTRY row:
  - **Mergify** — rules engine + merge queue, reacts to PR webhooks; the market leader
  - **GitHub native merge queue** — zero new infra, already in the platform we use
  - **Prow / Tide** (Kubernetes) — the mature open-source answer; batch merging on label+CI state
  - **Kodiak** — small auto-merge bot, GitHub App
  - **Bulldozer** (Palantir) — auto-merge on configurable conditions
  - **Aviator**, **Trunk Merge** — commercial merge queues
  - **plain GitHub Actions on `pull_request` / `check_suite` events** — the DIY event-driven floor,
    and the honest baseline every candidate must beat
MCP-first still applies: check EVERY candidate for an MCP interface (standing operator input).

WHY IT MATTERS HERE, measured 2026-08-02: **67 open PRs, 52 DRAFTS, up from 42 in ONE session.**
`fleet-droid.sh` ends every ticket by opening a draft, so drafts are the launcher's normal output
and the queue grows monotonically with fleet throughput. Polling reviewers cannot keep up and
already drained the entire GraphQL quota trying. **This needs to be EVENT-DRIVEN, not polled** —
which is precisely what this category does and our `review-pool.sh` does not.

Done contract additions:
 1. Evaluate the merge-queue category against the SAME 4 criteria as the review half. A verdict per
    candidate in EVAL-REGISTRY — never in a handoff note.
 2. Answer explicitly: **can it drive DRAFT PRs?** Most merge queues ignore drafts by design. If the
    fleet's normal output is a draft, either the tool must handle drafts or the LAUNCHER must stop
    opening them as drafts. That is a real fork in the design — decide it here.
 3. Weigh event-driven (webhook/Action) vs polling explicitly. Polling is what exhausted the quota;
    it is a cost axis, not just an elegance one.
 4. Land PR #391 first or fold it in — an ADOPT verdict stuck in a draft is this ticket's own
    failure mode, and it has been sitting unread.
 5. The two halves compose: a REVIEW tool produces the verdict, a MERGE tool acts on it. Do not
    pick one and call the problem solved.

## Dependencies & Sequence

Raised with PR-QUEUE-DRIVE (queue #6): that ticket DRAINS the current 52 by hand, this one stops the
backlog re-forming. Do both — draining without automation just refills, automating without draining
leaves 52 stranded.

### HARD CONSTRAINT (operator, 2026-08-02): PROPERLY, NOT BLINDLY

"It's closing PRs / draft PRs PROPERLY with whatever oversight and review is required — not doing
it blindly."

**The automation is a DELIVERY MECHANISM for a review bar that has already been SATISFIED. It is
never a substitute for the bar.** A merge queue that lands work faster than we can verify it is a
regression, not an improvement — it converts a review backlog into a defect backlog, which is
strictly worse because the defects are then on master.

MEASURED THE SAME DAY, and this is the whole argument: **6 of 8 PRs in one review round were
BOUNCED.** Two shapes accounted for nearly all of them —
  (a) a safety property asserted in PROSE that the code does not implement (#360 claimed atomic
      config write three times; `grep -n os.replace` = 0, the real write was `cp -p`);
  (b) a suite that passes against a MOCK of the component under test and therefore cannot fail on
      revert (#334 byte-identical 21/0 with the change reverted).
**Blind auto-merge on green CI would have landed every one of those**, because CI was green on all
of them. Green CI is not evidence of correctness here; it is evidence that the tests ran.

THEREFORE, evaluate every candidate on these first — a tool that cannot do this is disqualified
however good its merge queue is:
 1. Can it BLOCK on an explicit human/agent verdict, not merely on CI status?
 2. Can it require the ADVERSARIAL review to have run, and treat a missing verdict as BLOCKING
    rather than as absent-therefore-fine? (Fail-closed on absence — today's `land-push` CI gate
    fails OPEN on "no PR exists", which is exactly the wrong default.)
 3. Can it distinguish "CI green" from "reviewed"? Anything that conflates them is disqualified.
 4. Does it handle a CONFLICTED PR correctly? Those get ZERO checks and read as mergeable-looking —
    a queue that treats no-checks as not-failing will merge unverified work.
 5. Is the merge decision AUDITABLE after the fact — who/what approved, on what evidence?
The prize is removing the LATENCY and the polling cost, not removing the judgement.

## CONSOLIDATED SCOPE 2026-08-02 — ONE EVAL, TWO HALVES, ONE BAR

This ticket now covers the FULL PR lifecycle. Both halves are in scope and neither may be dropped:

  HALF A — REVIEW automation: who/what produces the verdict.
    Candidates: pr-agent (current ADOPT verdict, stuck in OPEN DRAFT PR #391), aider, CodeRabbit,
    Greptile, Danger, Reviewpad, our own review-pool.sh (~830 hand-rolled lines).
  HALF B — MERGE / LIFECYCLE automation: what ACTS on the verdict, in the background, as PRs appear.
    Candidates: Mergify · GitHub native merge queue · Prow/Tide · Kodiak · Bulldozer (Palantir) ·
    Aviator · Trunk Merge · plain GitHub Actions on `pull_request`/`check_suite` events (the honest
    DIY baseline every candidate must beat). ZERO of these has an EVAL-REGISTRY row today.
  THEY COMPOSE. A review tool produces a verdict; a merge tool acts on it. Adopting one and
  declaring the problem solved is the failure mode — say which half each candidate covers.

### THE BAR — every candidate is scored on ALL of these, and 1-5 are DISQUALIFYING

  1. Blocks on an explicit VERDICT, not merely on CI status.
  2. Treats a MISSING adversarial review as BLOCKING — fail-CLOSED on absence. (Our own land-push
     CI gate fails OPEN on "no PR exists"; that is the wrong default and must not be reproduced.)
  3. Distinguishes "CI green" from "reviewed". Anything conflating them is disqualified.
  4. Handles a CONFLICTED PR correctly — those receive ZERO checks and read mergeable-looking. A
     queue treating no-checks as not-failing will merge unverified work.
  5. Leaves an AUDITABLE decision trail: who/what approved, on what evidence.
  6. Can it drive DRAFT PRs? Most merge queues ignore drafts BY DESIGN, and drafts are the
     launcher's normal output (52 of 67 open PRs). Either the tool handles drafts or
     `fleet-droid.sh` stops opening them as drafts — decide that fork explicitly, do not leave it.
  7. EVENT-DRIVEN vs POLLING, treated as a COST axis: polling drained the entire GraphQL quota on
     2026-08-02 (cycle 461 in minutes; killing the pools took graphql 0/5000 -> 3784/5000).
  8. MCP interface? Check EVERY candidate (standing operator input).
  9. Self-hosted vs SaaS: egress and secret exposure for a PRIVATE rig and a PUBLIC product repo.

### WHY THE BAR IS SHAPED THIS WAY — measured, not theoretical
**6 of 8 PRs bounced in ONE review round on 2026-08-02, every one with GREEN CI.** Two shapes:
(a) a safety property asserted in PROSE that the code does not implement — #360 claimed atomic
config write three times, `grep -n os.replace` = 0, the real write was `cp -p`; (b) a suite passing
against a MOCK of the component under test, so it cannot fail on revert — #334 was byte-identical
21/0 with the change reverted. **Blind auto-merge on green CI would have landed all of them.**
Green CI proves the tests RAN, not that the work is CORRECT.
**The automation is a DELIVERY MECHANISM for a review bar already satisfied — never a substitute
for it.** The prize is removing LATENCY and POLLING COST, not removing judgement. A queue that
lands work faster than we can verify converts a review backlog into a DEFECT backlog on master,
which is strictly worse.

### REQUIRED: A FOCUSED ADVERSARIAL REVIEW OF THIS EVAL (operator-directed)
Do NOT accept this eval's own conclusions. Run a dedicated adversarial pass against it and record
the result in EVAL-REGISTRY:
  - Attack the INCUMBENT framing: is `review-pool.sh` being scored generously because we wrote it?
    It has 6 known defects incl. a `rm -rf` of the caller's TMPDIR and silently dropped
    `--wait/--retries`. State them in the comparison.
  - Attack the CHALLENGER framing: check for the **under-scoped trial** anti-pattern — an eval that
    genuinely runs a candidate but configures the INCUMBENT too narrowly so the candidate wins a
    comparison it should have lost. It has ALREADY happened twice here (PR #320 Coverage.py 2/3 ->
    WATCH vs OTel 0/3 -> ADOPT; PR #371 River run on defaults with its deciding parameter unset).
  - Verify every capability claim by RUNNING it, not by reading the README. A vendor claim is a
    hypothesis.
  - The verdict must name what we would DELETE if we adopt. An adoption that deletes nothing is an
    addition, and additions are how we reached ~20% utilisation across 52 tools.
  - Cross-check against REVIEWER-TAB-POOL and UNBLOCK-REVIEW-INFRA: if a tool wins, those are
    re-scoped or retired — say which, explicitly.

## Dependencies & Sequence

P0, and paired with PR-QUEUE-DRIVE (queue #6): that ticket drains the current 52 by hand, this one
stops the backlog re-forming. Draining without automation refills; automating without draining
leaves 52 stranded. Land PR #391 or fold it in FIRST — an ADOPT verdict sitting in an unread draft
is this ticket's own failure mode, demonstrated.
