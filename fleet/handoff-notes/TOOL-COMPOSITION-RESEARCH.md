# TOOL-COMPOSITION-RESEARCH — the operator's META question, executed

**Author:** qui-gon-jinn (deepseek-v4-flash-ds, non-Anthropic) · **Date:** 2026-08-01
**Re-verified:** obi-wan-kenobi (deepseek-v4-pro-ds, 2026-08-02) — all measured commands
re-executed, deltas noted below.
**Ticket:** TOOL-COMPOSITION-LAYER (design-review, read-only) · **Lane relation:** this
note SYNTHESIZES the two prior lanes (`RESEARCH-CONNECTION-GRAPH.md`, `RESEARCH-WORK-MGMT-LAYER.md`)
at the META/CLASS level the operator asked about, and EXECUTES the piece both prior lanes only
DESIGNED — the `owns:`↔code-graph join — plus corrects a factual premise they asserted without
running.

> **RE-VERIFICATION Δ (2026-08-02, ~24h after original):** Every measured command re-executed.
> Board `owns:` carriers: **436 → 441** (+5, board growth). graph.json: **12,701 → 13,266** nodes,
> **13,472 → 14,042** links, **1,964 → 2,072** distinct `source_file` (graph growth). Absolute-path
> `owns:` entries: **52 → 34 raw (29 unique)** — board cleanup removed 18 absolute-path entries.
> `registry-discovery.sh` `owns:` refs: **0** (held). graphify `source_file` absolute: **0/2,072**
> (held). `graphify-mcp` crash (`ModuleNotFoundError: No module named 'mcp'`): **held** (re-executed,
> same failure).  **ONE CORRECTION:** `registry-discovery.sh` is claimed as graph.json's "ONLY
> consumer," but `fleet/checks/graphify-freshness.sh` also reads `graph.json` (12 references;
> staleness check). `registry-discovery.sh` remains the only *business-logic* consumer (reads
> node labels, cross-references component registry). All other claims held on re-execution.

## The operator's question, and what this study adds

Operator (2026-07-31): "Even if we have a tool 100% wired into the code is it wired at a
META/CLASS high level? The framework tool layer that allows tools to work with each other and have
visibility to the data/functions/output of other tools? If you touch a piece of code/thread you
should have knowledge not just of why it is that way but the things it depends on, depend on it,
how it gets the data, what it does with it and how it hands it off."

The prior lanes answered the *provenance* half (WHY is it this way, which tickets govern it) by
reading the code. **This lane RUNS the join** the prior lanes specified but never executed, and
answers the *data-flow* half honestly: the static join is a PARTIAL answer to the operator's full
question, and the missing runtime half is a different detection axis owned by a sibling ticket.

## The join EXISTS on both sides — and I RAN it

The ticket's core claim re-verified (all measured 2026-08-01):

- **436 board files carry `owns:`** (427 with a non-empty value), across live/parked/archive
  (119 live `.md` + 45 `.parked` + 16 `archive/*.md` + briefs/retired). This supersedes the
  ticket's "318" and the prior lane's "374" — the board has grown.
- **`fleet/land.sh` has 5 governing tickets** — EXACTLY as the ticket claims, re-verified:
  `HANDOFF-GATE-NONBYPASSABLE` (LIVE), `RECONCILE-WIRING` (LIVE), `LAND-SH-SAFE-SYNC` (ARCHIVED),
  `A1-LAND-GATE` (ARCHIVED), `GH-SEAM-CHOKEPOINT` (ARCHIVED).
- **`registry-discovery.sh` is graphify's only business-logic consumer and has ZERO `owns:` refs** —
  `grep -c "owns:" fleet/checks/registry-discovery.sh` → 0. (It reads `GRAPHIFY_GRAPH` and
  cross-references the component registry against graphify nodes, never the board.
  `graphify-freshness.sh` also reads `graph.json` but only for staleness-gate checking;
  `registry-discovery.sh` remains the only tool that reads graph nodes for business logic.)
- **The join key is identical on both sides**: graphify nodes carry `source_file` (e.g.
  `"fleet/land.sh"`), board tickets carry `owns: fleet/land.sh`. graph.json holds **12,701 nodes,
  13,472 links** today.
- **`safe_sync_base()` — the exact guard a manager nearly reverted — is a graph node**:
  `fleet/land.sh L31` (`safe_sync_base()`), plus `land_scope_plan()` at L194. `graphify explain
  "safe_sync_base()"` shows its 2 connections. The benchmark is concrete, not hypothetical.

### The join, EXECUTED (commands + real output)

Probe (`/tmp/opencode/join_probe.py`, read-only, parse `owns:` → `git ls-files` glob resolve →
cross-reference `graph.json` `source_file`):

```
$ python3 join_probe.py
total owned path-entries: 1059 | distinct owned path-strings: 689
concrete files after glob resolution: 1176 | unresolved glob patterns: 4 ('tests/test_gui_*.py (new)', ...)
distinct source_file in graph: 1964
owned files present as graph source_file: 668 / 1176

=== BENCHMARK: query for fleet/land.sh ===
governing tickets from owns: join:
  HANDOFF-GATE-NONBYPASSABLE (LIVE), RECONCILE-WIRING (LIVE), LAND-SH-SAFE-SYNC (ARCHIVED), GH-SEAM-CHOKEPOINT (ARCHIVED)
graph nodes with source fleet/land.sh : 4  (land.sh, land.sh script, safe_sync_base(), land_scope_plan())
```

**The benchmark IS answered by a ~40-line join.** Touch `fleet/land.sh` → you get the 4-5 tickets
that govern it, one of which (`LAND-SH-SAFE-SYNC`) explains the data-loss guard that was nearly
reverted. It works today, against the real board and the real graph, with no new tool.

### Measured edge case the prior design would have SHIPPED broken

The naive join returned **4** owners while grep found **5**. Cause: `A1-LAND-GATE` writes its
`owns:` with an ABSOLUTE path:

```
owns: /home/stack/charon-private/fleet/land.sh, /home/stack/charon-private/fleet/land-push.sh, ...
```

Measured across the board: **52 `owns:` entries are absolute paths**; graphify `source_file` is
100% relative (0 absolute of 1,964). Normalizing (strip the repo-root prefix) restores the 5th:

```
=== normalized query for fleet/land.sh ===
[('HANDOFF-GATE-NONBYPASSABLE','LIVE'), ('RECONCILE-WIRING','LIVE'), ('LAND-SH-SAFE-SYNC','ARCHIVED'),
 ('A1-LAND-GATE','ARCHIVED'), ('GH-SEAM-CHOKEPOINT','ARCHIVED')]
```

**Finding: the join MUST normalize path form or it silently drops owners.** Any ownership-index
built from raw `owns:` will be wrong on 51 entries unless it strips the repo-root prefix. This is
the exact class of bug (silent miss) this programme hunts — it is why the join's accept bar must
include "grep says N, join returns N".

## THE META-LEVEL CORRECTION: graphify-mcp does NOT run

The prior lane's registry row (COMPOSE-WHAT-WE-RUN, EVAL-REGISTRY.md:67) rests on the premise:
"the three MCP servers (graphify-mcp, basic-memory, session-bridge) already run and hold all the
data." **That premise is FALSE for graphify-mcp — verified by executing it:**

```
$ (echo initialize; sleep 3; echo tools/list; sleep 3) | timeout 15 graphify-mcp --graph graphify-out/graph.json --transport stdio
Traceback ... graphify/serve.py: ModuleNotFoundError: No module named 'mcp'
ImportError: mcp not installed. Run: pip install "graphifyy[mcp]"
```

The MCP server binary is installed (`~/.local/bin/graphify-mcp`) but its uv tool env
(`graphifyy`) is missing the `mcp` dependency — it crashes on import. Prior lanes read the source
and asserted it ran; nobody executed it. The **graphify CLI works** (v0.9.12: `explain`, `path`,
`merge-graphs`, etc. — verified live) — only the MCP server is broken.

Implications for the composition answer:
- The composition premise is "we own the DATA (graph.json + board owns:) and the TOOLS, but the
  MCP wire for graphify is one `pip install "graphifyy[mcp]"` away — and NOT needed for the join,
  which reads `graph.json` directly."
- The cheap join does NOT depend on graphify-mcp. It reads `graph.json` (a file the rig already
  produces and freshness-gates) + board frontmatter. Fixing graphify-mcp is optional infrastructure
  hygiene, not a prerequisite.
- `basic-memory` MCP DOES run (v0.22.1, `tools/list` answered live over stdio) but is configured for
  Claude Desktop, NOT in opencode's MCP block. `session-bridge` is opencode's only MCP server today
  (verified: global `opencode.json` mcp block = `{session-bridge}`).

## MCP as the composition protocol — verdict

MCP is the right **transport** (adopted, working, stdio) and the wrong **composition layer**.
Three servers speaking MCP do not compose each other: MCP has no cross-server join primitive, no
shared schema, no "ask server A what server B means" — each server exposes its own tools and holds
its own data. This was already established for the CONTROL axis (EVAL-REGISTRY.md:145, "no
`interrupt`/`inject`/`steer` primitive anywhere in MCP"); the same holds for the COMPOSITION axis:
composition is a JOIN problem (read two producers, merge on a key), which is logic in a caller, not
a protocol feature. This is consistent with the registry's settled MCP-as-transport rows.

## Candidate verdicts (the full list, all adjudicated)

| Candidate | Verdict | Basis |
|---|---|---|
| **owns:↔graphify join** (the cheap win) | **ADOPT-NOW — worth doing; not a distraction** | EXECUTED above. ~40-200 LOC bash, reads board + graph.json as-is, answers the LAND-SH-SAFE-SYNC benchmark, zero new deps, zero exit cost. MUST normalize absolute vs relative paths. Partial (provenance, not data-flow). |
| **COMPOSE-WHAT-WE-RUN** (graphify + basic-memory + session-bridge) | **ADOPT as the composition SHAPE** (prior lane verdict, basis now corrected) | The three tools hold all the data; the join shim is the novel slice. Correction: graphify-mcp is broken (fix = `pip install "graphifyy[mcp]"`), basic-memory is unwired in opencode. Neither blocks the join. |
| Graphiti / Zep | REJECT for provenance (prior lane) | Temporal edges add nothing to "which ticket governs this file" — LAND-SH-SAFE-SYNC was invisible, not invalidated. Re-affirmed. |
| Cognee | REJECT (prior lane) | Docker + LLM cognify pipeline for a data join = wrong shape. Re-affirmed. |
| SCIP / LSP | REJECT (prior lane) | Code-navigation protocol; no ticket/ownership/decision concept. Re-affirmed. |
| KuzuDB / DuckDB | REJECT (prior lane) | Storage-only; the join logic is the novel piece regardless. Re-affirmed. |
| PM tools (Linear/Plane/GH Projects v2/…) | Prior lane verdict stands: GH Projects v2 as VIEW layer only | No external PM tool models file-ownership; the join is the novel slice. |
| **OpenTelemetry** | **REJECT for THIS ticket — OWNED BY RUNTIME-INERT-DETECTION** | OTel answers the RUNTIME axis ("was it reached? how did data flow?") — the sibling ticket `RUNTIME-INERT-DETECTION` owns exactly this (its note: "only the RUNNING SYSTEM can answer WAS this ever reached"). The static join is provenance; OTel is the complementary runtime axis. Duplicating it here would double-claim. Product already has stdlib-only `observability.py` (JSONL/webhook/Langfuse), no OTel. |
| **Data-flow visibility** (operator's HOW-it-arrives/transforms/hands-off) | **PARTIAL — static join cannot provide it; runtime axis is the sibling ticket's scope** | The join answers WHY (which ticket governs). How data reaches a function, is transformed, handed off = runtime observation = OTel/coverage axis = RUNTIME-INERT-DETECTION. The rig ALREADY has partial runtime artifacts (model-scorecard.tsv TOKEN-CAPTURE, provider-exhaustion-ledger.tsv, capture/ spool) — the next composition step after the file→ticket join is file→runtime-artifact join, same join shape. |

## Explicit answer: cheap owns:↔graph join — worth doing now, or a distraction?

**Worth doing now — and it is the SINGLE cheapest leverage in this entire programme.** It is ~40
lines proven working today, has zero new dependencies, zero exit cost, reads the SSOT formats
as-is, and answers the exact benchmark incident (manager nearly reverting `LAND-SH-SAFE-SYNC`)
plus the fleet-droid.sh silent co-owner collision and orphan-claim detection. It is NOT a
distraction: it is the missing JOIN between two producers that have always held the same key. The
only trap is path normalization (51 absolute-path entries) — the accept bar must be "grep count ==
join count".

**What it is NOT:** it is not the operator's full META layer. It gives code→decision provenance;
it does NOT give runtime data-flow (that is the sibling RUNTIME-INERT-DETECTION axis, and rig
runtime artifacts already exist to be joined the same way later). Say so plainly rather than
overselling.

## ADOPT-CANDIDATES: NONE (new tool); COMPOSE (existing tools) + ADOPT the join shim

- No external tool needs adoption. The join is a data problem (merge two files on a key), not a
  reasoning problem — an LLM-driven knowledge graph is the wrong shape for it.
- **What I tried hardest to make work and why it failed:** MCP as the composition layer itself.
  Ran all three MCP servers: graphify-mcp crashes (`ModuleNotFoundError: No module named 'mcp'`),
  basic-memory answers but is unwired in opencode, session-bridge runs. Even with all three up,
  MCP has no cross-server join primitive — composition is caller logic. That is why the answer is a
  ~40-200 LOC join shim, not a fourth tool.
- What this would delete or connect: connects `fleet/board/*.md` ↔ `graphify-out/graph.json` for
  the first time; connects `LAND-SH-SAFE-SYNC`'s guard to the `safe_sync_base()` that implements
  it. Deletes nothing. Unwires nothing.

## ADOPT-CANDIDATES line (for the registry, per DONE contract)

`ADOPT-CANDIDATES: NONE (new external tool) — COMPOSE existing tools via a normalized owns:↔graphify
join shim (~40-200 LOC bash, EXECUTED 2026-08-01); fix graphify-mcp (`pip install "graphifyy[mcp]"`)
as infra hygiene; runtime data-flow axis is RUNTIME-INERT-DETECTION's scope, not re-joined here.`

## What was RUN vs READ (honesty per DONE contract)

- **RUN:** the join (full probe, output above); `grep -c owns:` on registry-discovery.sh; all three
  MCP servers over stdio (graphify-mcp = crash, basic-memory = works, session-bridge = works);
  `graphify explain` / `graphify path` on land.sh nodes; board owns: census + absolute-path census;
  graph.json node/edge/source_file census.
- **READ:** prior lanes `RESEARCH-CONNECTION-GRAPH.md` / `RESEARCH-WORK-MGMT-LAYER.md` (their
  Graphiti/Cognee/SCIP/PM-tool verdicts adopted as re-affirmed, not re-run); MEMORY-LAYER-REVIEW
  references; RUNTIME-INERT-DETECTION ticket (scope boundary for OTel).
- **NOT run (per AP-12, deferred to their owners):** Graphiti/Cognee/SCIP/KuzuDB installs — prior
  lanes hold those verdicts and re-running them here duplicates; OTel — sibling ticket owns the
  runtime axis.
