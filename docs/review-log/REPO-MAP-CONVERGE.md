# REPO-MAP-CONVERGE — review/decision note

## Changes
- `fleet/validate_board.sh`: replaced hand-maintained `REPO_ROOTS` Python dict (3rd copy of the map) with
  `_make_repo_roots()` that shells out to `repo-registry.sh` (canonical source). `PRODUCT_REPO` env
  override (test-fixture support) is preserved for the charon/product key; all other keys come from
  the registry. Fail-closed: an unrunnable registry yields `{}` so unknown-key check fails on everything.
- `fleet/preflight.sh`: added `_vm_refresh "$id"` before `verify_merged "$id"` in both
  `detect_needs_push` (:447) and `done_merge_gate` (:508) per-marker loops. The existing function-level
  `_vm_refresh` (product-only) is kept for backward-compat; the per-marker call refreshes the CORRECT
  repo based on the ticket's `repo:` field.
- `fleet/checks/base-integrity.sh`: changed `_vm_repo` (no arg) to `_vm_repo "$id"` at :63, and
  `_vm_refresh` to `_vm_refresh "$id"` at :73. Also updated the error message at :64 to name the
  resolved repo rather than hardcoding "product repo".
- `fleet/checks/repo-map-single-home.sh` (NEW): gate that scans fleet/*.sh + fleet/checks/*.sh for
  private repo->path maps. Two patterns: (1) a Python `REPO_ROOTS = {...}` dict, (2) a shell case/if
  chain mapping repo keys to hardcoded paths. Allow-lists: `_lib.sh`, `repo-registry.sh`.
- `fleet/tests/repo-map-converge.test.sh` (NEW): 14 assertions across 3 sections:
  (1) NO SECOND MAP — gate detects private REPO_ROOTS and shell case maps, is green on clean fixture,
      --warn stays advisory, runs on real fleet dir
  (2) STALE RIG REF — _vm_repo resolves to correct repo per ticket, verify_merged uses correct repo,
      product sha correctly rejected for rig ticket, _vm_refresh targets correct repo
  (3) VALIDATOR READS THE ONE MAP — known keys accepted, unknown keys rejected, registry change
      changes accepted keys (proves the validator follows the registry, not a hardcoded dict)

## Test evidence
- `repo-map-converge.test.sh`: 14/14 PASS
- `base-integrity.test.sh`: 12/12 PASS  
- `verify-merged-repo-aware.test.sh`: 0 failures
- `repo-field-required.test.sh`: 10 failures PRE-EXISTING (fixture doesn't have `checks/gate-parity.sh`,
  which was added after that test was written; not caused by this change)

## Decision
All 5 owned files changed. No off-scope file touched. Gate is GREEN.
