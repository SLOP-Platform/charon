# TOOL-COMPOSITION-LAYER — Review Log

## Ticket
TOOL-COMPOSITION-LAYER: design-review, read-only — the operator's META/CLASS composition question
("the framework tool layer that allows tools to work with each other and have visibility to the
data/functions/output of other tools"), made concrete by the owns:↔code-graph join.

## What was done
- **EXECUTED the join the prior lanes only designed.** Probe parses `owns:` frontmatter from all
  436 owns-carrying board files → glob-resolves via `git ls-files` → cross-references
  `graphify-out/graph.json` `source_file`. Real output: query `fleet/land.sh` → 4-5 governing
  tickets incl. `LAND-SH-SAFE-SYNC`, plus the graph nodes implementing the guard
  (`safe_sync_base()` @ `fleet/land.sh:31`). Benchmark answered with ~40 LOC and zero new deps.
- **Measured edge case the prior design would have shipped broken:** 52 `owns:` entries are
  ABSOLUTE paths; graph `source_file` is 100% relative. A raw join silently drops owners
  (grep=5, naive join=4; `A1-LAND-GATE` missed). Normalizing restores all 5. Accept bar must be
  "grep count == join count."
- **Ran all three MCP servers** (the composition premise's substrate): graphify-mcp CRASHES
  (`ModuleNotFoundError: No module named 'mcp'` — its uv tool env lacks the dep); basic-memory
  v0.22.1 answers `tools/list` but is unwired in opencode; session-bridge runs. graphify CLI
  v0.9.12 works.
- **Corrected the prior lane's factual premise** (EVAL-REGISTRY COMPOSE-WHAT-WE-RUN row: "the three
  MCP servers already run") via a superseding row.
- **Registered verdicts in EVAL-REGISTRY.md** (5 new rows: join ADOPT-NOW, MCP-composition REJECT,
  COMPOSE premise correction, OTel scope-ruling to RUNTIME-INERT-DETECTION, runtime-artifacts
  RECORD).
- **Wrote the synthesis note** to `fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md`.

## Key decisions
- **ADOPT-NOW the normalized owns:↔graph join** — cheapest leverage in the programme; partial
  answer (provenance, not runtime data-flow). Not a distraction: it is the missing JOIN between
  two producers that always held the same key.
- **ADOPT-CANDIDATES: NONE (new tool)** — composition is a data-join problem, not a reasoning
  problem; an LLM-driven knowledge graph is the wrong shape. Tried hardest to make MCP the
  composition layer itself; it cannot (no cross-server join primitive).
- **OTel REJECTED-for-this-ticket by scope ruling** — the runtime axis belongs to the sibling
  RUNTIME-INERT-DETECTION ticket; adopting here would double-claim.

## Files changed
- `fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md` — in `owns:`
- `fleet/state/EVAL-REGISTRY.md` — in `owns:`
- `docs/review-log/TOOL-COMPOSITION-LAYER.md` — this fragment (allowed per instructions)

## Scope check
All changed paths are in the ticket's `owns:` line (plus this review-log fragment). No off-scope
file created or edited.

## Gate
Docs-only change to a design-review ticket in the RIG repo. The rig CI gate
(`.github/workflows/rig-ci.yml`) diff-scopes to changed `*.sh` (syntax) and changed
`fleet/board/*.md` (board); neither applies to these two markdown files. `rig-ci-scope.sh`
validated: no `*.sh` and no `fleet/board/*.md` changed in this PR.

## Retry re-verification (2026-08-01, qui-gon-jinn)

This branch was re-opened after the prior run's upstream was removed. The deliverable was
re-executed end-to-end, not just re-read, because the ticket's DONE CONTRACT requires measured
evidence:

- **Re-ran the join probe** against the live board + graph (`/tmp/opencode/join_probe.py`): 436
  owns-carrying board files (427 non-empty), 1,071 owned path-entries → 1,336 concrete after
  `git ls-files` glob resolution, 751 present as graph `source_file`. Benchmark query for
  `fleet/land.sh` returns all **5** governing tickets (HANDOFF-GATE-NONBYPASSABLE LIVE,
  RECONCILE-WIRING LIVE, LAND-SH-SAFE-SYNC / A1-LAND-GATE / GH-SEAM-CHOKEPOINT ARCHIVED) and the
  4 graph nodes (`safe_sync_base()` @ L31, `land_scope_plan()` @ L194). Counts have drifted up
  slightly as the board grew; corrected 431→436, 51→52 absolute-path entries.
- **Re-ran all three MCP servers**: graphify-mcp still crashes (`ModuleNotFoundError: No module
  named 'mcp'`); basic-memory v0.22.1 (was mis-cited as v3.3.1 — **corrected**) answers
  `tools/list`; session-bridge is still opencode's only MCP server. graphify CLI v0.9.12
  `explain "safe_sync_base()"` works. All prior verdicts stand; only the version/census numbers
  were corrected.

## Second re-verification (2026-08-02, obi-wan-kenobi, deepseek-v4-pro-ds)

Ticket reopened 2026-08-02 (operator directive: FALSE DONE — marker archived, no deliverable).
The research note now exists on disk (created 2026-08-01 by qui-gon-jinn). This session re-verified
the ticket's central measurements against the live rig:

- **Board `owns:` census:** 441 non-empty owns:-carrying files (+5 since 2026-08-01; the board
  grows ~5 files/day). grep across live/parked/archive/retired board files.
- **graph.json stats:** 13,266 nodes / 14,042 links / 2,072 distinct `source_file` (graph growth
  since prior census). 0 absolute `source_file` entries (held, as claimed).
- **Absolute-path `owns:` entries:** 34 raw (29 unique), down from 52 — board cleanup removed
  ~18 absolute-path entries. The principle holds: path normalization is essential; raw join
  drops owners.
- **`registry-discovery.sh` `owns:` refs:** 0 (held).
- **"ONLY consumer" claim:** CORRECTED — `graphify-freshness.sh` also reads `graph.json` (12 refs,
  staleness gate). `registry-discovery.sh` is the only *business-logic* consumer. Fixed in
  research note.
- **graphify-mcp crash:** held (`ModuleNotFoundError: No module named 'mcp'` re-executed 2026-08-02).
- **Land.sh 5 governing tickets:** all 5 confirmed present on board.
- **Join probe:** NOT re-executed (prior session's output trusted after verifying all its inputs).
- **EVAL-REGISTRY.md rows:** 5 rows registered by prior session, verified present at lines 151-155
  (join ADOPT-NOW, MCP-composition REJECT, COMPOSE premise correction, OTel scope-ruling,
  runtime-artifacts RECORD). No new rows needed — re-verification only corrected imprecisions.

### Scope self-check
`git diff --name-only master...HEAD`: `docs/review-log/TOOL-COMPOSITION-LAYER.md`,
`fleet/handoff-notes/TOOL-COMPOSITION-RESEARCH.md`, `fleet/state/EVAL-REGISTRY.md`. The third
was edited by the prior session before EVAL-REGISTRY was dropped from this ticket's owns. This
session did NOT edit EVAL-REGISTRY.md — the change is a prior-epoch artifact.

