repo: charon-private
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: feat/discovery-diff
depends_on:
owns: fleet/discovery/offer_diff.py
note: |
  D3 of the DISCOVERY leg AND the SHARED diff/drift algorithm (FREE-PROVIDER-DISCOVERY-DESIGN §3b/§4,
  operator-approved P1, 2026-07-23). This IS the "diff algorithm reused by R17 + discovery" — factor it
  ONCE. Do NOT implement drift twice: R17 (PRICING-LIMITS-CHECK-SH, configured-provider price drift) and
  discovery (community-listed drift) are two callers of this one signed-delta differ. money-path: a wrong
  delta mis-orders spend or misses a price hike. [[always-fix-catalog-mismatches]]
accept: |
  A signed-delta differ (§3b), keyed on (provider, normalized_model via _normalize_model_id), comparing a
  fresh normalized snapshot to (1) the persisted prior snapshot AND (2) fleet/config-manifest.tsv:
    1. **ADDED** = in new ∧ not in old ∧ not in config-manifest -> `CANDIDATE` (free/trial = high interest;
       cheaper-than-incumbent paid = medium).
    2. **REMOVED** = in old ∧ not in new -> configured provider gone from its own /models = OUTAGE-RISK RED;
       community-only listing dropping = informational.
    3. **CHANGED** = both, field delta, DIRECTION-SIGNED (operator cares only about WORSE): free-tier
       rpd/rpm/tpm/tpd decreased, or cost_in/out increased >= %-threshold, or free->paid, or personal_only/
       trains_on_data flipped adverse -> DRIFT ALERT (the NeuralWatt $5->$10 2x class, generalized);
       improved -> OPPORTUNITY note (lower urgency).
    4. **CROSS-CHECK** = for a CONFIGURED provider, community-listed price/limit vs R17's measured value ->
       disagreement = a data-quality flag into R17.
  Determinism: numeric threshold + %-change on price/limit fields only (mirrors the changedetection.io
  pattern from PRICING-TOOLS-EVAL §B); cosmetic churn (description, ordering) is NOT a diff field.
  BUILT TO ALSO SERVE R17 — a public entrypoint R17/PRICING-LIMITS-CHECK-SH can call (co-design).
  FAIL-ON-REVERT: inject a price hike / limit cut in a fixture snapshot -> DRIFT ALERT fires; revert the
  signed-delta logic -> the case goes RED.
  NON-VACUOUS: diffing two IDENTICAL non-empty snapshots must report "0 deltas over N keys" with N proven
  > 0; a diff over ZERO keys must RED, never green.
  RUNNER-REACHABLE: the red-proof must be EXECUTED by a real runner (fleet/gate.sh's
  `fleet/tests/*.test.sh` glob or rig-ci-scope.sh CI_SUITES) — a proof no runner runs is not evidence.
scope: |
  The shared signed-delta differ (§3b): NEW/CHANGED/GONE with severity + %-thresholds, vs prior snapshot +
  config-manifest, keyed on router identity. One implementation, two callers (discovery + R17). No pull/
  normalize (D1/D2), no queue (D4).
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. The DISCOVERY-NORMALIZE edge was REMOVED 2026-07-24 and it was NOT a real build
    prereq: D3 reads a §3c-column TSV snapshot, and those columns are fixed by
    FREE-PROVIDER-DISCOVERY-DESIGN §3c and committed as a FIXTURE by D2 — this ticket's own red-proof
    injects a price hike into a FIXTURE snapshot and never executes normalize.py. Owns are disjoint
    (offer_diff.py vs normalize.py + discovery-inventory.tsv). It was a DATA-FORMAT contract, satisfied
    by the spec, not a code dependency; as a board edge it only serialized two agents for no reason.
    Both legs must agree on the §3c header — that is a review item, not a blocker.
  - Co-design with R17 (PRICING-LIMITS-CHECK-SH) which becomes the second caller — do not implement
    drift twice.
  - feeds: DISCOVERY-QUEUE (D4) consumes NEW/CHANGED/GONE; R17 consumes the same differ for configured drift.
  - reuse: config-manifest.tsv (diff target), _normalize_model_id, changedetection threshold pattern.
  - concurrency: disjoint new file fleet/discovery/offer_diff.py (R17 owns fleet/pricing-limits-check.sh —
    separate file; this ticket exposes the callable, R17 wires to it in its own ticket). Safe to build in
    parallel with D2/D4/D5/D6 — no shared file with any of them.
  - UN-BUNDLED 2026-07-24: briefly absorbed into a DISCOVERY-PIPELINE mega-ticket; reverted. Grouping is
    one ROADMAP wave (`discovery-leg`) at one priority, not one serial ticket.
