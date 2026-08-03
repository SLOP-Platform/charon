repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: fix/unblock-review-infra
depends_on:
owns: fleet/state/UNBLOCK-REVIEW-INFRA.md, docs/review-log/UNBLOCK-REVIEW-INFRA.md
serial_justified: |
  One dependency chain, not parallel work. The review pool is the mechanism every other PR is
  processed BY, so its three defects must be resolved in order against a single moving target
  (fleet/review-pool.sh). Splitting them means two tabs rewriting the same file concurrently,
  which is the collision this ticket exists to end.
substrate: N/A
substrate-novel: |
  Nothing is adopted or built here. This is sequencing and reconciliation of THREE existing
  branches that all touch fleet/review-pool.sh, whose base moved when PR #393 landed the
  sandbox-containment fix into that exact file. There is no external tool that resolves
  ownership contention between three of your own open PRs.
accept: |
  HIGHEST BLAST RADIUS FIRST — this lane unblocks the machinery that processes every other PR.
  1. PR #392 (PR-QUEUE-REST-ETAG, 40/40 tests, 8-way red-proof, zero-quota steady state) is
     BUILT and its cutover into review-pool.sh is APPROVED but never done. GitHub GraphQL quota
     (5000/hr) was exhausted in under an hour by 7 reviewer tabs, which also blocked `gh pr
     review` and land-push CI verification, while REST core sat untouched at 5000/5000. Do the
     cutover. This is the single highest-leverage item in the queue.
  2. PR #389 (reviewer-tab) is the tool the reviewer tabs RUN. Land or fix it before scaling the
     pool further.
  3. PR #346 is BOUNCED, do NOT land as-is: it switches B1 to a CHARON-AUTHOR-DROID PR-body
     marker that ZERO of 16 PRs carry and no code writes, with fail-closed skip — i.e. it would
     make the pool review NOTHING. It also now conflicts with #393's review-pool.sh hunk. Rework
     or close with evidence.
  Each step: fail-on-revert test, and `gh pr checks` verified GREEN before landing.

note: |
  ## THREE-WAY RECONCILIATION MAP (corrected — first fragment swapped #389 and #346)

  Base: origin/master (2119d77 fix/SANDBOX-CONTAINMENT) — review-pool.sh has trap fix only.

  PR #392 (feat/pr-queue-rest-etag) — OPEN, CI GREEN:
    - fleet/pr-queue.sh: NEW file, REST+ETag queue generator, drops INTO review-pool.sh's queue.
      Author extraction: git commit name via REST /pulls/{n}/commits (same semantics as old GraphQL).
    - fleet/tests/pr-queue.test.sh: 40/40 PASS, 8-way red-proof, zero real API calls.
    - fleet/review-pool.sh: NOT MODIFIED.
    Status: READY. Cutover requires integrating pr-queue.sh into the review-pool.sh call path.

  PR #389 (feat/reviewer-pool-headless-tabs) — MERGED 2026-08-02T04:48:33Z (e83bea0):
    - The reviewer-tab tool: fleet/reviewer-tab.sh + fleet/spawn-tab.sh + fleet/REVIEWER-POOL-PROCESS.md.
    - Does NOT touch fleet/review-pool.sh.
    Status: LANDED. Step 2 of the ticket is DONE.

  PR #346 (feat/reviewer-tab-pool) — OPEN, BOUNCED:
    - Touches fleet/review-pool.sh, fleet/checks/rig-ci-scope.sh, fleet/tests/review-pool.test.sh.
    - Contains both good hardening and a fatal author-extraction change:
      1. queue_gen: CHARON-AUTHOR-DROID PR-body marker (jq capture from .body).
         PROBLEM: ZERO of 32 open PRs carry this marker. With B1 fail-closed, every PR
         skips — the pool reviews nothing. REJECT; revert to git-commit approach.
      2. claim_next: mapfile+awk field parse (fixes IFS collapse bug) — KEEP.
      3. claim_next: B1 fail-closed on UNKNOWN author — KEEP.
      4. build_review_prompt: base64-encode diff (B4 prompt-injection fix) — KEEP.
      5. _parse_verdict: strict delimiter enforcement (exit 2 on malformed) — KEEP.
      6. rig-ci-scope.sh add review-pool.test.sh to CI_SUITES (B3 fix) — KEEP.
    - Merges cleanly against current master (no conflict with #393's trap fix).
    Status: PARTIAL — rework (revert author extraction) or close with evidence.

  ## ACCEPT CRITERIA (per step)

  Step 1 (#392 cutover):
    - review-pool.sh queue_gen() calls fleet/pr-queue.sh gen OR review-pool.sh imports pr-queue.sh logic.
    - OR reviewer tabs are updated to run `pr-queue.sh gen` before `review-pool.sh claim`.
    - Gate: 40/40 pr-queue tests pass; zero GraphQL calls on steady-state queue generation.
    - No change to review-pool.sh claim/review logic in this step.

  Step 2 (#389) — DONE: headless reviewer-tab tool landed (e83bea0, 2026-08-02).

  Step 3 (#346 disposition):
    - REWORK: keep mapfile, B1 fail-closed, base64 diff, strict verdict parse, CI_SUITES add;
      REVERT author extraction to git-commit approach. Then land.
    - OR CLOSE with evidence: CHARON-AUTHOR-DROID marker not present in any of 32 open PRs.

  ## CONFLICT RESOLUTION

  The only genuine conflict is in fleet/review-pool.sh lines 86-92 (author extraction).
  - master keeps: `gh pr view --json commits --jq '.commits[-1].authors[0].name'`
  - #346 wants to change to: `gh pr view --json body --jq 'capture("^CHARON-AUTHOR-DROID: (?<id>...)")'`
  Resolution: #346's author extraction is REJECTED (zero of 32 open PRs have the marker).
  The git-commit approach (current master) is PRESERVED.
  All other changes from #346 (mapfile, B1, base64, verdict, CI_SUITES) are PRESERVED.
