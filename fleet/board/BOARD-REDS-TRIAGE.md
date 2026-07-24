repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: rig-meta
branch: feat/board-reds-triage
depends_on: 4LOM-CANARY-SERVICE
real-dep: 4LOM-CANARY-SERVICE — consumes its canary-report.tsv slow-vs-broken attribution to know which reds are genuine (vs slow false-reds); cannot disposition without it
owns: fleet/state/gate-red-disposition.tsv, fleet/reds-triage.sh, fleet/tests/reds-triage.test.sh
serial_justified: the disposition ledger + the "every genuine red is dispositioned or it's flagged" gate are
  one anti-forgetting mechanism — a triage with no durable ledger just re-loses the reds it was meant to fix.
source: |
  operator directive 2026-07-24 — un-parked to be THE VEHICLE for the gate-test reds. Original #19 scope (5
  owns-collision board reds) is stale/superseded by board hygiene. New role: the 4LOM-CANARY-SERVICE surfaces
  the gate-test reds with slow-vs-broken attribution (~8 GENUINE, ~4 slow-timeout FALSE-reds); this ticket turns
  each GENUINE red into a tracked disposition so surfaced reds stop getting forgotten (the recurring failure).
note: |
  Consumes fleet/state/canary-report.tsv (from 4LOM-CANARY-SERVICE). For each BROKEN (genuine) red: fix inline
  if trivial, else mint a fix ticket, else accept-with-reason — recorded in fleet/state/gate-red-disposition.tsv.
  The SLOW (rc=124 timeout) false-reds are recorded as slow, NOT chased as bugs and NOT silently treated as red.
  Principle: no silent red ([never-ignore-preexisting-issues]). A NEW genuine red in the canary report with no
  disposition is flagged (fail-loud) — so canary FINDS, this DISPOSITIONS, nothing rots.
accept: |
  - every BROKEN gate-test red in the canary report is dispositioned (fix / ticket / accept-with-reason) — none
    left silent; recorded in gate-red-disposition.tsv.
  - the SLOW false-reds are recorded as slow (not bugs); the count matches the canary's slow attribution.
  - a genuine red with no disposition -> reds-triage.sh fails LOUD (the anti-forgetting gate).
  - fail-on-revert; ADVERSARIAL REVIEW.
scope: |
  Dispositioning the canary's gate-test reds into tracked outcomes + minting fix tickets for the genuine ones.
  Does NOT build the canary (4LOM-CANARY-SERVICE) and does NOT itself deep-fix the reds beyond trivial — it
  ROUTES them to fixes and guarantees none is forgotten. The stale 5-owns-collision scope is retired.
ds: |
  ## Dependencies & sequence
  P0. depends_on 4LOM-CANARY-SERVICE (needs its honest slow-vs-broken attribution to know which reds are real).
  Pairing: the canary FINDS + attributes, this ticket DISPOSITIONS. Part of the "surface -> act, nothing rots"
  loop with ISSUE-BOARD-SURFACE.
