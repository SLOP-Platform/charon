# GATE-INTEGRITY-A — inert side

**Status:** done  
**Date:** 2026-07-13  

## Changes

1. **§2a** — Stripped `# @covers: inert-graph-coupling` from `tools/inert_to_graph.py`.
   The annotation referenced no gate in `tools/gates.json`, producing an orphan-covers
   failure in `check_gate_registry.py`. The script is a diagnostic-only tool with no
   invariant/exit-code contract, so no gate coverage is needed.

2. **§3** — `tools/check_inert_code.py` already monkeypatches `_ksf_impl._EXCLUDE_DIRS`
   to include `.claude/`, caches, build dirs, etc. Verified deterministic output across
   3 runs with `.claude/worktrees/` present.

3. **§4** — Applied inert triage to `tools/inert-code-disposition.json`:
   - Deleted `charon.capability.actuals.ActualRow` and `charon.capability.actuals.ActualsLedger`
     entries (both stale — detector no longer flags them; actuals.py symbols became reachable
     via test imports).
   - Maintained `keep-pending-wire` for `ReviewerCircuitBreaker`/`next_entry`/`proxy_excluded_keys`.
   - All remaining entries unchanged with existing dispositions.

## Verification

- `PYTHONPATH=src python3 tools/check_inert_code.py` → OK (28 dead, 28 tracked)
- `PYTHONPATH=src python3 tools/check_gate_registry.py` → no ORPHAN-COVERS
