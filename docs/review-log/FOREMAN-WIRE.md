# FOREMAN-WIRE — Review Log

## Ticket
Wire foreman.sh into preflight.sh scan (report-only, advisory), surface STARVE/COLLISION/OK verdict prominently in operator-actions output.

## What was done
- **fleet/preflight.sh**: Added `foreman_advisory` function that runs `foreman.sh` without `--fix` (report-only, never acts). Captures the `== FOREMAN VERDICT:` line into `FOREMAN_VERDICT_LINES` global. Wired into the `scan` dispatch (non-blocking, advisory). Modified `show_operator_actions` to surface the verdict wrapped in `!! ... !!` for loud prominence.
- **fleet/tests/test_foreman_wire.sh**: Hermetic fixture with symlinked callees. Tests: (a) empty board -> STARVE surfaces loudly in foreman output + operator actions, NEVER `--fix`; (b) fully fed board -> OK surfaces, no false alarm.

## Scope self-check
Only changed files: `fleet/preflight.sh` (M), `fleet/tests/test_foreman_wire.sh` (new). Both in `owns:`.

## Test summary
`bash fleet/tests/test_foreman_wire.sh` -> 7/7 PASS.
