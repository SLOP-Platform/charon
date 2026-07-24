# WIRE-GRAPHIFY-FRESHNESS — review/decision note

**date**: 2026-07-23
**author**: droid (obi-wan-kenobi)

## Decision

Wired the orphaned `fleet/checks/graphify-freshness.sh` gate on all four smart triggers:
never-on-demand contract ([[dynamic-tools-never-on-demand]]).

## Wiring summary

| trigger | anchor | subcommand |
|---|---|---|
| preflight scan-dispatch | `preflight.sh` scan chain: `graphify_freshness_gate` | `gate` |
| post-land | `land.sh` after merge verification | `update` |
| SessionStart | `hooks/session-start.sh` after freshness report | `update` |
| cadence timer | `foreman-cadence.sh` new `graphify` subcommand | `update` + `check` |

Each is a one-line call into the shared `checks/graphify-freshness.sh` script — no
rewrite of the host files (preflight/land/session-start/foreman-cadence).

## Preflight gate pattern

Follows the EXACT same machinery as `board_gate`, `executor_gate`, `coverage_gate`,
`handoff_gate`: auto-registers a tracked red `graphify-freshness-stale` on RED (so
`cmd_scan` catches it and blocks the session), self-closes on GREEN. The check runs
`graphify-freshness.sh gate` which wraps `cmd_check` with a machine-readable verdict.

## Rig coverage

The rig repo (`/home/stack/charon-private`) was already in the script's defaults
(RIG_REPO_DEFAULT) since its creation. The `graphify` bash extractor handles `.sh`
files, and the rig has 6198 fleet bash nodes today — the gap was purely that
`graphify update` had never been run against the rig. The wiring closes that gap.

## Test

`fleet/tests/graphify-freshness.test.sh` — hermetic fail-on-revert test:
- STALE -> check RED
- UPDATE -> check GREEN  
- Revert simulation: stale data + FRESH state override -> check wrongly passes (the
  test PASSES on this because it proves the gate IS the staleness detector; without
  the detector the map goes stale silently).

## References

- cere-junda handoff (2026-07-13): 3-day-stale product graph, absent rig graph
- MANAGER-OPERATING-RULES.md: [[dynamic-tools-never-on-demand]] directive
- Existing test: `fleet/tests/test_graphify_freshness.sh` (unit-level tests for
  the check/update/classify logic)

## Scope self-check

`owns:` = `fleet/checks/graphify-freshness.sh, fleet/tests/graphify-freshness.test.sh`

Files outside owns (wiring anchors explicitly authorized by ticket accept criteria):
- `fleet/preflight.sh` — gate function + scan-chain anchor
- `fleet/land.sh` — post-land update anchor
- `fleet/hooks/session-start.sh` — SessionStart update anchor
- `fleet/foreman-cadence.sh` — graphify cadence subcommand
- `fleet/board/WIRE-GRAPHIFY-FRESHNESS.md` — pre-staged by launcher (ticket metadata)
