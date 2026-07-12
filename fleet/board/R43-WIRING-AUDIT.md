tier: strong
difficulty: 3
work_class: design-review
branch: audit/r43-wiring-audit
depends_on:
owns: /home/stack/charon-private/fleet/state/WIRING-AUDIT-MATRIX.md
accept: |
  READ-ONLY sweep of the charon gateway/product for BUILT-BUT-INERT features → a wired/inert matrix doc.
  DO NOT edit product code. Produce fleet/state/WIRING-AUDIT-MATRIX.md: one row per built capability with columns
  {feature | defining file:line | constructed? | INVOKED on a real request path? | verdict WIRED/INERT | evidence path:line}.
  Must at minimum classify and cite (code-confirmed, path:line — do NOT trust docstrings):
  - the per-provider cost METER / BalanceTracker (standing #1 remediation — is it ever constructed from config? does
    record_spend fire? is the ledger written?),
  - SpeculativeExecutor + ConsensusRouter (SR-4-confirmed constructed-but-never-invoked in _handle()),
  - any Smart-Routing module in gateway's _module_inst ladder that is instantiated but has no live call site.
  For each INERT item: the ONE wiring change that would make it live, and which downstream ticket should own it
  (feeds R44 dogfood-gate / R45 inert-startup-check / R46 balance-wire scoping).
  FAIL-ON-REVERT: n/a for a read-only audit — instead the completeness bar is: EVERY row carries a code path:line for
  its "invoked?" verdict (no prose-only claims), and the meter/executor/consensus rows are all present. A row asserting
  WIRED without a call-site path:line is INCOMPLETE → reject.
  GREEN-IS-NOT-PROOF: "the tests pass" does NOT prove a feature is wired — a built-but-never-invoked module has no
  failing test. The audit's proof is a reachable call-site citation per WIRED verdict, and a confirmed 0-caller
  citation per INERT verdict.
scope: |
  ROUTER Wave 3 — pull to the FRONT. Cheap, read-only, zero owns-collision; de-risks the whole ROUTER project in
  one pass by enumerating the inert surface ONCE instead of R44/R45/R46 each re-discovering it. Source: QUICKWINS-LEVERAGE.md #2.
  [[charon-meter-inert]] [[charon-work-engine-vision]]
ds: ROUTER Wave 3. depends_on EMPTY — launch NOW. Owns a NEW fleet/state doc → zero owns-collision; safe to run fully
  concurrently with every other ticket in this wave.
