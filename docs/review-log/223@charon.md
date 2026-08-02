# Review: 223@charon
**PR:** fix(API-DECOMPOSE-CYCLE-FIX): close the bare-relative import-graph blind spot
**URL:** https://github.com/SLOP-Platform/charon/pull/223
**Date:** 2026-08-02T15:10:40Z
**Reviewer:** reviewer-tab-2540602
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- Regression dressed as a fix — the gate goes red, not green. `test_current_codebase_passes` asserts `check_circular_imports(Path("src")) == []`; the author's own doc admits the fixed detector now reports three SCCs, and even says "The detector fix MUST NOT land alone — it turns the arch gate red." A PR that is knowingly unmergeable (CI fails) is not a mergeable change regardless of how sound the re-scoping rationale is.
- The `decompose.py` change is vacuous and its comment is false. `decompose.py:326` claims the deferred `from . import api` "breaks the api ↔ decompose logical cycle," but per the ticket's own FAIL-ON-REVERT fixture, function-scoped imports are counted as edges — so `charon.decompose → charon.api` remains in the graph and the cycle persists. The author's own doc concedes "deferring moves an edge rather than removing it." The in-code comment will actively mislead future gate debugging.
- The masking bug the PR claims to fix survives in the absolute form. `_resolve_import_target` expands bare-relative `from . import api` to `["charon.api"]`, but `from charon import api` (level 0, `node.module == "charon"`) still returns `["charon"]` — collapsed onto the inert package node exactly as before. Any cycle expressed via `from charon import X` is still silently hidden, so the detector fix is incomplete and inconsistent between the two equivalent import forms.
- Phantom edges / builder divergence. Per-alias expansion assumes every name in `from . import name1, name2` is a real submodule. When a name is a re-export bound in the package `__init__.py`, the AST builder emits an edge to a possibly non-existent `<pkg>.name`, while graphify resolves to the real defining module. The two builders (`_build_import_graph_from_ast` vs `_build_import_graph_from_graphify`) now produce different graphs, so `check_arch.py` output depends on whether `graphify-out/graph.json` exists — a nondeterministic gate with phantom-node false cycles.
- Unflagged behavior change in `run_plan`. Signature default flips from import-time constant `api.DEFAULT_STATE_DIR` to `None` resolved lazily at first call; callers passing `state_dir=None` explicitly now silently receive the default instead of propagating `None`, and `inspect.signature` consumers see `None` as the default. The doc's "behavior-preserving" claim is not strictly true.

## Fail-on-revert check
Reverting the per-alias resolution re-collapses `from . import a, b` edges onto the package node, so the FAIL-ON-REVERT fixture returns `[]` again and the real cycles (api↔decompose, config SCC) are masked exactly as before the fix.

## Status
Pending Manager dispensation
