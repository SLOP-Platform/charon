repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/code-map-mermaid
depends_on:
owns: fleet/code-map.sh, fleet/tests/code-map.test.sh
substrate: N/A
substrate-novel: |
  Mermaid is ADOPTED as the render format — it needs no dependency (GitHub renders it natively in
  markdown, and PR #169 already uses it). graphify is ADOPTED as the graph source and already
  refreshes on every land. NO diagram SaaS: todiagram / eraser.io / mermaid.ai would add an
  external service for a rendering step we do locally over data we already hold. The novel slice
  is the JOIN + query-scoping: colouring graphify nodes by which board ticket `owns:` them and
  that ticket's live state. That join is what both research lanes (RESEARCH-CONNECTION-GRAPH,
  RESEARCH-WORK-MGMT-LAYER, merged 2026-07-31) independently recommended and no tool performs.
serial_justified: |
  One renderer over one join. A generator without the ownership overlay is just a hairball; the
  overlay without the generator has nothing to draw on.
source: |
  Operator request (repeated): a real-time visual code diagram showing connections, data flow,
  relationships and status. Promoted to P0 2026-08-01.
note: |
  ## GROUNDING (measured 2026-08-01 — do not re-derive)
  - graphify holds **7,945 nodes / 12,884 edges** for the product tree; nodes carry `source_file`.
  - **374 board tickets carry `owns:`** — the join key, identical on both sides.
  - `fleet/checks/registry-discovery.sh` is graphify's ONLY consumer and has **zero** `owns:` refs.
  - graphify is refreshed automatically on EVERY land (`graphify-freshness: UPDATE OK`), so the
    source data is already live — no new cadence needed.
  - **PR #169 `docs/charon-flowchart` already exists** — a printable Mermaid map, operator-
    requested, DRAFT since 2026-07-19. Land or supersede it FIRST; do not build a second thing
    alongside a rotting first thing.

  ## SCOPE
  `fleet/code-map.sh <query>` emits Mermaid to stdout:
  1. **QUERY-SCOPED, never whole-graph.** 7,945 nodes renders as an unreadable hairball. Input is
     a file path / symbol / ticket id; output is that node plus its neighbourhood to depth N
     (default small). A whole-graph mode, if offered, must be explicitly asked for.
  2. **Status overlay — the actual value.** Annotate each node with: which ticket `owns:` it,
     that ticket's state (ready/claimed/submitted/done/blocked), and whether the code is flagged
     inert. This is what makes it a decision tool rather than a picture.
  3. Output is plain Mermaid in markdown so GitHub renders it with zero dependency.

  ## WIRE IT EVERYWHERE IT BELONGS (operator: wire to the code map and other tools)
  - **graphify** — consume `graphify-out/graph.json`; do NOT re-walk the source tree.
  - **the board** — read `owns:` + state markers for the overlay.
  - **preflight** — a `code-map` subcommand available where the other analysis tools live.
  - **MCP** — graphify-mcp / basic-memory already run; expose or compose rather than bolting on a
    private channel. Check what `graphify-mcp` already exposes BEFORE adding anything.
  - **handoff** — a session should be able to render the map for the code it is about to touch.
  Record which of these you wired and which you deliberately did not, with reasons. An unwired
  renderer is the inert class this rig keeps producing.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
  Hermetic, `mktemp -d`, offline (fixture graph.json + fixture board — never the live graph):
    a. a query for a file returns valid Mermaid containing that node and its direct neighbours;
       revert the generator -> RED.
    b. a node whose file is in some ticket's `owns:` is annotated with that ticket id AND state.
       Revert the overlay -> RED. **This is the load-bearing assertion** — without it this is a
       picture, not a tool.
    c. a file owned by NO ticket renders as explicitly unowned, not silently blank.
    d. query scoping holds: a depth-1 query on a fixture with 500 nodes returns a bounded subgraph,
       not the whole graph.
    e. ANTI-OVER-BLOCK: output parses as Mermaid (round-trip or a syntax check), so GitHub renders.
  Then DOGFOOD: render the map for `fleet/land.sh` and show it surfaces the tickets that own it
  (there are 10) — including LAND-SH-SAFE-SYNC, the provenance a manager needed and could not find.

D&S — Deps & Sequence:
  - Depends on: nothing; graphify + the board are already live.
  - FIRST ACTION: dispose of PR #169 — land it, or supersede it and say so in the PR.
