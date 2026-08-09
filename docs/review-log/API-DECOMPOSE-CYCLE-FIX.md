# API-DECOMPOSE-CYCLE-FIX — detector gap closed, but the real tree is a web

## Status

BLOCKED / RELEASED — the in-owns deliverable (detector fix + decompose decoupling)
is complete and correct, but the ticket's accept criterion
(`python3 tools/check_arch.py` exits 0 on the real `src/charon` tree) is
UNSATISFIABLE within the `owns:` scope. The operator's premise — "decompose/api is
just the confirmed live instance" — is factually wrong: fixing the detector
reveals **three** real circular-import SCCs that the bug was masking, and
resolving all of them requires editing files outside `owns:`.

## What was done (in `owns:`, gate-clean)

1. **`tools/check_arch.py`** — `_resolve_import_target` now returns a *list* of
   targets and resolves `from . import name1, name2` to **one edge per alias**
   (`<pkg>.name1`, `<pkg>.name2`), matching how `from .name1 import X` already
   resolves. `_scan_module_level_imports`, `_build_import_graph_from_graphify`,
   and `_build_import_graph_from_ast` all emit the per-alias edges; the
   parent-package remap (`bare_relative`) that collapsed edges onto the inert
   package node was removed from both graph builders.
2. **`src/charon/decompose.py`** — `from . import api, gitutil` split to
   `from . import gitutil`; `run_plan`'s `api.DEFAULT_STATE_DIR` default is now
   resolved through a deferred, function-scoped `from . import api` (the same
   lazy pattern api.py already uses). Behavior-preserving (decompose/phase2/
   service tests green).

## Verification

- **FAIL-ON-REVERT fixture passes**: `a.py` module-level `from . import b` +
  `b.py` function-scoped `from . import a` → `check_circular_imports` reports
  `charon.a → charon.b → charon.a`. (Previously: `[]`.)
- **Per-alias resolution**: `from . import api, gitutil` → `charon.decompose →
  charon.api` and `charon.decompose → charon.gitutil`. (Previously: collapsed to
  `charon.decompose → charon`.)
- `ruff check`, `mypy src tests` clean on the changed files; decompose/phase2/
  service test suites pass.

## The blocker: three real cycles the bug was masking

With the detector fixed, `check_circular_imports(Path("src"))` reports (DFS order):

1. **`charon.config → charon.config._store → charon.secrets → charon.providers →
   charon.config`** (config SCC, 12 nodes). `config/__init__.py` imports
   `from .. import secrets` at module level; `secrets.py:320` imports
   `from . import providers as _providers` (deferred); `providers.py:282` imports
   `from . import config` (deferred). This is the "second, more harmful cycle" —
   it sits on the provider-key path.
2. **api/gateway ring SCC (12 nodes)**: `api → gateway → routing_policy →
   proxy_server → console_router → console_work → engine.board → land → parallel
   → api`, plus `api → decompose → parallel → api` and `gateway ↔ proxy_server ↔
   forwarder ↔ routing_policy`. None of the ring edges is removable from
   `api.py`/`decompose.py` alone.
3. **`charon.decompose_planner ↔ charon.intake`**: `decompose_planner.py:64`
   imports `from .intake import …` at module level; `intake.py:1042` imports
   `from . import decompose_planner as _dp` (deferred).

These are **real logical cycles**, not detector noise. The codebase has a
documented workaround culture built on the very bug being fixed — developers use
the `from . import X` form precisely because it collapsed to the package root and
never tripped the checker, e.g. `intake.py:1044` ("a static
`from .decompose_planner import ...` here would trip the arch-lint
circular-import check. The `from . import` form … there is no cycle"),
`providers.py:282` ("deferred: config has no reverse dependency on this"),
`secrets.py:320` ("deferred: providers.py must not need secrets"),
`engine/scheduler.py:297` ("local: avoid import cycle at top"). The ticket's own
suggested fix ("defer decompose's `from . import api`") cannot produce a DAG
either: the detector counts function-scoped imports as edges (per the ticket's
own FAIL-ON-REVERT fixture), so deferring moves an edge rather than removing it.

## Why this is blocked

The accept criterion requires the **whole real tree** to be clean
(`test_current_codebase_passes` asserts `check_circular_imports(Path("src")) == []`
and `python3 tools/check_arch.py` must exit 0). Breaking all three SCCs requires
editing `config/__init__.py`, `config/_store.py`, `secrets.py`, `providers.py`,
`gateway.py`, `proxy_server.py`, `console_router.py`, `console_work.py`,
`engine/board.py`, `forwarder.py`, `land.py`, `parallel.py`, `routing_policy.py`,
`routing_policy/catalog_refresh.py`, `decompose_planner.py`, and `intake.py` —
all outside this ticket's `owns:`. Per fleet ownership rules (owns is the single
source of truth; never create/edit files another ticket owns), the change was
released for re-scoping rather than improvising outside scope.

## NEXT for the manager

Re-ticket as an architecture-cleanup wave: land the detector fix (this PR's
in-owns work) together with cycle-breaking changes to the ~16 out-of-owns files,
or split per-SCC tickets with matching `owns:` lists. The detector fix MUST NOT
land alone — it turns the arch gate red (1 violation: the config cycle) and
breaks `test_current_codebase_passes`.
