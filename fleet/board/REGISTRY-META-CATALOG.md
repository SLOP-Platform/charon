repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/registry-meta-catalog
owns: fleet/state/registry-catalog.tsv, fleet/checks/discover-registries.sh, fleet/tests/registry-catalog.test.sh
depends_on:
serial_justified: the catalog, its auto-discovery, and the conformance/discovery gate are ONE primitive —
  an index nobody keeps current, or one with no discovery leg, just recreates the "can't find the registries"
  problem it exists to solve.
source: |
  operator directive 2026-07-24 (approved option B). We have many registries (tier-models, plane-canary,
  reconciler, service-registry, SSOT, catalog/providers, jedi-name-pool, lessons/reds, ...) and no easy way
  to find them. Folds under KS29 component-registry-primitive; FN5 registry-sweep (DONE) already produced the
  candidate list this catalogs. HARD operator constraint: MUST NOT become a god-file or a merge/ownership
  bottleneck.
note: |
  A registry OF registries — the KS29 primitive applied recursively (Backstage software-catalog pattern).
  INDEX, not container: it lists the registries themselves (name | purpose | path | schema | owner |
  conformance_gate), NOT their contents. Each registry's data stays in its own file. It grows with the NUMBER
  of registries (~a dozen), never with their entries — so it can't become a god file, and editing a registry's
  data never touches it.
  AUTO-DISCOVERED: populate by scanning for registry files/descriptors by convention (or a small self-describing
  descriptor beside each registry) rather than hand-maintaining a central file — that kills the sync chokepoint.
  DISCOVERY leg (fail-closed): a registry present on disk but absent from the catalog -> alarm.
accept: |
  - fleet/state/registry-catalog.tsv is INDEX-ONLY (metadata/pointers) — a test asserts it holds NO registry's
    data rows (anti-god-file guard).
  - AUTO-DISCOVERED: discover-registries.sh finds registry files by convention and reconciles them against the
    catalog; a registry on disk not in the catalog -> FAIL-CLOSED (the discovery leg).
  - grows with # registries, not entries (structural: the schema has no data-value column).
  - first catalogued entry = SERVICE-LIVENESS-WATCHDOG's fleet/state/service-registry.tsv.
  - WIRED: a gate runs discover-registries.sh (firing layer), not inert.
  - fail-on-revert: remove a registry from the catalog while it's on disk -> discovery gate goes RED.
  - ADVERSARIAL REVIEW (reviewer != builder).
scope: |
  The index + auto-discovery + conformance/discovery gate ONLY. Explicitly does NOT move any registry's DATA
  into it (that would be the god-file the operator forbade). Does not build new registries — it catalogs
  existing ones. Pairs with SERVICE-LIVENESS-WATCHDOG (whose service-registry is catalog entry #1).
ds: |
  ## Dependencies & sequence
  P0. Folds under KS29 (component-registry-primitive); FN5 (registry-sweep) is DONE and produced the candidate
  registries. No hard prereq. Natural pair with SERVICE-LIVENESS-WATCHDOG.
