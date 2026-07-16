tier: strong
difficulty: 2
work_class: refactor
branch: feat/dedup-actuals-delete
repo: charon
parent: DEDUP-GRAPHS-LEDGERS
depends_on: GATE-INTEGRITY-A
real-dep: GATE-INTEGRITY-A's accept step 3 writes the ActualsLedger/ActualRow=DELETE triage into
  tools/inert-code-disposition.json; this ticket performs the code deletion those triage decisions
  authorize, so the disposition-file edit and the code deletion must not be concurrent.
owns: src/charon/capability/actuals.py, src/charon/decompose_sizing.py, tests/test_actuals_ledger.py
note: |
  Manually decomposed sub-ticket of DEDUP-GRAPHS-LEDGERS (fleet/decompose.sh's plan_decomposition
  engine was unavailable 2026-07-15 — whole model pool 429/exhausted, see DEDUP-GRAPHS-LEDGERS.md
  history). Disjointness verified by hand: this ticket owns only the dead-module deletion path;
  DEDUP-CHECKARCH-GRAPHIFY (sibling) owns the unrelated tools/check_arch.py consolidation — zero
  file overlap between the two. From fleet/state/TOOL-AUDIT-REDUNDANCY.md finding 5 — READ IT
  FIRST, do not re-derive the audit.
accept: |
  1. DELETE `src/charon/capability/actuals.py` (`ActualsLedger`/`ActualRow`) — confirmed zero
     production callers by `check_inert_code.py` (audit finding 5). Remove its only reference, the
     comment at `src/charon/decompose_sizing.py:54`. Delete/retire `tests/test_actuals_ledger.py`
     (tests the dead module only — if any assertion is actually exercising still-needed shared
     logic, port that assertion into `tests/test_capability_matrix.py` or `scorecard.py`'s tests
     instead of deleting it silently). The live equivalent (`capability/scorecard.py`, wired into
     `lifecycle.py`/`decompose_effort.py`) is UNCHANGED — this is a pure deletion of the superseded
     module, not a migration.
  2. File a follow-up charon-private (rig) board ticket for audit finding 6 (dual TSV-append
     impls — `fleet/model-scorecard.sh` cmd_append vs `fleet/capability/auto_append.py`)
     referencing `fleet/state/TOOL-AUDIT-REDUNDANCY.md` — this ticket only FILES it, does not
     implement it (that work is entirely RIG-side, out of scope for this charon-repo ticket).

  ## Accept (all must pass)
  - `grep -rn "ActualsLedger\|ActualRow" src/ tests/` → zero hits.
  - `PYTHONPATH=src python3 tools/check_inert_code.py` → no longer flags them (they no longer
    exist to flag).
  - `PYTHONPATH=src python3 -m pytest -q` → full suite green (no orphaned test imports of the
    deleted module).
  - A new charon-private board ticket file exists for the TSV-append unification (finding 6),
    referencing TOOL-AUDIT-REDUNDANCY.md.
scope: |
  Manually-decomposed single-domain sub-ticket of DEDUP-GRAPHS-LEDGERS (fleet/decompose.sh).
