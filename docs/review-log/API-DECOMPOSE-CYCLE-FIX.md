# API-DECOMPOSE-CYCLE-FIX

## Change

Architecture-hygiene fix in two layers:

### 1. Graph-builder bug (`tools/check_arch.py`)

`_resolve_import_target` collapsed `from . import a, b` to a single edge against the
parent package (`<pkg>`), masking every alias's real module-level dependency edge.
The three affected code paths were all fixed:
  - `_resolve_import_target` returns `list[str]` now; bare-relative multi-alias
    `from . import a, b` yields `["<pkg>.a", "<pkg>.b"]`.
  - `_scan_module_level_imports` simplified — no more `bare_relative` dict (the
    per-alias resolution is done in the AST pass itself).
  - `_build_import_graph_from_graphify` drops the stale `bare_relative` remapping.
  - `_build_import_graph_from_ast` iterates the new list return.

### 2. Decouple `decompose.py` from `api.py` (`src/charon/decompose.py`)

`decompose.py` had a module-level `from . import api` (line 30), creating a real
logical dependency cycle with `api.py`'s function-level `from .decompose import …`.
Removed the module-level import and inlined the one constant (`DEFAULT_STATE_DIR =
".charon"`) that was the sole consumer — the cycle is now gone.

## Side finding: `charon.config.* → charon.providers → charon.config` cycle

The graph-builder fix also reveals a pre-existing logical cycle:

    charon.config → charon.config.keyprobe → charon.providers → charon.config

All three edges are function-scoped (deferred), so it causes no runtime
ImportError, but it is a genuine architectural coupling.  The files involved
(`config/__init__.py`, `config/keyprobe.py`, `providers.py`) are outside this
ticket's ownership.  A follow-up ticket should either (a) break the back-edges
by deferring the module-level `config/__init__.py → keyprobe` import, or (b)
split the shared symbol into a neutral third module.

## Verification

- `python3 tools/check_arch.py src` now detects the decompose→api cycle WITHOUT
  the fix, and exits clean WITH the fix modulo the out-of-scope config cycle.
- `PYTHONPATH=src python3 -m pytest -q` (excluding `test_check_arch.py`): 1821 passed.
- `ruff check`: clean.
- `mypy src tests`: clean.
- `tools/check_boundary.py src`: clean.
- `tools/check_version.py`: pre-existing drift.
