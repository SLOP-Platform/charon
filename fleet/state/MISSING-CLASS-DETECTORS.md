# MISSING-CLASS-DETECTORS — State & Design

## Implementation date
2026-08-02

## Status
All nine class detectors implemented in `fleet/checks/class-detectors.sh`.

## Classes covered

| # | Class ID | Detection method | Status |
|---|---|---|---|
| 1 | uncommitted-tools | git ls-files --others (untracked in tools/) | IMPLEMENTED |
| 2 | untracked-reviews | filesystem: review-log entries without reviewed/ markers | IMPLEMENTED |
| 3 | crontab-registration | crontab -l + filesystem path validation | IMPLEMENTED |
| 4 | config-ssot-keys | code scan vs CONFIG-SOURCES.tsv cross-reference | IMPLEMENTED |
| 5 | deploy-drift | gh REST deployment API vs origin/master rev-parse | IMPLEMENTED |
| 6 | catalog-rot | pricing CSV scan for zero/missing price entries | IMPLEMENTED |
| 7 | daemon-liveness | process table pgrep vs service-registry.tsv retirement dates | IMPLEMENTED |
| 8 | name-pool-exhaustion | claim-jedi-name.sh pool stats | IMPLEMENTED |
| 9 | operator-staleness | OPERATOR-ACTIONS.md item count + age estimation | IMPLEMENTED |

## Uniform contract

Every class emits:
```
CLASS[<class-id>] verdict=<OK|FINDING(n)|STALE|BROKEN> summary="<one-line>" recover="<command>"
```

- **OK**: class is clean, nothing to report
- **FINDING(n)**: n issues found, each emitted as a separate line
- **STALE**: detector ran but output is too old (heartbeat check)
- **BROKEN**: detector cannot run (tool missing, unreadable state)
- `summary`: one-line description of the finding or clean state
- `recover`: exact command to fix or investigate

## Registration

To register with FLEET-STATUS-BOARD (ticket FLEET-STATUS-BOARD), add each class to CHECK-REGISTRY.tsv with the format the status board expects. The detector script path is `fleet/checks/class-detectors.sh`. Each class can be invoked individually with `--class <id>`.

## Cron cadence

A cron wrapper analogous to `fleet/checks/stranded-work-cron.sh` should invoke this detector on a 20-minute cadence. The wrapper must:
1. Write a heartbeat file on every invocation (anti-silence)
2. Use `pending.sh add --key "CLASS DETECTORS:"` for keyed upsert escalation
3. Hash the finding state to avoid churn on identical runs

## FAIL-ON-REVERT

Every class has a corresponding test in `fleet/tests/class-detectors.test.sh` that seeds the exact condition and proves the detector FIRES. A detector never seen to fire is not a detector.

## Dependencies

- FLEET-STATUS-BOARD: owns registry + runner + meta-check; this detector IS the input it registers
- No other inbound deps
