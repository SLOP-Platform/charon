tier: frontier
difficulty: 4
work_class: money-path
branch: feat/router-core
depends_on: METER-MODEL-PROVIDER, COST-RANK-AUTO
owns: src/charon/router.py, src/charon/failover.py, src/charon/routing_policy/, fleet/state/capability-matrix.json
accept: |
  Per-model provider selection is SORTED CHEAPEST-FIRST from the REAL metered cost (not hand-typed
  order), and fails over to the next provider when the current one is: (1) EXHAUSTED (401/429/credit=0/
  quota), (2) HAS A PROBLEM (capability/correctness — e.g. reasoning_content breakage, model-downgrade),
  or (3) TOO SLOW (latency > threshold). Caller sees a stable endpoint; switching is invisible.
  Fail-on-revert tests, each:
    - cost-sort: given metered costs, the chain orders cheapest-first (revert -> wrong order).
    - exhausted: 401/429 -> next provider (exists; keep covered).
    - problem: a provider flagged reasoning-incapable for a model is SKIPPED for thinking-mode requests
      (capability-matrix entry openrouter/Novita ✗ reasoning_content); revert -> it gets picked and breaks.
    - slow: a provider over the latency threshold is deprioritized/failed-over.
    - safety floor: when price/health unknown, a deterministic static chain is used (never no-net).
scope: |
  Design of record: fleet/state/ROUTER-DESIGN.md. This is the DECIDE stage of the sense->decide->act
  routing loop (SENSE = METER; ACT = gateway failover). Consolidated under PROJECT ROUTER.
  Sub-deliverables tracked as sibling ROUTER tickets: capability-matrix (R3), latency-signal (R8),
  cost-rank-auto (R5, the price signal). [[charon-pools-redesign]] [[charon-work-engine-vision]]
ds: money-path; sequence AFTER meter-wire (R4/K2) lands the real cost signal. Prereq: METER (done).
