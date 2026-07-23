repo: charon-private
tier: strong
difficulty: 3
work_class: money-path
priority: 1
branch: feat/discovery-diff
depends_on: DISCOVERY-NORMALIZE
dep-kind: build
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
  FAIL-ON-REVERT: inject a price hike / limit cut in a fixture snapshot -> DRIFT ALERT fires; revert -> green.
scope: |
  The shared signed-delta differ (§3b): NEW/CHANGED/GONE with severity + %-thresholds, vs prior snapshot +
  config-manifest, keyed on router identity. One implementation, two callers (discovery + R17). No pull/
  normalize (D1/D2), no queue (D4).
ds: |
  ## Dependencies & sequence
  - depends_on: DISCOVERY-NORMALIZE (real build dep — diffs its normalized snapshot). Co-design with R17
    (PRICING-LIMITS-CHECK-SH) which becomes the second caller — do not implement drift twice.
  - feeds: DISCOVERY-QUEUE (D4) consumes NEW/CHANGED/GONE; R17 consumes the same differ for configured drift.
  - reuse: config-manifest.tsv (diff target), _normalize_model_id, changedetection threshold pattern.
  - concurrency: disjoint new file fleet/discovery/offer_diff.py (R17 owns fleet/pricing-limits-check.sh —
    separate file; this ticket exposes the callable, R17 wires to it in its own ticket).
