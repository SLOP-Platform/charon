repo: charon-private
tier: strong
priority: 1
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
