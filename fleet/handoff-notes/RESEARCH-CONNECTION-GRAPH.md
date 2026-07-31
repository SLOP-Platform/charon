# RESEARCH-CONNECTION-GRAPH — deepseek-v4-pro
## VERDICT: COMPOSE-WHAT-WE-RUN + thin join shim (NOT a framework)

### Direct Answer

The right move is **COMPOSE-WHAT-WE-RUN** — compose graphify-mcp + basic-memory +
session-bridge over MCP with a minimal join shim (~200 LOC). The gap was never a missing
tool; it was a JOIN nobody performs. The join key (file path) exists on both sides
(318+ board tickets with `owns:`, graphify nodes with `source_file`), and the
composition layer is literally the wire between them.

This is NOT hand-rolling a framework (the disease) — it IS "compose what we already run"
(the brief's §3). The novel slice is the join logic, not a new graph.

---

## MEASURED GAP (re-verified, not re-derived)

The gap stated in the brief is correct and was independently confirmed:

- **374 board tickets carry `owns:`** (365 non-empty). The brief said 318 — this was
  a stale count. Current: 121 live + 45 parked + 208 archived = 374.
- **5 tickets own `fleet/land.sh`** — confirmed: LAND-SH-SAFE-SYNC (archived),
  HANDOFF-GATE-NONBYPASSABLE (live), RECONCILE-WIRING (live), plus 2 others.
- `graphify` holds 12,064 nodes + 12,884 edges in `graphify-out/graph.json`.
- `registry-discovery.sh` is graphify's ONLY consumer and has ZERO `owns:` refs (confirmed:
  `grep -c "owns:" fleet/checks/registry-discovery.sh` → 0).
- The join key: graphify nodes carry `source_file` (e.g. `"fleet/land.sh"`),
  board tickets carry `owns: fleet/land.sh`. Identical key, both sides, zero join.

## BENCHMARK QUESTION: LAND-SH-SAFE-SYNC

"Would this tool have surfaced LAND-SH-SAFE-SYNC to a session about to touch land.sh's
sync refusal?"

| Candidate | Answers benchmark? | How |
|---|---|---|
| COMPOSE-WHAT-WE-RUN | YES | Query file path → join to owns: → surface the 5 tickets including LAND-SH-SAFE-SYNC and their handoff notes |
| Graphiti | PARTIAL | Would need ingestion pipeline to load board tickets + graphify nodes as episodes; no MCP server; requires graph DB |
| Cognee | PARTIAL | Could ingest both data sources into unified KG; but requires Docker + LLM calls for cognify pipeline; overkill for a lookup |
| KuzuDB | YES (with build) | Embedded Cypher graph; hand-roll import + query layer |
| SCIP/LSIF | NO | Code-navigation standard, not a provenance/project-management protocol |
| DuckDB CTE | YES (with build) | Trivially joins owns: table to graphify file nodes; pure data join |
| Neo4j | PARTIAL | Same as KuzuDB but operational overhead; needs server |

## CANDIDATES (per-brief list + additions)

### 1. COMPOSE-WHAT-WE-RUN (graphify-mcp + basic-memory + session-bridge over MCP)
**VERDICT: ADOPT — the answer.**

- **MCP?** YES. All three already have or can have MCP interfaces.
  graphify-mcp: 10 tools (query_graph, get_node, get_neighbors, etc.).
  basic-memory: 12 MCP tools (search-notes, read-note, write-note, etc.).
  session-bridge: 8 MCP tools (register, board, claim, nudge, etc.).
- **Answers benchmark?** YES, with the join shim. Without it: NO — none of the three
  tools individually knows about the other two's data.
- **Storage/ops cost:** ZERO new dependencies. graphify already runs (every session boot,
  every 30min cadence). basic-memory already running (146 notes). session-bridge already
  running (auto-heartbeating). The join shim adds one new script.
- **Control direction:** LIBRARY (we call the shim). The shim calls existing tools, does
  not own the agent loop or replace any component.
- **Exit cost:** ZERO. The join shim reads existing data formats. Remove the shim and
  the underlying tools still work independently.
- **Reads board as-is?** YES. The join shim parses `fleet/board/*.md` frontmatter using
  the existing `_vm_meta()` parser in `_lib.sh` — zero board schema change required.

### 2. Graphiti (temporal KG engine, v0.29.3, Apache-2.0)
**VERDICT: WATCH — not for this gap.**

Already evaluated in MEMORY-LAYER-REVIEW.md:
- Temporal invalidation IS real (valid_at/invalid_at/expired_at edges)
- Requires a graph DB (Kuzu embedded works, 7.6MB)
- NO MCP server — pure library
- All writes explicit (add_episode()) — same failure mode as basic-memory
- No plans/tasks/commitments
- **Answers benchmark?** PARTIAL. Would need to ingest board tickets as episodes into
  a graph, then query temporal edges. But the temporal dimension adds nothing to the
  provenance lookup — LAND-SH-SAFE-SYNC was not invalidated, it was invisible.
- **Control direction:** LIBRARY. Good fit.
- **Exit cost:** MEDIUM. Data in KuzuDB/FalkorDB native format.
- **Reads board as-is?** NO. Tickets must be reshaped into episode format.

### 3. Zep (SaaS platform, v3.25.0)
**VERDICT: REJECT — egress.**

Already evaluated in MEMORY-LAYER-REVIEW.md:
- SDK (`zep-cloud`) sends ALL data to api.getzep.com
- Legacy self-hosted CE is abandoned
- **Answers benchmark?** NO (egress violation, plus no code-graph integration)

### 4. Cognee (KG memory platform, 29.6K stars, Apache-2.0)
**VERDICT: REJECT — overkill for a join.**

Full evaluation (this session, from README + repo structure):
- **Has MCP?** YES. cognee-mcp ships as a Docker container with HTTP transport.
- **What it does:** Ingest documents → LLM-driven cognify pipeline → knowledge graph
  (entities + relationships) → `recall()` for semantic+graph search. Supports
  Postgres/PGVector/KuzuDB/Neo4j/LanceDB backends.
- **MCP tools:** The MCP server exposes recall/remember/forget over MCP.
- **Answers benchmark?** PARTIAL. Could ingest both board tickets AND graphify nodes
  into the KG, then query for connections. But:
  - The cognify pipeline requires LLM calls per ingestion (operational cost)
  - Requires Docker for the MCP server (additional service)
  - Does NOT read board as-is — tickets must be preprocessed into Cognee documents
  - The full KG + LLM pipeline is vastly more than a provenance lookup needs
- **Storage/ops cost:** HIGH. Docker service + LLM API costs per ingestion cycle.
  Data stored in Cognee's internal graph format.
- **Control direction:** LIBRARY (SDK). We call cognee.remember()/cognee.recall().
  Not a framework — good.
- **Exit cost:** MEDIUM. Data in Cognee's graph format; export path exists.
- **Maintenance liveness:** ACTIVE. 29.6K stars, 8,959 commits, active Discord.
  Apache-2.0 license.

### 5. SCIP / LSIF (Code Intelligence Protocol)
**VERDICT: REJECT — wrong category.**

- Category mismatch: SCIP is a code-navigation protocol (go-to-def, find-references).
  It standardizes how INDEXERS describe code symbols. It has NO project-management
  or provenance concept. LSIF is its predecessor.
- **Answers benchmark?** NO. SCIP indexes symbols, not board tickets. It would tell you
  where land.sh's sync_guard() function IS in the code, not which ticket explains WHY
  it exists.

### 6. KuzuDB (embedded graph DB)
**VERDICT: REJECT — hand-roll required.**

- Embedded Cypher graph DB (7.6MB). Could load graphify nodes + board owns: as vertices.
- No MCP server. Pure storage engine.
- Would need: import scripts (graphify JSON → Kuzu nodes/edges, board owns: → Kuzu nodes),
  query layer (Cypher queries for file→ticket join), MCP wrapper.
- This IS hand-rolling per AP-5/AP-7. The storage is the easy part; the join logic is
  the novel piece we'd build anyway. KuzuDB just changes the storage format.

### 7. DuckDB + recursive CTE
**VERDICT: REJECT — same as KuzuDB, hand-roll.**

- Could query graphify's graph.json directly: `SELECT * FROM read_json('graphify-out/graph.json')`
- Could join owns: via a table built from board frontmatter.
- But still a hand-roll. Same join logic, different storage.

### 8. basic-memory (already adopted)
From MEMORY-LAYER-REVIEW.md:
- Already ADOPTED with 146 notes in charon project.
- No file-path-to-ticket mapping. Semantic search only.
- The "join key" problem is structural, not semantic — basic-memory can't join file paths
  to tickets unless we explicitly store that mapping inside it.

### 9. GitHub linked-issues / CODEOWNERS
- CODEOWNERS maps files to teams, not to tickets/decisions.
- GitHub linked-issues connects PRs to issues, not file paths to tickets.
- Wrong shape.

### 10. Backstage (catalog + TechDocs + relations)
- Full developer portal platform. Catalog maps services to owners. TechDocs maps docs
  to services. Relations link entities.
- Can model "file X belongs to ticket Y" via catalog entities + relations.
- BUT: this is a full platform (requires deployment, maintenance, catalog YAML files).
  Wrong size for a solo operator with a single board of markdown tickets.
- **Answers benchmark?** WOULD require us to model every ticket as a Backstage entity
  with relations to source files. This IS reshaping our board into Backstage's format.

### 11. ADR tools (adr-tools, Log4brains)
- adr-tools: CLI for creating/managing ADRs. No query-by-code-path.
- Log4brains: ADR knowledge base with web UI. No code-graph integration.
- Neither answers the benchmark.

### 12. OpenTelemetry semantic conventions for provenance
- Runtime telemetry, not static code-to-decision provenance.
- Wrong layer.

---

## THE INTEGRATION SHAPE FOR THE TOP PICK

### What gets built (the novel slice — NOT a framework)

**One file**: a bash script (or small Python MCP tool) that performs the join.

### File-level design

```
fleet/checks/ownership-join.sh    # THE join shim (~150-200 LOC bash)
graphify-out/ownership-index.tsv  # Generated index: file_path → ticket_id, ticket_title
```

### How `owns:` joins to graphify nodes

1. **Index generation** (runs at session-start + post-land):
   - Iterates `fleet/board/*.md` (live) + `fleet/board/*.md.parked` (parked)
   - Parses `owns:` field via `_vm_meta owns $ticket` (reuses existing parser)
   - For each owned path, writes `file_path\ticket_id\tticket_title\thandoff_notes_path\n`
     to `graphify-out/ownership-index.tsv`
   - For glob patterns (e.g. `fleet/checks/*.sh`), resolves to concrete files via
     `git ls-files` and writes one row per resolved file.

2. **Query** (session-time):
   - Input: a file path (e.g. `fleet/land.sh`) or a graphify node label
   - Step A: grep `ownership-index.tsv` for the file path → returns ticket IDs
   - Step B: call graphify-mcp `get_neighbors("label")` → returns code neighbors
   - Step C: for each neighbor's source_file, grep ownership-index.tsv → returns
     governing tickets for neighbors
   - Step D (optional): `basic-memory search-notes "land.sh sync"` → surface
     stored memories about this file/topic
   - Output: combined provenance report

### Where the joined index lives

`graphify-out/ownership-index.tsv` — colocated with `graph.json` so a single
directory is the "joined knowledge base." graphify-freshness.sh's existing
staleness primitives apply: if `graph.json` is stale, the ownership index is
regenerated alongside it.

### What queries it must answer

| Query | How |
|---|---|
| "Which tickets govern `fleet/land.sh`?" | `grep -w fleet/land.sh ownership-index.tsv` |
| "What does the code at `fleet/land.sh` connect to, and who governs those connections?" | graphify-mcp get_neighbors + cross-reference each neighbor's source_file against ownership-index.tsv |
| "Show the provenance chain for the sync refusal guard" | Same as above, filtered to the specific code region |
| "What past incidents mention changes to land.sh?" | basic-memory search-notes "land.sh incident" |
| "Which sessions are currently working on tickets that own land.sh?" | session-bridge board + filter by ticket IDs from ownership-index.tsv |

### What refreshes it

| Trigger | Action |
|---|---|
| Session-start hook | Rebuild ownership-index.tsv |
| Post-land (land.sh trigger) | Rebuild ownership-index.tsv |
| graphify-freshness.sh gate | Enforce: if graph is stale OR ownership-index.tsv older than graph.json, block | 
| Preflight hook | Verify ownership-index.tsv exists and is fresh |

### Honest caveat: the data-flow question

The brief and TOOL-COMPOSITION-LAYER.md ask: "how data reaches a function, is transformed,
and is handed off." A static owns:<->graph join answers provenance (WHY, which tickets
govern), but does NOT answer runtime data flow. The brief acknowledges this explicitly:
"the operator is asking for data-flow visibility... which a static owns<->symbol join does
NOT provide. Say so if the join is a partial answer."

The join IS a partial answer. It closes the provenance gap (which ticket explains why
this guard exists), but runtime data flow requires a different tool entirely
(OpenTelemetry instrumentation, liveness tracing), which is scope-creep for this
brief's question. The owns:→graph join is the cheapest, highest-leverage first step
and answers the benchmark question definitively.

---

## INCIDENT COVERAGE

| Incident | Prevented by this? | How |
|---|---|---|
| Manager nearly reverting LAND-SH-SAFE-SYNC | YES | Query land.sh → sees LAND-SH-SAFE-SYNC ticket explaining the guard |
| 39 orphan claim-markers | PARTIAL | Orphans without an owning board ticket would have no ownership-index.tsv entry; query would return EMPTY rather than silence |
| Three tickets silently co-owning fleet/fleet-droid.sh | YES | Query fleet-droid.sh → returns all 3 co-owning tickets; the collision is visible |
| Doctrine rule asserting a capability was impossible, 12 days after it shipped | PARTIAL | Query capability's code paths → surfaces the shipped code's owning ticket alongside the contradictory doctrine ticket |
| 60+ loaded memories, none blocked unfinished work | NO | This is a memory-layer scheduling problem (LETTA-REVIEW.md lane), not a provenance problem |

---

## HONEST NO-GO

If compose-what-we-run is rejected, the NEXT-BEST is not Graphiti or Cognee or KuzuDB.
Those all require MORE new code (ingestion pipelines, Docker services, LLM calls) to
achieve the same result. The NEXT option after compose-what-we-run is DuckDB with a raw
JSON join — zero new infrastructure, just a SQL query against graph.json + a owns:-derived
table. But this still hand-rolls the join logic.

The minimal novel slice is unavoidable: something must read both `owns:` and
`graph.json` and emit the joined answer. The question is only how thick that something
needs to be. The answer: ~200 lines of bash, thinner than any adopted alternative's
integration cost.

---

## WHAT WAS CHECKED

### Pre-existing notes (read first per brief §6)
- `fleet/handoff-notes/LETTA-REVIEW.md` — Folded in. Verdicts on Letta (REJECT:
  framework controls agent loop), mnemostroma (REJECT: unrunable), Mem0 (REJECT:
  no auto-extraction, cloud telemetry), basic-memory (ADOPTED for memory store).
  Key insight: the scheduling/injection layer concept from Letta is the most
  relevant capability, but it addresses a different gap (follow-through on
  commitments, not provenance joins).
- `fleet/handoff-notes/MEMORY-LAYER-REVIEW.md` — Folded in. Evaluated 7 memory
  tools. Key finding: "No tool beats finishing basic-memory." Graphiti's temporal
  invalidation is real but requires Neo4j/Kuzu. Forgetful's plans+tasks is the
  closest to structured work-tracking. Neither provides the owns:→graph join.
- `fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md` (does not exist yet —
  this is the ticket TOOL-COMPOSITION-LAYER's output target; this research
  note is the CONNECTION-GRAPH lane's output per the brief).

### Primary verification (this session)
- Confirmed graphify-mcp tool list and data shape by reading `serve.py` and `graph.json`
- Confirmed board owns: count and format by grepping `fleet/board/*.md`
- Confirmed `registry-discovery.sh` has zero owns: refs
- Confirmed `opencode.json` has ONLY session-bridge in its MCP block (no graphify-mcp,
  no basic-memory)
- Confirmed basic-memory is ADOPTED but configured outside opencode.json (Claude Desktop MCP)
- Read Cognee README + file structure for MCP server and integration shape
- Read SCIP protocol documentation for scope match
- Evaluated KuzuDB/DuckDB as storage-only alternatives (both require hand-roll)

---

## ADOPT-CANDIDATES: NONE (new tool); COMPOSE (existing tools)

No external tool needs adoption. The existing stack (graphify-mcp + basic-memory +
session-bridge) already holds all the data. The join shim is the novel slice, not
a new tool.

What I tried hardest to adopt: Cognee. It has an MCP server (cognee-mcp in Docker)
and can ingest both board tickets and code-graph data into a unified KG. But:
1. Requires Docker (new service to maintain)
2. Requires LLM calls per ingestion cycle (operational cost, latency)
3. Does not read board as-is (needs preprocessing)
4. The full KG+LLM pipeline is >10x the complexity of a thin join for the same result

The join is a data problem, not a reasoning problem. An LLM-driven knowledge graph
is the wrong shape for "grep two sources and merge the results."