repo: charon-private
tier: strong
difficulty: 2
work_class: money-path
priority: 1
branch: feat/discovery-approval-wire
depends_on: ADD-PROVIDER-MECHANIZE-COMPLETE
dep-kind: build
owns: fleet/discovery/approval_wire.sh
note: |
  D5 of the DISCOVERY leg (FREE-PROVIDER-DISCOVERY-DESIGN §3e/§4, operator-approved P1, 2026-07-23). The
  GLUE from an approved queue row to the money path — the SAFETY BOUNDARY: discovery proposes, a human+eval
  disposes, and ONLY the existing mechanized add crosses into config. REUSE-FIRST: compose
  benchmark/dogfood-eval.sh (real-work trust test) + fleet/add-provider.sh (ADD-PROVIDER-MECHANIZE-COMPLETE)
  — do NOT build a new actuator. NO auto-apply. [[real-work-is-the-trust-test]] [[security-is-a-ratchet-gate]]
accept: |
  Human-in-loop glue: an OPERATOR-APPROVED discovery-review.tsv row must clear ALL of, in order, before it
  touches config:
    1. **ToS/eligibility** — surface personal_only / trains_on_data; free tiers flagged PERSONAL-use-only
       per [[charon-free-tier-routing]]. Operator confirms fit.
    2. **Real-work eval** — `benchmark/dogfood-eval.sh` on a live small ticket (NOT synthetic smoke).
    3. **Actuate via the mechanized add** — only on PASS, hand the row to `fleet/add-provider.sh`
       (ADD-PROVIDER-MECHANIZE-COMPLETE: sets funding_class + real costs + routable-not-just-visible verify).
       After add, the provider is a normal configured provider owned by catalog_refresh + R17 + cost-rank.
  NEVER auto-wire: no path from queue -> add without the human confirm + eval PASS. Rejected rows stay
  status=rejected with reason.
  FAIL-ON-REVERT: an un-approved (or eval-FAIL) row must NOT reach add-provider.sh; wire a bypass -> RED.
  NON-VACUOUS: a run that evaluated ZERO approved rows must report `examined 0 rows` and RED, never a
  silent green — a safety boundary that proves nothing is not a boundary.
  RUNNER-REACHABLE: the red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  `fleet/tests/*.test.sh` glob or rig-ci-scope.sh CI_SUITES).
  ADVERSARIAL REVIEW REQUIRED (reviewer != builder): this is the ONLY path from discovery into config.
  Confirm BY EXECUTION that the bypass case is RED.
scope: |
  Compose dogfood-eval + add-provider.sh into the approval actuation glue (ToS check -> real-work eval ->
  mechanized add), human-in-loop, no auto-apply. Reuses existing tools; builds only the glue.
ds: |
  ## Dependencies & sequence
  - depends_on: ADD-PROVIDER-MECHANIZE-COMPLETE only — a REAL build dep, KEPT: D5's whole contract is
    "actuate through the EXISTING mechanized add and build no second actuator", so it hands rows to a
    fleet/add-provider.sh whose funding_class + real-cost + routable-verify behaviour that ticket is
    still completing. Wiring to the un-completed actuator would ship a money-path boundary that trusts
    behaviour that does not exist yet. BUILT (feat/add-provider-mechanize-complete, PR #186) and
    UNLANDED — the edge clears by LANDING.
  - The DISCOVERY-QUEUE edge was REMOVED 2026-07-24 and it was NOT a real build prereq: D5 reads
    APPROVED rows out of discovery-review.tsv, a TSV whose status column set is specified in
    FREE-PROVIDER-DISCOVERY-DESIGN §3e; the red-proof supplies hand-written approved / un-approved /
    eval-FAIL fixture rows and never executes queue.py. Owns are disjoint (approval_wire.sh vs
    queue.py + discovery-review.tsv). Data-format contract, not a code dependency.
  - reuse: benchmark/dogfood-eval.sh, fleet/add-provider.sh, config-manifest.tsv (the SSOT add-provider writes).
  - concurrency: disjoint new file fleet/discovery/approval_wire.sh (add-provider.sh owned by its own
    ticket — D5 only CALLS it). Safe to build in parallel with D2/D3/D4/D6.
  - UN-BUNDLED 2026-07-24: briefly absorbed into a DISCOVERY-PIPELINE mega-ticket; reverted. Grouping is
    one ROADMAP wave (`discovery-leg`) at one priority, not one serial ticket.
