repo: charon-private
tier: frontier
priority: 0
difficulty: 4
work_class: money-path
branch: eval/hypothesis-failover
depends_on:
owns: fleet/state/HYPOTHESIS-FAILOVER-EVAL.md, docs/review-log/HYPOTHESIS-FAILOVER-EVAL.md
serial_justified: |
  One property-based evaluation against one failover implementation. Splitting it would produce
  two partial models of the same state machine that disagree.
substrate: N/A
substrate-novel: |
  This ticket IS a substrate evaluation and therefore cannot cite a prior adopt-verdict for the
  tool it is evaluating. VERIFIED 2026-08-02 - fleet/state/EVAL-REGISTRY.md has ZERO rows for
  Hypothesis, schemathesis, or any property-based testing tool. The deliverable APPENDS the
  missing rows.
execution: |
  Off-Claude, SG tab. EVAL lane - measure and report. Add no dependency to any shipped package;
  a scratch venv for running experiments is expected and encouraged. Change no routing code.
source: |
  Operator, 2026-08-02 - pair Hypothesis with pytest-bdd, specifically to validate failover pools
  by STATE OUTCOME rather than by mocking call order. Operator's stated mechanism - "No matter
  which provider in the pool throws a transient error, the gateway outcome must eventually return
  a valid 200 payload." Requested a DEEP feature review, not a surface view.
note: |
  ## THE PROBLEM THIS IS MEANT TO SOLVE — verify it is real before evaluating the cure
  Charon's gateway routes across upstream providers and fails over on error codes (429, 402, 503)
  and on latency. Mocking a STRICT CALL ORDER makes those tests fragile - every added or
  reordered provider breaks tests that assert HOW rather than WHAT.
  FIRST, CONFIRM the fragility is real in OUR code, not just in theory. Find the existing failover
  tests, count how many assert call ORDER or mock a specific provider chain, and quote two. If
  they are already outcome-shaped, say so - the case for Hypothesis weakens and you must report
  that honestly [[research-posture-solution-seeking]].

  ## REAL GROUND TRUTH ALREADY MEASURED TODAY — use it, do not re-derive
  These are live failure shapes from fleet/state/agent-logs (380 logs) and are exactly the kind of
  input a property test must survive -
    - Groq TPM ceiling - "Request too large ... on tokens per minute (TPM): Limit 8000, Requested
      44225" (16 logs).
    - Provider region opt-in - "only available hosted in China and requires explicit opt in" (12).
    - Whole-chain exhaustion - `CHARON_RUN_RESULT=EXHAUSTED` in 47 of 380 sessions.
  A property model that cannot express "every leg fails" is not modelling our reality - chain
  exhaustion is a REAL terminal state, so "eventually returns 200" is NOT universally true and the
  property must be stated correctly (e.g. "returns 200 OR a well-formed exhaustion result, never a
  hang, never a partial write, never a silent success").
  **Getting this property statement right is the single most valuable output of this ticket.**

  ## FEATURE-DEPTH REVIEW REQUIRED — surface comparison will be rejected
  Evaluate each with a RUN example against real or faithfully-stubbed failover code -
    - `@given` + strategies - can we generate provider pools, error-code sequences and latencies?
    - **`RuleBasedStateMachine` / stateful testing** - the most relevant feature by far. Model the
      gateway as a state machine (providers healthy/parked/cooled/capped) and let Hypothesis drive
      transitions. Show a working model, however small.
    - **Shrinking** - when it finds a failure, how minimal is the counter-example? This is the
      main practical payoff over hand-written fuzzing; demonstrate it on a seeded bug.
    - `@example` - pinning the REAL incidents above as permanent regression cases.
    - The example DATABASE - does a failure found in CI replay deterministically later? Where does
      the DB live, and does it survive our ephemeral CI checkout?
    - `assume()` / filtering, and the health-check failure mode when filters are too narrow.
    - DETERMINISM + runtime - property tests are slow and can flake on a time budget. Measure
      wall-clock for a realistic profile and state whether it fits a merge gate or belongs in a
      nightly lane. LATENCY IS A FAILURE CLASS here [[latency-is-a-failure-class]].
    - Interaction with pytest-bdd - can a `when` step drive a Hypothesis-generated example, or do
      the two fight? The operator wants them PAIRED, so this compatibility question is required,
      not optional. If they compose badly, say so plainly.

  ## THE LEDGER BOUNDARY — the operator's third mechanism
  Operator's design principle - assert on EXTERNAL ARTIFACTS (the Work Ledger JSON snapshot) as
  the vendor-neutral source of truth, rather than on live runtime internals. Evaluate whether
  property tests can assert purely against ledger state, and whether the ledger is complete enough
  to serve as the assertion surface. If the ledger is missing fields a property would need, LIST
  THEM - that is an actionable finding regardless of the adopt verdict.
accept: |
  DELIVERABLE `fleet/state/HYPOTHESIS-FAILOVER-EVAL.md` containing -
  a. A VERDICT - ADOPT / ADOPT-NARROW (named surfaces only) / DO NOT ADOPT. One line, up front.
  b. The CORRECTED property statement for failover, written precisely enough to implement,
     accounting for legitimate exhaustion. Include the properties you REJECTED and why.
  c. A per-feature table (the list above), each row backed by a RUN, not a doc quote.
  d. The fragility measurement - how many existing failover tests assert call order, with two
     quoted examples, or the finding that they do not.
  e. A working `RuleBasedStateMachine` sketch for the provider pool, even if small, plus the
     shrunk counter-example it produces against a deliberately seeded bug. A property framework
     that has never been SEEN to catch a real bug proves nothing [[gates-must-actually-run]].
  f. Wall-clock measurement and a recommendation on merge-gate vs nightly placement.
  g. The pytest-bdd composition answer.
  h. Ledger-as-assertion-surface answer, with any missing fields listed.
  i. EVAL-REGISTRY rows appended for every tool evaluated, in a SEPARATE EARLIER commit.
scope: |
  Evaluation and written verdict only. Changes no routing or gateway code, adds no dependency to
  a shipped package, converts no existing test. BDD framework choice belongs to
  BDD-FRAMEWORK-EVAL - reference it, do not duplicate it.

## Dependencies & Sequence

- **depends_on: none.** Reads the product repo, the live agent logs and public tool source.
- Runs in PARALLEL with BDD-FRAMEWORK-EVAL and KSF-PLUGIN-FRAMEWORK-RESUME. Disjoint owns.
- HARD PREREQUISITE IF ADOPT - `chore/remove-stdlib-only-prohibition` (`ca7d046`) must land before
  any dependency is added. Name it; do not do it here.
- Synthesised with the other two lanes by the MANAGER. Do not self-merge.
