repo: charon-private
tier: economy
difficulty: 2
work_class: rig-meta
branch: feat/config-sources-tsv
owns: fleet/state/CONFIG-SOURCES.tsv, .gitignore
depends_on:
note: config-drift.sh is DEGRADED — it needs fleet/state/CONFIG-SOURCES.tsv (registry of config sources local~/.charon vs 4-LOM gateway /data) which is absent/gitignored. Create it + !-negate in .gitignore (like RULE-REGISTRY.tsv). This is what let a stale local-silo view mislead the manager (providers looked MISSING locally but are SET on the gateway).
accept: |
  - fleet/state/CONFIG-SOURCES.tsv exists with rows for the local + gateway config sources; !-negated in .gitignore.
  - bash fleet/config-drift.sh runs (no "registry not found") and reports local-vs-gateway provider drift.
