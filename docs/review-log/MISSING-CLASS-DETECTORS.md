# MISSING-CLASS-DETECTORS — Review Log

## Decision: Build detectors before registry lands
FLEET-STATUS-BOARD (obi-wan-kenobi) is implementing the registry + runner. Per the ticket's dependency note, the status board should land FIRST so detectors have somewhere to register. At build time, CHECK-REGISTRY.tsv does not yet exist — the status board hasn't landed. This detector is built with the uniform contract so registration is a mechanical step once the registry is available.

## Decision: All nine classes in one harness
The ticket explicitly says "One detector harness with one output contract consumed by one registry." Splitting into separate scripts per class means N tabs inventing N output shapes the status board then cannot consume uniformly. All nine class detectors live in `fleet/checks/class-detectors.sh` with `--class <id>` for individual invocation.

## Decision: First three classes implemented with pure local git
Classes 1-3 (uncommitted-tools, untracked-reviews, crontab-registration) are pure local git + filesystem — zero network, zero gh, zero live state. They have full hermetic FAIL-ON-REVERT tests. Classes 4-9 are implemented but several need live state (deploy-drift needs gh REST, daemon-liveness needs running processes). The BROKEN verdict is used when the detector's prerequisites are not available on the current box.

## Decision: ADOPT existing tools, not reimplement
Where a tool already answers a class, it is wired, not reimplemented: git for classes 1-2, crontab for class 3, gh REST for deploy-drift, existing pricing CSV for catalog-rot, pgrep for daemon-liveness, claim-jedi-name.sh for name-pool-exhaustion. The novel slice is the uniform verdict contract.

## Decision: pending.sh --key for escalation
The cron wrapper (future ticket, mirroring stranded-work-cron.sh) will use `pending.sh add --key "CLASS DETECTORS:"` for keyed upsert — one standing row whose value changes, not ~72 rows/day.

## Verified
- All 31 tests pass (hermetic, no network)
- reentrancy guard tested
- Structural integrity: every class produces output (section F in test)
