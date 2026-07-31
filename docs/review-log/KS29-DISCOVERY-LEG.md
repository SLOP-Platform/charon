# KS29-DISCOVERY-LEG — Review Log

## Ticket
KS29 (SG-ISSUE-CONTROL-PLANE slice 2): declare a component registry (schema + scope) and get,
for free, a CONFORMANCE gate (entries valid) + a DISCOVERY gate (FAIL-CLOSED on an unknown
component that SHOULD be registered) + a drift check. Uses graphify's code-relations graph
(9786 links) to auto-detect a NEW load-bearing subsystem/plane/entrypoint and REFUSE it until
it has a canary/detector or an explicit registered exemption.

## What was done
- **fleet/state/component-registry.tsv** (15 rows): canonical registry of load-bearing
  components/planes/subsystems/entrypoints/tools/gates. Tab-separated, 8 columns:
  component_id, kind, path, canary, test, status (registered|exempted), owner, note.
  Seeded with every plane from plane-canary-registry.tsv plus the tools and gates that
  are load-bearing for the fleet.

- **fleet/checks/registry-discovery.sh** (~290 lines): the DISCOVER leg gate. k8s-controller
  reconcile shape: LIST (read registry + graphify graph) -> DIFF (conformance + discovery +
  drift) -> ACT (report findings).
  - `check` subcommand: full reconcile (exit 0 GREEN / 1 RED)
  - `gate` subcommand: same with machine-readable GATE: prefix
  - `conformance`, `discovery`, `drift` subcommands: individual legs
  - `list` subcommand: machine-readable component listing
  - FAKE mode (REGISTRY_DISCOVERY_FAKE) for hermetic self-test
  - Load-bearing detection: regex-based pattern match on graphify node labels
    (plane, subsystem, gate, tool, detector, etc.) with anti-pattern exclusions

- **fleet/tests/registry-discovery.test.sh** (6 test cases, 17+ asserts): the
  FAIL-ON-REVERT self-test.
  - (1) HEALTHY: well-formed registry + all nodes registered -> GREEN
  - (2) CONFORMANCE: malformed row / invalid status / unknown kind -> RED
  - (3) DISCOVERY: unregistered load-bearing graph node -> RED (names it)
  - (4) RECONCILE: register the missing node -> GREEN (proves RED was data-driven)
  - (5) DRIFT: remove registered component's canary/test -> RED
  - (6) FAIL-ON-REVERT: fully-registered graph is GREEN, unregistered graph is RED —
    proves the RED is from the discovery check, not a coincidence

## Key decisions
- **k8s-controller reconcile shape (LIST -> DIFF -> ACT)**: The ticket demands this
  pattern. The three legs run sequentially and independently; each produces its own
  findings. A single RED finding in any leg fails the full gate.

- **Graphify integration via node labels, not subgraph analysis**: Graphify's graph.json
  contains 9786 links. The gate extracts all node labels and filters for load-bearing
  patterns via regex. A more precise subgraph-cluster analysis would be more accurate
  but would couple the gate to graphify's internal heuristics. The label-based approach
  is simpler, deterministic, and catches the important class of "brand new plane whose
  name contains a known load-bearing suffix."

- **Non-vacuous empty-registry guard**: An empty component-registry.tsv (or one with
  only header/comment lines) is RED — the gate cannot prove "nothing is missing" unless
  it has data to cross-reference. This follows the GATE-CREATION-STANDARD.md S2
  NON-VACUOUS rule.

- **FAKE-mode seam vs REGISTRY_FILE override**: Both exist. FAKE mode (REGISTRY_DISCOVERY_FAKE)
  replaces ALL file reads — registry, graph nodes, canaries — enabling fully hermetic
  tests. Individual env overrides (REGISTRY_FILE, GRAPHIFY_GRAPH) allow operator use
  against non-default paths without FAKE mode.

## Out of scope (intentionally not done)
- **Wire into preflight.sh / rig-ci-scope.sh**: The ticket says it's the HIGHEST-RISK
  new build; wiring into the production gate pipeline is a follow-up ticket once the
  primitive is accepted. The gate can run standalone today.
- **Subgraph-level discovery**: As noted above, the current approach labels nodes at
  the per-label granularity. A future ticket could add cluster/community detection
  to identify planes that span multiple labels.
- **Automatic exemption expiry**: Exempted rows carry a note but no expiry date
  enforcement. Future work could add a `tsv-append` field `exempt-until`.
