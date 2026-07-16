# DEDUP-CHECKARCH-GRAPHIFY — consolidated import graph builder

## What

Replaced `tools/check_arch.py`'s from-scratch `ast.parse`/`ast.walk` import-graph
builder with graphify's pre-computed graph (`graphify-out/graph.json`), using the
"prefer graphify, fall back to stdlib scan" pattern from
`ksf/modules/graph_adapter.py`.

## Changes to `tools/check_arch.py`

- **`_build_import_graph`** — now dispatches: tries `graphify-out/graph.json` first,
  falls back to the original AST walk (`_build_import_graph_from_ast`).
- **`_build_import_graph_from_graphify`** — reads graph.json nodes/links, filters
  to `src/charon/` import edges, applies `from . import X` remapping and
  TYPE_CHECKING exclusion.
- **`_scan_module_level_imports`** — lightweight scan that records which charon
  imports appear at module level (not inside `if TYPE_CHECKING:` guards) and
  which `from . import X` forms need parent-package remapping.
- **`_resolve_import_target`** — extracted helper that resolves a single
  Import/ImportFrom node to its absolute charon module name.
- **`_build_import_graph_from_ast`** — preserved fallback for environments
  without graphify's output (e.g., test temp dirs, fresh checkouts).

## Behavior-preservation notes

Graphify's import resolution is strictly more accurate than the old AST code:

1. **`from . import X`** — the old `_resolve_relative("pkg", level, None)`
   returned the parent package name (e.g. `"charon"`), not the sibling module
   (`"charon.api"`).  Graphify correctly resolves to the sibling module.  To
   preserve existing detection semantics, `_scan_module_level_imports` records
   these bare relative imports and remaps them back to the parent package.

2. **TYPE_CHECKING-guarded imports** — graphify includes them; the old code
   excluded them via `_collect_type_checking_import_ids`.  If included, they
   create a false cycle `proxy_server ↔ proxy_response` (forwarder/proxy_response
   import proxy_server only for type annotations).  The module-level scan
   excludes these edges, matching the old behavior.

## Result

- 77 modules, 254 edges — identical to the old AST graph.
- No circular import detections — identical to old behavior.
- All 34 `test_check_arch.py` tests pass (both AST-fallback and graphify paths).
- Full `pytest` suite: 1834 passed, 3 skipped, 1 xfailed, 1 xpassed.
- `ruff check`, `mypy` — clean.
- File scope: only `tools/check_arch.py` modified.

## Pre-existing bug discovered

The old `_resolve_relative` bug for `from . import X` (bare relative import with
`module=None`) meant the circular import check was **missing a real cycle**:
`charon.api ↔ charon.decompose` (api.py imports decompose at module level;
decompose.py imports api at module level).  The graphify-based approach
correctly detects this.  The remapping workaround was applied to maintain
backward-compatible behavior.  A follow-up ticket should fix this cycle in the
source and remove the remapping.
