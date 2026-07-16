tier: strong
difficulty: 2
work_class: refactor
branch: feat/dedup-checkarch-graphify
repo: charon
parent: DEDUP-GRAPHS-LEDGERS
depends_on:
owns: tools/check_arch.py, tests/test_check_arch.py
note: |
  Manually decomposed sub-ticket of DEDUP-GRAPHS-LEDGERS (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted). Disjointness verified by
  hand: this ticket owns only tools/check_arch.py + its test; DEDUP-ACTUALS-DELETE (sibling) owns
  the unrelated src/charon/capability/actuals.py deletion — zero file overlap. No dependency on
  GATE-INTEGRITY-A (that dependency belongs only to the actuals.py deletion sibling, which touches
  the inert-code-disposition.json triage this ticket does not read or write). From
  fleet/state/TOOL-AUDIT-REDUNDANCY.md finding 2 — READ IT FIRST, do not re-derive the audit.
accept: |
  AST-graph-builder consolidation (audit finding 2, product-side only — graphify,
  `tools/_vendor/ksf_inert_code.py` via `tools/check_inert_code.py`, `tools/check_arch.py`): the
  graphify/inert_code split is already a reasoned, documented, LOW-blast-radius decision (see
  `tools/inert_to_graph.py`'s own docstring) — do NOT touch that split. The NEW, unacknowledged
  duplication is `tools/check_arch.py`'s own from-scratch `ast.parse`/`ast.walk` import-graph
  builder (lines ~145-236) with its own hand-rolled `_is_docstring`/
  `_collect_type_checking_import_ids` (lines ~87-129), duplicating AST-quirk handling
  `ksf_inert_code.py` already solves. Apply the audit's named consolidation candidate: make
  `check_arch.py` consume graphify's raw extraction (`graphify update --no-cluster`, no LLM,
  deterministic, already computed once per CI run) for its import edges instead of a fourth
  from-scratch parse — same "prefer graphify, fall back to stdlib scan only if graphify absent"
  pattern `ksf/modules/graph_adapter.py` already uses for `reuse-check`. If, once inside the code,
  this proves higher blast-radius than the audit estimated, it is acceptable to instead land a
  written decision note (docs/adr or a follow-up board ticket) deferring the merge with concrete
  rationale — but the default expectation is the bounded consolidation lands.

  ## Accept (all must pass)
  - Either: `tools/check_arch.py`'s existing test suite stays green after it's switched to consume
    graphify's extraction (no behavior change to what it flags), with its own from-scratch
    `ast.parse` import-graph walk removed; OR a committed decision note explains why the
    consolidation is deferred, with the follow-up ticketed.
  - `PYTHONPATH=src python3 -m charon.cli gate` → GREEN.
scope: |
  Manually-decomposed single-domain sub-ticket of DEDUP-GRAPHS-LEDGERS (fleet/decompose.sh).
