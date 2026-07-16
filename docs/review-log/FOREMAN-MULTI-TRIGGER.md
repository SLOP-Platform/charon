# FOREMAN-MULTI-TRIGGER review log

## What changed

Applied [[dynamic-tools-never-on-demand]] to the foreman. FOREMAN-WIRE wired it
into preflight ONLY; this adds the missing trigger points so the tier-health
surface updates at every relevant lifecycle event — never stale more than the
cadence interval.

## Files created/modified

| File | Change |
|---|---|
| `fleet/foreman-cadence.sh` | NEW — multi-trigger dispatcher with 4 subcommands: `session-start`, `post-land`, `handoff`, `cadence`. Each runs foreman.sh report-only (NEVER `--fix`). |
| `fleet/handoff.sh` | Added `### Foreman tier-health (auto)` section in auto-generated state, calling `foreman-cadence.sh handoff`. |
| `fleet/tests/test_foreman_triggers.sh` | NEW — 4 triggers × starving/fed/fail-on-revert. |

## Trigger design

| Trigger | When | Mechanism |
|---|---|---|
| `session-start` | SessionStart hook | Entry point in foreman-cadence.sh; wire into `~/.claude/settings.json` SessionStart hooks or `fleet/hooks/session-start.sh` |
| `post-land` | After a merge/land | Entry point in foreman-cadence.sh; wire into `land.sh` post-merge or via land-push.sh wrapper |
| `handoff` | handoff.sh | Wired directly — auto-generated state section emits foreman verdict + fenced block |
| `cadence` | Timer/cron backstop | Entry point in foreman-cadence.sh with interval gate (`FOREMAN_CADENCE_INTERVAL`, default 30m) |

## Constraints honored

- All triggers are report-only (never `--fix`); acting stays a manager decision.
- `foreman-cadence.sh` uses the same `FOREMAN_FLEET` test seam as `foreman.sh`.
- Hermetic test fixture mirrors `test_foreman_wire.sh` patterns.
