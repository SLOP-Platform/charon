repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-tier-canon
depends_on: EVAL-TAXONOMY-ALIGN
dep-kind: build
serial_justified: one canonical tier axis defined once + repointing tier-models.tsv and assign.py's filter to it is atomic; two tier definitions live at once is the bug being fixed.
owns: fleet/tier-models.tsv, fleet/capability/assign.py, fleet/state/TIER-CANON.md
accept: |
  Review F-tier: "tier-appropriate difficulty" is UNDEFINED and tier boundaries are inconsistent/unenforced across
  tier-models.tsv, assign.py, and the ladder. DEFINE ONE canonical tier axis (the COST band is the meaningful one for
  routing) with a concrete rule.
  DO:
  - fleet/state/TIER-CANON.md: define the canonical tiers (economy/strong/frontier) by an OBJECTIVE cost-band rule
    ($/Mtok thresholds), and define "tier-appropriate difficulty" concretely (which item-bank difficulty levels a tier's
    rungs draw from). State whether rungs and tiers are the SAME axis, orthogonal, or how they map (the review flags
    they're currently conflated). DISAMBIGUATE two distinct "tier" meanings that must NOT be conflated: the
    COST-BAND tier (an INPUT — how expensive a model is, defined here) vs the CEILING-GRADE band (an OUTPUT of
    EVAL-PIPELINE-CONSOLIDATE/F9 — how capable a model proved). TIER-CANON.md owns the cost-band definition;
    state explicitly how the capability-ceiling output maps back onto (or is independent of) the cost band.
  - Repoint tier-models.tsv + assign.py's tier filter to the canonical rule (assign.py:14 tier filter currently no-ops
    for uncatalogued ids — F-tier/MED — make an uncatalogued id resolve its tier from the cost band, not silently pass).
  FAIL-ON-REVERT (extend assign tests): a model priced in the economy band resolves tier=economy even if uncatalogued
  (revert → it no-ops/mis-tiers → test fails); a --tier strong query excludes a frontier-priced model. TIER-CANON.md's
  band thresholds are the single source (drift guard: assign.py reads them, doesn't hardcode).
