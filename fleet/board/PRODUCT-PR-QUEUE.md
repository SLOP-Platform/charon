repo: charon
tier: frontier
priority: 1
difficulty: 4
work_class: money-path
branch: chore/product-pr-queue
depends_on:
owns: docs/review-log/PRODUCT-PR-QUEUE.md
serial_justified: |
  The product queue is money-path adjacent end to end — routing, pricing, catalog and provider
  keys all land through it. Reviews must be taken against one consistent view of the live
  catalog and provider set, which two concurrent reviewers would not share.
substrate: N/A
substrate-novel: |
  No tool adopted or built. The reviewer pool exists and is used as-is; what is missing is
  COVERAGE — the pool has been pointed at the rig repo while the product queue accumulated
  unreviewed PRs. This ticket supplies the missing lane, not a new mechanism.
accept: |
  14 open product PRs, at least 8 with ZERO reviews: #216 #215 #214 #212 #211 #210 #209 #208.
  Adversarial review each; money-path items are guilty until proven innocent.
  Known priors, verify do not assume:
   - #208 was BOUNCED as a strict no-op: the live catalog has 10 of 861 models priced so the
     sort key is degenerate, the chain is already sorted with the identical key at startup, and
     proxy_server.py full-sorts by EWMA latency immediately after, discarding cost order.
   - #210 adopts pylint W0613 for the defect class ruff ARG already covers. MEASURED: ruff
     --select ARG = 406 findings, pylint W0613 = 46. They are NOT equivalent; decide on evidence
     which single tool we adopt, do not assume duplication.
   - #215 enables ruff S and BLE — cross-check against the RUFF-SEC-RULES-ON chain so the two do
     not land conflicting pyproject.toml edits.
  For every safety claim, grep for the MECHANISM; for every suite, run it with the change
  REVERTED before believing it. Those two shapes accounted for 6 of 8 bounces on 2026-08-01.

## Dependencies & Sequence

No inbound deps; disjoint from the rig lanes (different repo). Sequence inside: money-path PRs
(#212, #211, #208) FIRST — pricing is upstream of every other routing decision — then the
lint/tooling PRs (#215, #210, #209), then docs (#216, #214).
