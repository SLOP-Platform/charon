repo: charon-private
tier: strong
difficulty: 2
work_class: money-path
priority: 1
branch: feat/discovery-approval-wire
depends_on: DISCOVERY-QUEUE, ADD-PROVIDER-MECHANIZE-COMPLETE
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
scope: |
  Compose dogfood-eval + add-provider.sh into the approval actuation glue (ToS check -> real-work eval ->
  mechanized add), human-in-loop, no auto-apply. Reuses existing tools; builds only the glue.
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-QUEUE (reads approved rows) + ADD-PROVIDER-MECHANIZE-COMPLETE (the actuator it
    hands off to). Both real build deps.
  - reuse: benchmark/dogfood-eval.sh, fleet/add-provider.sh, config-manifest.tsv (the SSOT add-provider writes).
  - concurrency: disjoint new file fleet/discovery/approval_wire.sh (add-provider.sh owned by its own ticket).
