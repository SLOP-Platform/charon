# SG-ISSUE-CONTROL-PLANE — review-log fragment

Author model: deepseek-v4-pro
Reviewer: operator (per DESIGN umbrella — build-slices get adversarial review; the design is operator-reviewed)

## Self-review notes

1. **Completeness.** All 7 failure classes are enumerated with desired-source, actual-source, drift-algorithm, RED condition, and heal-template classification. The 3 build-slices are file-disjoint and ordered by data-flow dependency (SURFACE → DISCOVERY → SELF-HEAL).

2. **Adopt-first posture (§7).** Four patterns are explicitly cited (StackStorm sensor→rule→action, ArgoCD opt-in self-heal, K8s level-triggered, Backstage/Dagster scorecard/freshness). Each has a "why not the tool" justification. The ~15% novel build is the thin bash/python glue.

3. **KS20 anti-accretion.** Per-class detectors are registry rows; per-class heal-templates are registry rows; future classes are data appends, not scripts. The schema supports this.

4. **Gating (§5).** Safe-vs-NEVER classes are explicitly listed. The gate is data in heal-templates.tsv, not hard-coded. The circuit breaker (`ReviewerCircuitBreaker`) is reused from BLAST-TIER-ENFORCEMENT.

5. **fail-on-revert (§8).** One dogfood per slice + the plane's own plane-canary row. The plane is a meta-checker; its own false-green is the worst-case failure mode.

6. **Open seams flagged (§9).** Graphify dependency, review-pool dependency, preflight bypass — each with explicit mitigation. None are faked-closed.

7. **Integration with UNIFIED-RECONCILIATION-GATE.** The design explicitly folds DISCOVER+SURFACE into the existing reconciliation gate axis (§0, §3.3). The issue-board is the convergence point for all existing detectors and reconcilers.

## Known gaps (accepted)

- The exact schema of `issue-class-registry.tsv` is defined in §2 (7 columns documented), but the KS29 DISCOVERY-LEG build ticket must land the precise tsv + the primitive implementations. The design is the contract; the build is the implementation.
- The `graph-reachability` primitive is novel and depends on graphify's bash+python extractors. The quality of the reachability walk is bounded by graphify's extractor quality. Documented as an OPEN SEAM (§9.1).

## Verdict: CONFIRMED-CLEAN (design-only — operator approval required before build slices spawn)
