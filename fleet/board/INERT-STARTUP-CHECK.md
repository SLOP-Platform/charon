repo: charon
tier: strong
difficulty: 3
work_class: tests
priority: 0
branch: feat/inert-startup-check
depends_on: GATEWAY-NONTOKEN-METERING, WIRE-GRADING-PRIOR-LIVE
real-dep: GATEWAY-NONTOKEN-METERING, WIRE-GRADING-PRIOR-LIVE — both are single-owners of
  src/charon/gateway.py, which is where a STARTUP self-check must ultimately be invoked. Four tickets
  claim that file. This ticket owns the CHECK MODULE only and must land its gateway wiring on top of
  theirs, never beside it. dep-kind: build.
dep-kind: build
owns: src/charon/startup_check.py, tests/test_startup_check.py
serial_justified: |
  ONE self-check module plus its proof. Owning the module but not gateway.py is deliberate: the wire
  point is contended by four tickets, and becoming a fifth concurrent writer is the collision class
  this fleet ticketed an arbitration for today.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Own worktree.
source: |
  Roadmap R45, unbuilt since Wave 3. Escalated to P0 by operator 2026-07-26 (decision 33).
note: |
  ## WHY — inert code is this system's dominant failure mode, repeatedly
  Verified instances on 2026-07-26 alone:
  * SIX gateway modules constructed at startup with ZERO invocation sites (RequestInspector,
    SessionAffinity, Observability, SpeculativeExecutor, ConsensusRouter, VirtualKeyManager).
  * The capability-grading prior: `SEED_PRIOR`/`seed_matrix()` have ZERO production consumers; the
    gateway builds a BARE EMPTY `CapabilityMatrix()`.
  * The meter: `remaining_usd: null` for every provider, `cost_usd` $0.0007 against 252M tokens.
  * The rig grading read: `assign.py` REFUSED every ticket because 0 rows passed a control filter.
  Every one looked healthy from outside. **Silence is this system's characteristic failure — not
  crashes.** A component that is constructed but never called is indistinguishable from a working one
  until someone audits by hand.

  ## WHAT IT MUST DO
  At startup, emit an explicit ACTIVE vs INERT inventory of optional components and FAIL LOUD (or at
  minimum log unmistakably) when something is constructed-but-unwired.
  **The distinction that matters, and that our existing detector gets WRONG:**
  `tools/check_inert_code.py` clears all six dead modules because it sees their `_MODULE_SPECS`
  registration. **Reachability-via-registry is NOT reachability-on-the-request-path.** This check must
  make that distinction or it reproduces the same false comfort.

  ## SCOPE BOUNDARY
  Own `startup_check.py` and its test. Do NOT edit `gateway.py` — it has four claimants. Deliver the
  module plus the EXACT wiring snippet the gateway owner should apply, and say where. If you believe
  the check cannot work without editing gateway.py, STOP and report rather than editing it.
accept: |
  DONE-CONTRACT:
  - The check correctly classifies all SIX known-dead modules as INERT. That is the fixture — a
    version that does not flag all six is not done.
  - It correctly classifies genuinely-wired components (spend_limiter, guardrails, semantic_cache,
    observer, quality_scorer) as ACTIVE. No false positives.
  - RED-PROOF BY EXECUTION: wire one dead module in -> it flips to ACTIVE; unwire a live one -> it
    flips to INERT. Report BOTH exit codes.
  - NON-VACUOUS: a check that inspects zero components is RED.
  - The exact gateway.py wiring snippet is provided but NOT applied. Confirm gateway.py is unmodified.
  - `PYTHONPATH=src python3 -m charon.cli gate` GREEN and `pytest -q` GREEN.
## Dependencies & sequence
- **Depends on:** the two live gateway.py owners (see real-dep). The MODULE is startable immediately;
  only its wiring waits.
- **Blocks:** nothing formally. Practically it is the alarm for the failure mode that has cost this
  project the most time.
- **Wave:** gate lane, P0.
