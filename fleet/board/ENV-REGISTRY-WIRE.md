repo: charon-private
tier: strong
difficulty: 2
work_class: ci-infra
branch: feat/env-registry-wire
depends_on: SESSION-CTX-PROPAGATE
real-dep: SESSION-CTX-PROPAGATE — the registry is surfaced to sub-agents THROUGH the preamble-injection mechanism CTX-PROPAGATE builds; it must exist to plug into. (Primary-side SessionStart wiring is coordinated with STARTUP-CONTEXT-DIET / SYNC-SCHEDULE, which own session-start.sh — do NOT edit that file here.)
owns: fleet/env-registry.sh, fleet/tests/env-registry.test.sh
accept: |
  Kill env-fact spelunking (gateway URL/key-ref, live served models, tier->model map, host map) — the exact rediscovery that
  cost this session multiple probes. A LIVE registry ALREADY EXISTS — fleet/state/CG-PROVIDERS.md (gateway-probe-sourced) —
  but is never surfaced (built-but-not-consulted). REUSE it; do not rebuild (see fleet/state/SESSION-RECALL-CHALLENGE.md).
  DO:
  - fleet/env-registry.sh: refresh/emit a COMPACT live env-registry from the gateway probe + tier-models.tsv (endpoint,
    served models, tier->model, host map). Prefer refreshing CG-PROVIDERS.md over a new file.
  - Surface it at SessionStart (primary) AND via the SESSION-CTX-PROPAGATE preamble (sub-agents). Keep it small.
  FAIL-ON-REVERT (fleet/tests/env-registry.test.sh): the surfaced registry lists the live served models + gateway endpoint
  (revert → absent → test fails). NON-VACUOUS: zero served models = RED, never a silent empty pass.

reuse: LEVERAGE PROVIDER-CATALOG-REFRESH (keeps model->provider current) + the existing fleet/state/CG-PROVIDERS.md — this ticket only SURFACES env facts to sessions/sub-agents; do NOT rebuild the catalog.
