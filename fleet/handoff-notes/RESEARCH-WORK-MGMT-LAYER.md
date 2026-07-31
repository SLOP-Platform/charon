# RESEARCH-WORK-MGMT-LAYER — ADOPT-first evaluation of work management / project manager layer

**Date:** 2026-07-31
**Scope:** ADOPT-FIRST research lane — produce a VERDICT, not code. Find or reject external tools that
address the operator's ask for "a PROJECT MANAGER layer that oversees ALL tickets, intelligently
organizes them, prioritizes against the NORTH STAR, optimizes deployment, KNOWS ALL THE CONNECTIONS,
and keeps ITSELF updated."

## Summary Verdict

**HONEST: no single external tool performs the `code ↔ decision ↔ incident` join.** The
composition of graphify's code-graph with the board's `owns:` fields is a genuinely novel slice
(~500 LOC of glue). But the SUBSTRATE is already adopted (graphify-mcp, basic-memory,
session-bridge) and the VIEW layer has a clear adopt candidate (GitHub Projects v2). The
recommended path is: adopt GitHub Projects v2 as the programmatic view, compose the existing MCP
tools for the code↔decision join, and keep our `.md` board as the SSOT with a thin sync bridge.

## The Known Gap (pre-confirmed, not re-derived)

The join key exists on BOTH sides and NOTHING joins them. graphify answers "what calls what." The
board's `owns:` answers "why is it this way / which ticket governs this code."
`fleet/checks/registry-discovery.sh` is the ONLY consumer of graphify's graph.json and contains
ZERO references to `owns:`.

## Research Method

Every candidate was researched via web search, GitHub API, npm/PyPI registry search, and MCP
registry search. For tools already trialed (ao, Omnigent, Windmill, Archon), the executed trial
transcripts in `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` were treated as settled evidence.
No trial was re-run — AP-12 satisfaction was verified by confirming the trial transcripts
contain host + command + observed output, not source:line citations.

## Candidate Analysis

### Category A: Work/PM systems with API + MCP

#### A1. Linear (linear.app)
- **MCP:** OFFICIAL first-party MCP server at `https://mcp.linear.app/mcp` (HTTP/SSE transport).
  Official Linear SDK + 16+ community MCP servers on npm. Strongest MCP story of any work tracker.
- **API:** Full GraphQL API at `api.linear.app/graphql`. Fully typed TS SDK (`@linear/sdk`, MIT).
  CRUD on issues, projects, teams, cycles, comments, webhooks. Interactive schema explorer.
- **Data model:** Priorities (4-level + urgent), parent/child dependencies, `IssueRelation`
  (blocks/blocked-by), custom fields (Business+), labels, cycles (sprints), estimates.
  **No file-ownership concept.** Would need external mapping layer.
- **Control direction:** We CALL Linear's API. Linear fires webhooks at us. Clean "you call us" model.
- **Self-hosted:** NO. SaaS-only at all tiers. Free tier: unlimited members, 2 teams, 250 issues,
  API access, MCP access.
- **Exit cost:** Medium. API-exportable (full GraphQL), CSV export, open-source import CLI
  (`@linear/import`). But SaaS-only means must extract proactively.
- **Incidents it would have prevented:**
  - 46 open PRs >370h — Linear's built-in analytics + cycle tracking would surface age
  - SYNC-SCHEDULE stranded ~194h — dependency visibility would flag blocked items
  - Doctrine rule outliving constraint by 12d — no (Linear has no doctrine/rule engine)
- **Verdict: WATCH — strong, but SaaS-only lock-in + no file ownership are blocking.** If
  the operator accepts SaaS-only for a work tracker, Linear is the best-in-class PM tool
  with the best MCP story. But it does NOT perform the code↔decision join — our `owns:` →
  code mapping would live outside it. RANKED #2.

#### A2. Plane (plane.so)
- **MCP:** OFFICIAL first-party MCP server (`@makeplane/plane-mcp-server`, Python/FastMCP,
  MIT, 100+ tools across 20 categories). Multiple community servers. Supports stdio, SSE,
  streamable HTTP, OAuth.
- **API:** Full REST API (`api.plane.so`). Predictable resource-oriented URLs, API key auth,
  cursor-based pagination. Projects, work items, cycles, modules, epics, custom properties.
- **Data model:** Rich hierarchy (Workspace → Teamspaces → Projects → Epics → Work Items).
  Work item links (blocking, related, duplicate). Custom properties (text, number, date,
  dropdown). States with workflow categories.
  **No file-ownership concept.**
- **Control direction:** We CALL Plane's REST API. Inbound webhooks (GitHub, GitLab, Slack)
  push into Plane. No generic outbound webhooks.
- **Self-hosted:** YES. Docker Compose, Kubernetes (Helm), Docker All-in-One. PostgreSQL +
  Redis + MinIO. AGPL-3.0 license.
- **Exit cost:** Low. PostgreSQL dump is highly portable. Data model is conventional.
- **Incidents it would have prevented:**
  - 46 open PRs >370h — custom fields + views would surface age
  - Orphan claim-markers (39) — item ↔ marker reconciliation would detect orphans
  - SYNC-SCHEDULE stranded — dependency links would flag blocked items
- **Verdict: WATCH — self-hosted + official MCP, but heavyweight and no code↔decision join.**
  AGPL-3.0 copyleft is a consideration (any modifications must be open-sourced). RANKED #4.

#### A3. Huly (huly.io)
- **MCP:** NO official MCP. Extremely rich third-party ecosystem: `@firfi/huly-mcp` (v0.47.0,
  470+ native tools, multiple transports), `huly-mcp-sdk` (WebSocket-native). Active
  maintenance (2 days ago).
- **API:** WebSocket-native TypeScript SDK (`@hcengineering/api-client`) + limited REST.
  SDK-first, not REST-first.
- **Data model:** Full relations system (blocks, is-blocked-by, relates-to). Sub-issues
  (native). Gantt scheduling. Components (issue areas). Plug-in extensible data model.
  **No file-ownership concept.**
- **Control direction:** We CALL via SDK or REST. GitHub App inbound webhooks push into Huly.
  No generic outbound webhooks.
- **Self-hosted:** YES. Docker Compose (CockroachDB, MinIO, Redpanda, Elasticsearch, 15+
  microservices). 2-4 vCPUs / 8-16 GB RAM minimum. EPL-2.0 license (more permissive than
  AGPL-3.0).
- **CRITICAL:** Hosted Huly shutting down July 2026. Self-host only going forward.
- **Exit cost:** Medium. Dedicated export service, but schema is complex (CockroachDB +
  multi-service state). Raw DB migration without tooling is harder than Plane.
- **Incidents it would have prevented:** Same class as Plane (aged PRs, orphan markers).
- **Verdict: WATCH — best third-party MCP ecosystem, but hosted shutting down, complex
  self-hosting, SDK-first API is less universal than REST.** RANKED BELOW SHORTLIST.

#### A4. GitHub Projects v2 (we already use GitHub)
- **MCP:** OFFICIAL first-party MCP server (`github/github-mcp-server`, 31.9k stars, Go-based,
  actively maintained). `projects` toolset: `projects_get`, `projects_list`, `projects_write`
  (full mutation surface). Deployed as remote server (`api.githubcopilot.com/mcp/`) or local
  (Docker/binary).
- **API:** Full GraphQL API. Dedicated `ProjectV2` types with queries and mutations for CRUD
  on projects, items, fields (text, number, date, single-select, iteration). Batch update
  (up to 50 items).
- **Data model:** Custom fields mirror our frontmatter exactly: `owns:` → text field,
  `priority:` → single-select, `depends_on:` → text field (or Issue-level `issue_dependencies`),
  `tier:`, `work_class:`, `difficulty:` → single-select/number fields. Status built-in.
  Sub-issues (parent/child). Issue-level blocking dependencies.
  **Critical caveat:** dependencies at Issue level, not Project level — must read through
  `content` (Issue) of each `ProjectV2Item`.
  **Webhooks:** org-level only, public preview. Not available for user-owned projects.
- **Control direction:** We CALL GitHub's GraphQL API. Inbound webhooks (org-level, preview)
  push events to us. Matches our existing pattern.
- **Self-hosted:** NO (GitHub is SaaS). But we already use GitHub — zero new infrastructure.
- **Pricing:** FREE for private repos (included in all tiers). No per-project or per-seat cost.
- **Exit cost:** Near ZERO. Our `.md` board remains the SSOT. GitHub Projects is a mirror/view.
- **Incidents it would have prevented:**
  - 46 open PRs >370h — Projects v2 views + filters would surface aged items
  - Orphan claim-markers (39) — programmatic item↔marker reconciliation
  - SYNC-SCHEDULE stranded ~194h — custom field for age + filter would surface
  - DROID-LIFECYCLE-REAP / LAUNCHER-CRASH-PARTIAL-DETECT / SESSION-REPORT-WIRE collision —
    `owns:` custom field with overlap detection query would catch
  - Doctrine rule outliving constraint — no (Projects v2 has no doctrine/rule engine)
- **What it FILLS:** Programmatic, MCP-accessible, query-able board view. Currently our `.md`
  board is only readable by bash scripts parsing frontmatter. GitHub Projects v2 provides
  a structured API that agents (and existing MCP tools) can query and update.
- **What it REPLACES:** Nothing. It is additive — a mirror/view of our SSOT `.md` board.
- **Verdict: ADOPT as VIEW LAYER.** Zero new infrastructure, free, official MCP, best
  control-direction story. RANKED #1.

### Category B: Agent-Native Task Layers

#### B1. jpicklyk/task-orchestrator (agent-native work management)
- **MCP:** YES — it IS an MCP server. 14 MCP tools. STDIO + HTTP transport. Docker image.
- **API:** REST API (`API_ENABLED=true`) with SSE events, JWKS JWT auth.
- **Data model:** Schema-enforced work items. Hierarchical graph (4 levels). Typed dependency
  edges. Phase-gated transitions (`queue → work → done`). Required notes per phase.
  Actor attribution. Full-text search (SQLite + FTS5).
- **Control direction:** Server-enforced workflow discipline. "Prompt-based frameworks hope
  the LLM follows instructions. This one blocks the call if it doesn't."
- **SCM-coupling:** NONE. SCM-agnostic — manages work items, not branches/PRs. Clean layering.
- **Exit cost:** Low. Work items in SQLite + config.yaml.
- **Stars:** 198. Active.
- **Incidents it would have prevented:**
  - Orphan claim-markers (39) — claim/release lifecycle with actor attribution
  - Built-but-not-wired tickets — phase-gated transitions ensure work progresses through
    defined states
  - SYNC-SCHEDULE stranded — dependency ordering with staleness visibility
  - DROID-LIFECYCLE-REAP collision — `owns:` could be modeled as work item tags, overlap
    detection possible
- **Verdict: WATCH — closest to genuine agent-native work management, but young and no
  GitHub integration.** The schema-enforced gate pattern is the right shape. If it had
  GitHub integration and more maturity, it would be the #1 pick. RANKED #3.

#### B2. Fulcrum (knowsuchagency/fulcrum)
- **MCP:** YES — 100+ MCP tools. Claude Code plugin.
- **API:** REST API + CLI + messaging (WhatsApp, Email, Discord, Telegram, Slack).
- **Data model:** Projects → tasks → git worktrees. Kanban board. Task dependencies.
  Agent memory (MEMORY.md + SQLite FTS5).
- **License:** PolyForm Perimeter (restrictive redistribution).
- **Verdict: SKIP — Claude Code-centric, restrictive license, monolithic.** The 100+ MCP
  tools are impressive but the PolyForm Perimeter license and Claude Code coupling make
  it incompatible with our agent-agnostic posture. BELOW SHORTLIST.

#### B3. Already-Trialed Tools (ao, Omnigent, Archon) — settled REJECT
See `fleet/state/WORKLOOP-INTEGRITY-STACK-SPIKE.md` for executed trial evidence:
- **ao:** GitHub-API-coupled hardcoded, session supervisor not work manager.
- **Omnigent:** Policy gates only, no work management, alpha/Databricks.
- **Archon:** Workflow engine not work manager, GitHub-centric, worktree conflict.

#### B4: Task Master AI, taskcrew, TASKPLAN, FlowGate, frame, vibe-loop — SKIP
All are either too early (0-1 stars), no MCP, or wrong abstraction (PRD→task generator,
document pipeline, markdown tracker). Worth studying as pattern donors (TASKPLAN's
deterministic code-side selector, taskcrew's mechanical verification, FlowGate's
typed document pipeline) but not adoptable. BELOW SHORTLIST.

### Category C: Workflow/Scheduling Engines

**None are work-management layers.** They are task/pipeline execution engines. Prefect has
the best MCP story (official, first-party, read-only) but monitors pipelines, not manages
work items. Windmill has no MCP. Dagster's MCP is data-asset-focused. Temporal, Kestra,
Airflow are overkill for solo and have no MCP.

**Verdict: REJECT — category error.** These execute tasks; they don't manage work items
with dependencies, file ownership, and scheduling intelligence. Using one as a work
management layer would fight the abstraction.

**Windmill gets the #5 shortlist spot** — not as a work management layer, but as the
execution *substrate* if we need durable script scheduling. RANKED #5.

### Category D: DAG/Build Tools

**All rejected.** Nx has the strongest MCP story of any build tool but for builds, not
tickets. Turborepo and Bazel are the same category error. `WORK-FRAMEWORK-TOOL-SCAN.md`
§4 already adjudicated: "no generic DAG library provides the domain-specific safety
wrapper." BELOW SHORTLIST.

## Integration Shape for Top Pick (GitHub Projects v2)

### Architecture

```
fleet/board/*.md (SSOT)
       │
       ▼
sync bridge (~200 LOC Python)
       │ reads frontmatter (owns:, depends_on:, priority:, tier:, etc.)
       │ writes to GitHub Projects v2 via GraphQL API
       │
       ▼
GitHub Projects v2 (VIEW LAYER)
  - One project: "Charon Fleet"
  - Custom fields: owns (text), depends_on (text), priority (single-select),
    tier (single-select), work_class (single-select), difficulty (number),
    branch (text), repo (single-select)
  - Status: derived from state/ markers (Todo → In Progress → In Review → Done)
       │
       │ agents query/update via github-mcp-server
       │
  ┌────┴─────────────────────────────────────────┐
  │                                               │
  ▼                                               ▼
graphify-mcp (code graph)               basic-memory (knowledge store)
  "what calls what"                       "code↔decision cross-reference index"
       │                                       │
       └───────────────────┬───────────────────┘
                           │
                   composition bridge (~300 LOC Python)
                     queries graphify: "what files are callers of file X?"
                     queries board: "which ticket owns file X?"
                     result: "ticket A blocks ticket B because A's code
                              is called by B's code"
                     writes to basic-memory: cross-reference index
                     writes to GitHub Projects: adds dependency edges
```

### sync bridge (file-level)

**New file:** `fleet/tools/sync-to-github-projects.py`

Reads `fleet/board/*.md`, extracts frontmatter fields, upserts to GitHub Projects v2:
- `project_id` — project number from `fleet/tools/github-projects-config.json`
- Each ticket maps to a `ProjectV2Item` with `content` = GitHub Issue (auto-created if
  no matching issue exists)
- Custom field values set: `owns`, `depends_on`, `priority`, `tier`, `work_class`,
  `difficulty`, `branch`, `repo`
- Status derived from `state/` markers: DONE if `state/done/<id>` exists, IN-REVIEW if
  `state/submitted/<id>` exists, IN-PROGRESS if `state/claims/<id>` exists, TODO otherwise
- Idempotent — re-running updates existing items, never creates duplicates
- Runs on preflight (similar to `report.sh`)

### composition bridge (file-level)

**New file:** `fleet/tools/compose-code-decision-join.py`

1. Queries `graphify-mcp` for code graph:
   - For each file mentioned in any ticket's `owns:`, find its callers and callees
2. Queries `fleet/board/*.md` for `owns:` mapping:
   - For each file returned by graphify, find which ticket owns it
3. Produces join result:
   - "Ticket A governs file X which is called by file Y governed by Ticket B —
     Ticket B depends on Ticket A"
   - Writes to `basic-memory` as a structured fact with TTL
   - Optionally writes `depends_on` edges to GitHub Projects v2
4. Validates against existing `depends_on:` edges:
   - Missing dependency → WARN
   - Unjustified dependency → WARN (reuses validate_board.sh's WCI logic)
5. Runs on preflight or on-demand via MCP tool

### What agents see via MCP

An agent with access to `github-mcp-server` (projects tools) can:
- `projects_list(method="list_project_items", query="status:Todo priority:P0")` →
  all P0 tasks ready to work
- `projects_get(method="get_project_item", item_id="...", fields=["owns","depends_on"])` →
  which files this ticket governs and what it depends on
- `projects_write(method="update_project_item", ...)` → update status, add notes
- Combined with `graphify-mcp`: "show me all tickets that own files called by this file"
- Combined with `basic-memory`: "show me the code↔decision cross-reference for ticket X"

## Shortlist (Ranked)

### #1 (TOP PICK): GitHub Projects v2 + existing MCP tool composition

- **MCP:** YES — official `github/github-mcp-server` (31.9k stars, projects toolset)
- **API:** Full GraphQL, custom fields mirror our frontmatter
- **Control direction:** We call GitHub API. Matches existing pattern.
- **Exit cost:** Near zero. `.md` board is SSOT; GitHub Projects is a mirror.
- **What it REPLACES:** Nothing. Additive view layer.
- **What GAP it fills:** Programmatic, MCP-accessible, query-able board. The composition
  bridge fills the `code ↔ decision` join gap (the KNOWN GAP).
- **Integration shape:** Thin sync bridge (~200 LOC) + composition bridge (~300 LOC).
  Total novel code: ~500 LOC of glue over adopted tools.
- **Would have prevented:**
  - Orphan claim-markers (39) — programmatic marker↔item reconciliation
  - SYNC-SCHEDULE stranded ~194h — age filter + dependency visibility
  - DROID-LIFECYCLE-REAP collision — `owns:` overlap detection query
  - 46 open PRs >370h — views + filters surfacing aged items
  - Code-dependent ticket ordering — composition bridge joining graphify with `owns:`
- **Recommendation: ADOPT.** This is the minimal, novel-slice-only approach.

### #2: Linear

- **MCP:** YES — official + 16+ community
- **API:** Full GraphQL, strong SDK
- **Control direction:** We call Linear. Clean.
- **Exit cost:** Medium (SaaS-only, must extract proactively)
- **What it REPLACES:** Nothing. Mirror of our board.
- **What GAP it fills:** Rich PM tooling (analytics, cycle tracking, roadmaps)
- **Would have prevented:** Aged PRs, stranded work visibility (but NOT code↔decision join)
- **Blocking:** SaaS-only lock-in; no file ownership model; no self-hosting
- **Verdict: WATCH — best PM tool if SaaS-only is acceptable.** NOT #1 because it doesn't
  fill the KNOWN GAP (code↔decision join) and adds SaaS lock-in.

### #3: jpicklyk/task-orchestrator

- **MCP:** YES — 14 MCP tools, schema-enforced gates
- **API:** REST + SSE
- **Control direction:** Server-enforced discipline
- **Exit cost:** Low (SQLite + YAML config)
- **What it REPLACES:** Nothing. Additive work-item layer.
- **What GAP it fills:** Structured work-item lifecycle with schema-enforced quality gates
- **Would have prevented:** Orphan markers, unwired work, claim/release races
- **Blocking:** 198 stars, no GitHub integration, SCM-agnostic (doesn't model branches/PRs)
- **Verdict: WATCH — closest to agent-native work management but immature.**

### #4: Plane

- **MCP:** YES — official Python MCP (100+ tools)
- **API:** Full REST
- **Control direction:** We call REST API
- **Exit cost:** Low (PostgreSQL dump, conventional schema)
- **What it REPLACES:** Nothing. Mirror of our board.
- **What GAP it fills:** Self-hosted PM tool with official MCP
- **Would have prevented:** Aged PRs, orphan markers, stranded work visibility
- **Blocking:** AGPL-3.0, heavyweight (PG + Redis + MinIO), no code↔decision join
- **Verdict: WATCH — best self-hosted PM tool but heavyweight.**

### #5: Windmill

- **MCP:** NO — no MCP server found
- **API:** Full REST + OpenAPI spec + 5 SDKs
- **Control direction:** We call REST API
- **Exit cost:** Medium (scripts are portable, flows are JSON/YAML)
- **What it REPLACES:** Nothing. Execution substrate for scheduled work.
- **What GAP it fills:** Durable script execution with scheduling, retries, webhooks
- **Would have prevented:** Built-but-not-wired scripts (if wired through Windmill),
  gate decay (scheduled health checks)
- **Blocking:** No MCP, wrong abstraction (execution engine, not work manager)
- **Verdict: WATCH — execution substrate, NOT work management.**
  Only if we need durable scheduling for fleet scripts (e.g., periodic preflight runs,
  scheduled graphify refreshes). Not a PM layer.

## Pattern Donors (below shortlist, worth studying)

| Tool | Pattern to extract |
|---|---|
| TASKPLAN (ellmos-ai) | Deterministic code-side selector — "moves the decision out of the prompt and into code" |
| taskcrew | Mechanical verification + three-loop escalation (REVISE/REPLACE) |
| FlowGate | Typed document pipeline (R → T → TR) with review gates |
| Archon | YAML DAG workflows with approval gate nodes |
| Omnigent | Three-level policy stack (server/agent/session) |

## Honest No-Go Assessment

**No single external tool performs `code ↔ decision ↔ incident` joins.** The composition
of graphify's code graph with the board's `owns:` fields is genuinely novel — no PM tool,
workflow engine, or agent-native task layer models "which files a ticket governs" as a
first-class concept.

**The minimal novel slice** would be a Python MCP server (~300-500 LOC) that:
1. Reads `fleet/board/*.md` frontmatter (reusing validate_board.sh's parsing)
2. Queries `graphify-mcp` for code-graph data
3. Produces joined results (which tickets share code dependencies)
4. Validates against existing `depends_on:` edges
5. Writes to `basic-memory` for persistent cross-reference

This is exactly the composition bridge described in the top-pick integration shape.
It's novel only in the JOIN — the parts it joins (graphify's graph, board's `owns:`,
dependencies) are all existing, machine-readable data.

**The build slice (~500 LOC) is justified** because no adopt candidate performs this join.
But it's a thin WRAPPER over adopted tools (graphify-mcp, basic-memory, session-bridge,
GitHub Projects v2 MCP), not a from-scratch build.

## What We Already Have (do not rebuild)

The existing fleet already has significant work-management infrastructure:
- `fleet/board/*.md` — 113+ live tickets with machine-readable `owns:`, `depends_on:`,
  `priority:`, `tier:`, `work_class:`, `difficulty:` frontmatter
- `validate_board.sh` — validates board structure, owns-collisions, dep ordering, WCI
- `wci-contention.sh` — detects high-contention god-files, auto-generates decompose tickets
- `report.sh` / `board.sh` / `ROADMAP.tsv` — status rendering + roadmap
- `graphify` + `graphify-mcp` — full code graph of both repos
- `basic-memory` (MCP) — note/knowledge store
- `session-bridge` (MCP) — live session board
- `WORK-OPTIMIZER-DESIGN.md` — designed lane-planning + auto-close
- `WORKLOOP-INTEGRITY-STACK-SPIKE.md` — executed trials of ao, Omnigent, Windmill, Archon

**None of this should be rebuilt.** The answer is: adopt GitHub Projects v2 as the view
layer, compose the existing MCP tools for the code↔decision join, and keep the `.md`
board as the SSOT. The novel slice is the composition bridge — thin, justified, and
backed by executed trials proving no external tool fills the gap.

## Decision Framework

| Criterion | GitHub Projects v2 (#1) | Linear (#2) | task-orchestrator (#3) | Plane (#4) | Windmill (#5) |
|---|---|---|---|---|---|
| MCP server | Official, active | Official, active | Yes (14 tools) | Official, active | None |
| API-addressable | GraphQL | GraphQL | REST + SSE | REST | REST + SDKs |
| Control direction | We call API | We call API | Server-enforced | We call API | We call API |
| Self-hosting | N/A (we use GH) | No (SaaS-only) | Yes (Docker) | Yes (Docker) | Yes (Docker) |
| File ownership | Custom text field | No (external map) | Tags/labels | Custom properties | No |
| Dependency model | Issue-level | Parent/child + relations | Typed edges | Work item links | None |
| Exit cost | Near zero | Medium | Low | Low | Medium |
| New infrastructure | Zero | SaaS account | Docker container | PG+Redis+MinIO | PG+workers |
| Fills KNOWN GAP | With composition bridge | No | No | No | No |
| Replace vs fill | Fills VIEW GAP | Fills PM GAP | Fills STRUCTURE GAP | Fills SELF-HOST GAP | Fills EXECUTION GAP |

## Appendix: Candidates Researched But Not Shortlisted

**Rejected with reasons:**
- **Jira** — No MCP server found. Wrong posture (enterprise, heavyweight). Overkill for solo.
- **OpenProject** — No MCP server found. REST API exists but no agent-native integration.
- **Taiga** — No MCP server found. REST API exists but maintenance is slow.
- **Shortcut** — No MCP server found. API exists but less mature than Linear.
- **Tracker** — No MCP server found. Pivotal Tracker heritage, but no MCP.
- **Backlog.md** — No MCP, markdown-based only, no PM features.
- **Vibe-Kanban** — SUNSETTING. 27.6k stars but product is shutting down.
- **Temporal** — No MCP (agent-tempo uses it as infra), DAG-of-activities engine, overkill.
- **Prefect** — Official MCP but read-only, pipeline orchestrator not work manager.
- **Dagster** — MCP exists (official + community) but data-pipeline abstraction.
- **Kestra** — No MCP, JVM-based, YAML workflow engine.
- **Airflow** — No MCP, overkill by definition for solo.
- **Nx** — Strong MCP, but for builds not tickets. Category error.
- **Turborepo** — No MCP, JS/TS ecosystem lock-in, category error.
- **Bazel** — No MCP, extreme learning curve, category error.