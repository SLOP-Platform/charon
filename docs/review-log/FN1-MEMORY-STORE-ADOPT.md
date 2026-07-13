# FN1-MEMORY-STORE-ADOPT — Review Log

## Decision: ADOPT basic-memory (composed per MEMORY-DESIGN.md)

basic-memory is the clear winner for the manager memory layer:
markdown = source of truth (near-zero migration, our files are already markdown),
local FastEmbed semantic + full-text search, first-class MCP, lowest lock-in.
AGPL-3.0 is fine for the internal rig; txtai/MIT is the documented swap path.

### Migration approach
- 92 memory markdown files copied from `~/.claude/memory/` into `fleet/memory/markdown/`
- Light frontmatter added: `tags` (derived from filename/content patterns) + `last_referenced` (UTC date)
- MEMORY.md index not copied — search replaces it

### PINNED core
- `pin.md`: 14 critical always-on facts (build methodology, standing facts, recurring failure patterns)
- SessionStart hook now loads only `pin.md` via `load.sh` (34 lines vs 2234 lines full dump)
- 34x reduction in startup context burn
- Everything else: pull-on-demand via `memory.search` MCP tool

### Search engine (stdlib-only)
- `search.py`: full-text search over frontmatter + body, term-frequency scoring
- Supports `--json` for MCP integration, `--pin` for pinned core dump
- No external dependencies (stdlib `re`, `json`, `pathlib`)

### Verdict: GREEN — FAIL-ON-REVERT tests pass
- (a) `test_load_default_does_not_dump_full_memory`: default load.sh output << full dump
- (b) `test_search_returns_fact_not_in_pinned_core`: point-of-need retrieval works
- (c) `test_real_point_of_need_retrieval`: 5 diverse facts all retrievable from search
- All markdown files have tags + last_referenced frontmatter
- Search output is valid JSON with file/title/tags/score/snippet fields

### Scoping
- Reverted `load.sh` to dump full set → test (a) catches it (size check + content assertion)
- Reverted `search.py` to no-op → test (b) catches it (no results)
- GREEN-IS-NOT-PROOF: test (c) proves 5 real facts outside pinned core are retrievable
