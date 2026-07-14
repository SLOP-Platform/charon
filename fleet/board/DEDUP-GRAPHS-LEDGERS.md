repo: charon
tier: strong
difficulty: 3
work_class: refactor
branch: feat/dedup-actuals-graphs
depends_on: GATE-INTEGRITY-A
real-dep: GATE-INTEGRITY-A — its accept step 3 writes the ActualsLedger/ActualRow=DELETE triage
  into tools/inert-code-disposition.json; this ticket performs the code deletion those triage
  decisions authorize, so the disposition-file edit and the code deletion must not be concurrent
  (avoid double-write / disagreement between the two sessions).
owns: src/charon/capability/, tools/
note: |
  From fleet/state/TOOL-AUDIT-REDUNDANCY.md (findings 2 and 5) — READ IT FIRST, do
  not re-derive the audit. GATE-INTEGRITY was decomposed 2026-07-13 into
  GATE-INTEGRITY-A (inert-side, owns tools/inert-code-disposition.json) and
  GATE-INTEGRITY-B (gate-coverage side). GATE-INTEGRITY-A (its accept step 3)
  DECIDES ActualsLedger/ActualRow's disposition as DELETE; this ticket DOES the
  actual deletion — depends_on GATE-INTEGRITY-A so the disposition file and the
  code deletion aren't double-written by two concurrent sessions.
  REPO-BOUNDARY NOTE (product-vs-build-rig, standing rule): finding 6's "unify the
  two TSV-append impls" (`fleet/model-scorecard.sh` cmd_append vs
  `fleet/capability/auto_append.py`) is entirely RIG-side code
  (/home/stack/charon-private/fleet/), not product (src/charon/). It is OUT OF
  SCOPE for this ticket (repo: charon, owns: product paths only) — do NOT edit
  anything under /home/stack/charon-private/ from this ticket's worktree. File a
  separate charon-private-repo board ticket for finding 6 instead (this ticket's
  step 3 below covers filing it).
accept: |
  ## Task
  1. DELETE `src/charon/capability/actuals.py` (`ActualsLedger`/`ActualRow`) —
     confirmed zero production callers by `check_inert_code.py` (audit finding 5).
     Remove its only reference, the comment at `src/charon/decompose_sizing.py:54`.
     Delete/retire `tests/test_actuals_ledger.py` (tests the dead module only — if
     any assertion in it is actually exercising still-needed shared logic, port
     that assertion into `tests/test_capability_matrix.py` or `scorecard.py`'s
     tests instead of deleting it silently). The live equivalent
     (`capability/scorecard.py`, wired into `lifecycle.py`/`decompose_effort.py`)
     is UNCHANGED — this is a pure deletion of the superseded module, not a
     migration.
  2. AST-graph-builder consolidation (audit finding 2, product-side only — graphify,
     `tools/_vendor/ksf_inert_code.py` via `tools/check_inert_code.py`,
     `tools/check_arch.py`): the graphify/inert_code split is already a reasoned,
     documented, LOW-blast-radius decision (see `tools/inert_to_graph.py`'s own
     docstring) — do NOT touch that split. The NEW, unacknowledged duplication is
     `tools/check_arch.py`'s own from-scratch `ast.parse`/`ast.walk` import-graph
     builder (lines ~145-236) with its own hand-rolled `_is_docstring`/
     `_collect_type_checking_import_ids` (lines ~87-129), duplicating AST-quirk
     handling `ksf_inert_code.py` already solves. Apply the audit's named
     consolidation candidate: make `check_arch.py` consume graphify's raw
     extraction (`graphify update --no-cluster`, no LLM, deterministic, already
     computed once per CI run) for its import edges instead of a fourth
     from-scratch parse — same "prefer graphify, fall back to stdlib scan only if
     graphify absent" pattern `ksf/modules/graph_adapter.py` already uses for
     `reuse-check`. If, once inside the code, this proves higher blast-radius than
     the audit estimated, it is acceptable to instead land a written decision note
     (docs/adr or a follow-up board ticket) deferring the merge with concrete
     rationale — but the default expectation is the bounded consolidation lands.
  3. File a follow-up charon-private (rig) board ticket for audit finding 6 (dual
     TSV-append impls) referencing fleet/state/TOOL-AUDIT-REDUNDANCY.md — this
     ticket only FILES it (see repo-boundary note above), does not implement it.

  ## Accept (all must pass)
  - `grep -rn "ActualsLedger\|ActualRow" src/ tests/` → zero hits (module deleted,
    all references removed).
  - `PYTHONPATH=src python3 tools/check_inert_code.py` → no longer flags
    `capability.actuals.ActualsLedger`/`ActualRow` (they no longer exist to flag).
  - `PYTHONPATH=src python3 -m pytest -q` → full suite green (no orphaned test
    imports of the deleted module).
  - Either: `tools/check_arch.py`'s existing test suite stays green after it's
    switched to consume graphify's extraction (no behavior change to what it
    flags), with its own from-scratch `ast.parse` import-graph walk removed; OR a
    committed decision note explains why the consolidation is deferred, with the
    follow-up ticketed.
  - A new charon-private board ticket file exists for the TSV-append unification
    (finding 6), referencing TOOL-AUDIT-REDUNDANCY.md.
  - `PYTHONPATH=src python3 -m charon.cli gate` → GREEN.

  ## Dependencies & sequence
  depends_on: GATE-INTEGRITY-A (owns overlap: GATE-INTEGRITY-A's accept step 3 writes
  the ActualsLedger=DELETE triage into tools/inert-code-disposition.json; this
  ticket performs the deletion those triage decisions authorize — sequenced so the
  disposition-file edit and the code deletion are never concurrent/double-written).
  Single wave, lands after GATE-INTEGRITY-A.
