repo: charon-private
tier: frontier
difficulty: 3
work_class: rig-meta
branch: audit/on-demand-tools
serial_justified: One cohesive classification pass over the tool inventory into a single ledger; nothing independent to parallelize.
owns: fleet/state/ON-DEMAND-TOOL-LEDGER.tsv
depends_on:
note: |
  Applies [[dynamic-tools-never-on-demand]] as an AUDIT (operator directive, cere-junda). Find EVERY
  tool that violates it: (a) set/hardcoded to run ON-DEMAND only, (b) has NO trigger/cadence, or
  (c) has NEVER or RARELY run. A dynamic-data tool must have a cadence + multiple smart triggers +
  be tested/dogfooded — these are the offenders to mechanize (or retire if genuinely dead).
  EXTEND, don't redo: fleet/state/TOOL-WIRING-AUDIT.md already found several under-wired tools
  (foreman/memory/config-drift/dark-work/launch-plan/catalog-detector) — fold those in, add the
  "never/rarely run" dimension.
accept: |
  ## Method
  - Enumerate tools: TOOL-INVENTORY.md + fleet/*.sh + fleet/checks/*.sh + tools/*.py + key src/charon/*.
  - For EACH, determine invocation reality by EVIDENCE (grep callers across fleet/tools/settings.json;
    check for a cadence/cron/SessionStart/preflight/land/handoff trigger; check run-markers/logs/git
    history for last-run / never-run). Do NOT trust docstrings.
  - Classify: MECHANIZED (cadence+≥1 trigger) | ON-DEMAND-ONLY (no trigger) | NO-TRIGGER | NEVER-RUN | RARELY-RUN | DEAD(retire).
  ## Output fleet/state/ON-DEMAND-TOOL-LEDGER.tsv
  Row per tool: tool | invoked-how (evidence) | classification | dynamic-data? (Y/N) | fix (cadence+triggers to add, or RETIRE) | priority.
  Rank by impact. A dynamic-data tool that is ON-DEMAND/NO-TRIGGER/NEVER-RUN is a mechanization gap -> propose the cadence + specific triggers per [[dynamic-tools-never-on-demand]].
  ## Then
  - Board the top offenders' mechanization (or fold into FOREMAN-MULTI-TRIGGER / GRAPHIFY-MAP-FRESHNESS if already covered). No net-new tools without a reuse-check.
