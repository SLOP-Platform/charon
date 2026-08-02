# LOOP-GUARD-REASON-WIRE review

## Decision
Approved — the wire was structurally dead (zero callers passed `--reason`), making the infra-fault exemption inert. At all 6 call sites in `fleet-droid.sh`, the CHARON_RUN_RESULT from the outlog is now mapped to the reason vocabulary loop-guard.sh already recognizes.

## Changes
- `fleet/fleet-droid.sh`: added `--reason` at all 6 `loop-guard.sh record` call sites:
  - parallelizability-gate refused → bare (ticket fault, quarantine)
  - no runnable chain → `--reason launcher-refused` (infra)
  - work-class-missing → bare (ticket config fault, quarantine)
  - worktree creation failure → `--reason launcher-refused` (infra)
  - SUCCESS + zero commits → `--reason genuine` (model fault, quarantine)
  - non-zero exit → maps `CHARON_RUN_RESULT`: EXHAUSTED→exhausted, PREREQ-MISSING→launcher-refused, SUCCESS→genuine
- `fleet/tests/loop-guard-reason-wire.test.sh`: 21 tests, including fail-on-revert guards for both over-exempt and under-exempt directions

## Verification
The real incident scenario: EXHAUSTED → `--reason exhausted` → infra counter only → ticket stays claimable. Tested: 6 `--reason exhausted` records on one id never quarantine (confirmed infra counter at 6). Revert test confirms that without the exemption, the same 2 records would quarantine.