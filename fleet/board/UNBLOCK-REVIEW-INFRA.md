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

## Dependencies & Sequence

FIRST in the blast-radius order. The review pool is the machinery every other PR is processed
BY, so nothing else in the queue moves at full rate until this lands. No inbound deps.

Internal order is strict and NOT parallelisable: (1) #392 REST+ETag cutover, because the GraphQL
quota exhaustion it fixes is what throttles every reviewer tab; (2) #389 reviewer-tab, the tool
those tabs execute; (3) #346 rework-or-close, which touches the same fleet/review-pool.sh and
would collide with either of the first two.

Blocks: SESSION-CLOSE-UNBLOCK and MONEY-SECURITY-LANE do not depend on this, and may run
concurrently in other tabs — they own disjoint paths.
