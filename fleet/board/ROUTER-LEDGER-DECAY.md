repo: charon-private
tier: economy
priority: 3
difficulty: 3
work_class: routing
branch: feat/router-ledger-decay
owns: src/charon/routing_policy/ledger_decay.py, tests/test_ledger_decay.py
serial_justified: One self-contained router-side decay module + its test; nothing else touches the model-signal ledger weighting, so there is nothing to parallelize.
depends_on:
note: |
  EXTRACTED INTENT from the retired inert fleet/memory/bitemporal.py (deleted in
  FN-MEMORY-RETIRE-ADOPT). That module was a hand-rolled bitemporal exponential half-life decay
  (BitemporalRecord + bitemporal_weight, model_signal_weight, apply_model_signal_decay) that was
  NEVER wired to the router — only its own test imported it. Its real target was "gap B2": decay the
  routing MODEL-SIGNAL ledger so stale benchmark/outcome signals lose weight over time (half-life,
  last_referenced-aware). Retiring the inert copy forfeited that unbuilt intent, so it is re-opened
  HERE as an explicit ROUTER-side concern rather than kept on life-support in fleet/memory/.
  This is a build-when-needed ticket: the router does not yet consume time-decayed model signals; wire
  it only when the actuals/model-signal ledger is the live ranking input and staleness demonstrably
  skews routing. Reference impl to salvage from git history: bitemporal.py @ pre-retire (half-life
  exp2 decay, tz-aware, valid_from/valid_until/learned_at/last_referenced anchoring).
accept: |
  BUILD (when the model-signal ledger is a live router input): a router-side decay function that
  weights each model-signal entry by an exponential half-life of its age (default ~30d, configurable),
  anchored on learned_at/last_referenced, so stale signals decay toward zero. Wire it into the ranking
  path that consumes the model-signal/actuals ledger (NOT into fleet/memory/ — this is router code).
  FAIL-ON-REVERT: a test asserts an old signal is down-weighted vs a fresh one of equal raw score, and
  that the decay is actually applied in the router ranking path (not just defined).
  GREEN-IS-NOT-PROOF: demonstrate a routing decision that flips (or a rank that changes) BECAUSE a
  stale model signal decayed — not merely that the math function returns a smaller number.
scope: Router-side model-signal ledger decay only. Pure-stdlib math is fine (the retired reference was
  math-only); do NOT resurrect fleet/memory/ or couple this to session memory — those are unrelated.
ds: |
  Dependencies & sequence:
   1. Gated on the model-signal / actuals ledger being the LIVE ranking input — build only then.
   2. Independent of FN-MEMORY-RETIRE-ADOPT once that lands (this ticket holds the extracted intent so
      the retire could delete bitemporal.py atomically without losing gap-B2).
   Does NOT depend on session-memory / basic-memory work.
