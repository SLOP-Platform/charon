repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/graphify-map-freshness
serial_justified: One cohesive refresh-wiring + reuse-check surface around the code map; nothing independent to parallelize.
owns: fleet/checks/graphify-freshness.sh, fleet/tests/test_graphify_freshness.sh
depends_on:
note: |
  Code map goes STALE + causes DUPLICATE tools. graphify's graph (graphify-out/graph.json) is rebuilt
  ONLY on-demand (`graphify update <path>`); at cere-junda handoff the PRODUCT graph was 3 days stale
  (missing this session's failover_loop/context_shaper/memory/foreman/gh-cache) and the RIG had NO graph.
  So reuse-check / review that leans on graphify works from a stale map -> misses existing tools ->
  reinvention. Operator directives (cere-junda): (a) keep the map fresh automatically; (b) BEFORE building
  ANY new tool, audit existing tools (TOOL-INVENTORY.md + a FRESH graph) to confirm it doesn't already exist.
accept: |
  - DYNAMIC-DATA TOOL — mechanize, do NOT leave on-demand ([[dynamic-tools-never-on-demand]]): the map
    refresh runs on a CADENCE + MULTIPLE smart TRIGGERS, never a "run it manually" instruction:
    (a) TRIGGER on the event that dirties it — a post-merge/land refresh (source changed);
    (b) TRIGGER at SessionStart (boot) — refresh + surface staleness;
    (c) CADENCE — a scheduled periodic refresh as a backstop;
    (d) fleet/checks/graphify-freshness.sh detects a stale/absent graph and refreshes (`graphify update`) +
        surfaces LOUD in preflight. Covers the RIG too (build a rig graph if graphify handles bash; else
        document the gap). DOGFOOD: prove it refreshes after a real new file lands.
  - A REUSE-CHECK entry point the manager runs before creating a tool: given a proposed tool name/purpose,
    query the fresh graph + TOOL-INVENTORY.md and report existing matches ("do we already have X?").
  - fleet/tests/test_graphify_freshness.sh: a stale/absent graph -> freshness check FAILS/flags (fail-on-revert);
    a fresh graph -> passes.
  - Refresh product + rig maps once as part of this ticket so the map is current at land.
