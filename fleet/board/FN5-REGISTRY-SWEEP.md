tier: economy
difficulty: 3
work_class: ci-infra
branch: feat/fn5-registry-sweep
repo: charon-private
depends_on:
owns: /home/stack/charon-private/fleet/state/REGISTRY-CANDIDATES.md
accept: |
  AUDIT (then apply): sweep the charon PRODUCT + fleet RIG + KSF for "smart module registry" candidates — sites
  where a data-driven registry would replace accretion-prone code so that adding a thing = 1 data row + 1 file
  with ZERO edits to a central file. Patterns to find:
  - if-ladders / type-dispatch chains (e.g. the gateway `_module_inst` if-ladder),
  - mega config objects (GatewayConfig-style N-field passthrough),
  - N-owner god-files (from `bash fleet/wci-actions.sh` collision hotspots),
  - hardcoded lists that keep growing (providers PRESETS, model catalog, deny-lists, gate lists),
  - per-instance proliferation (one script per pattern/gate — KS20/KS28 territory).
  REUSE-CHECK (hard): apply the EXISTING **KS29 component-registry-primitive** (declare registry → conformance +
  discovery + drift). Do NOT hand-roll a new registry per site. For each candidate: current pattern → registry
  conversion → the collision/accretion class it eliminates → effort. RANK by leverage.
  Candidate #1 = the Smart-Routing module registry (F29, already ACCEPTED). Output feeds F29, KS20 anti-accretion,
  KS28 pattern-guard.
scope: Audit-first (discovery), then per-site conversions become their own tickets/PRs. This is the anti-accretion
  generalization of the F29 finding — it turns a one-file fix into a platform-wide structural pattern.
ds: FOUNDATION Wave C (anti-accretion). Reuses KS29 primitive + wci-actions.sh collision data. Owns a NEW audit
  file → no owns-collision. Best run AFTER FN4 research-gate exists (so the audit itself is reuse-check + evidence gated).
