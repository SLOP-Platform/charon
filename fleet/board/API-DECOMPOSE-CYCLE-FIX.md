repo: charon
tier: strong
difficulty: 2
work_class: refactor
branch: feat/api-decompose-cycle-fix
owns: src/charon/api.py, src/charon/decompose.py, tools/check_arch.py
depends_on:
dep-kind:
work_class_note: architecture-hygiene — the import-graph builder undercounts real edges,
  masking cycles project-wide, not just this one pair.
note: |
  OBSERVED 2026-07-15, confirmed by reading + a debug run of tools/check_arch.py's graph builder:
  ``decompose.py`` imports ``api`` at MODULE level (``from . import api, gitutil`` — decompose.py
  line 30, executes at import time) and ``api.py`` imports ``decompose`` at FUNCTION level, twice
  (``from .decompose import run_decomposed`` / ``... import decompose as _decompose_stages``,
  both deferred inside function bodies, api.py lines ~269/320) — a real logical dependency cycle
  between the two modules. It causes no runtime ImportError TODAY only because api.py's side is
  deliberately lazy/deferred — but ``tools/check_arch.py``'s circular-import detector is supposed
  to catch exactly this shape and does NOT, because of a real bug in its graph resolver:
  ``_build_import_graph`` walks ``from . import api, gitutil`` (module=None, multiple names) and
  ``_resolve_relative`` (check_arch.py ~line 74) only returns the PACKAGE root (``charon``) for
  this import FORM — it never appends the aliased names, so the edge recorded is
  ``charon.decompose -> charon`` instead of ``charon.decompose -> charon.api``. Meanwhile
  ``charon.api -> charon.decompose`` IS recorded correctly (confirmed: ``api`` node's edge set
  contains ``charon.decompose``). Because the decompose->api edge collapses to the inert package
  node, the DFS never closes the cycle, and ``check_arch.py`` reports clean. This is a graph-
  builder correctness bug (undercounts ``from . import a, b`` edges everywhere in
  src/charon/**), not specific to this pair — decompose/api is just the confirmed live instance.
accept: |
  ``tools/check_arch.py``'s ``_build_import_graph`` resolves ``from . import name1, name2`` to
  ONE EDGE PER ALIAS (``<pkg>.name1``, ``<pkg>.name2``), not a single collapsed edge to the
  package root, matching how ``from .name1 import X`` is already resolved. Then fix the actual
  decompose<->api coupling it now correctly detects: break the cycle (e.g. make decompose.py's
  ``from . import api`` deferred/function-scoped to match api.py's existing lazy pattern, or
  extract the specific ``api`` symbols decompose.py needs into a shared module both can import
  without a back-edge) so the graph is a true DAG.
  FAIL-ON-REVERT: a fixture package with ``a.py`` doing module-level ``from . import b`` and
  ``b.py`` doing (even function-scoped) ``from . import a`` -> ``check_circular_imports`` reports
  the cycle. Revert the ``_resolve_relative``/edge-per-alias fix -> the fixture cycle goes
  undetected again. A second assertion: ``python3 tools/check_arch.py`` exits 0 (clean) against
  the real src/charon tree once decompose.py/api.py are decoupled.
scope: |
  Architecture-hygiene fix: a real graph-builder blind spot in the project's own cycle detector,
  plus the one confirmed cycle it was masking. Product repo. Low risk (detector + import-shape
  fix, no runtime behavior change once decoupled).
ds: Now — no owns collision found on api.py/decompose.py/check_arch.py. Not launch-blocking;
  file to close the detector gap before it masks a SECOND, more harmful cycle.
