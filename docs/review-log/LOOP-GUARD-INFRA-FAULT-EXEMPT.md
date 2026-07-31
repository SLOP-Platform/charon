# LOOP-GUARD-INFRA-FAULT-EXEMPT — review log

**Date:** 2026-07-23
**Author:** fleet-droid (automated)

## Change summary

`loop-guard.sh` now accepts an optional `--reason <reason>` flag on the `record`
command. When the reason is an infra classification (exhausted, pool-too-thin,
red-board, gateway-reset, launcher-refused, etc.), the zero-commit release does
NOT count toward the quarantine threshold — it is tracked separately under
`state/loop-guard/infra/<id>` for observability but will never quarantine.
No `--reason` (backward-compatible) or `--reason genuine` still quarantines as
before.

The `list` command now surfaces both QUARANTINED tickets and INFRA-RETRY tracked
tickets, with counts, so a starved priority ladder is never silent.

## Design decisions

- **Reuse existing attribution, don't re-derive.** The infra-vs-genuine
  classification already lives in `charon-run.sh`'s `is_infra_fault()` and the
  per-leg failover branches. `loop-guard.sh` exposes the `--reason` knob; the
  `fleet-droid.sh` call sites wire it (separate step — not in this ticket's
  owns: to avoid double-claim violations). The knob exists now; wiring follows.

- **Safe default.** Unknown/invalid reasons default to quarantine (treat as
  genuine). No --reason stays backward-compatible. The only way to skip
  quarantine is to explicitly pass a recognized infra reason.

- **Infra counter is separate, never expires to quarantine.** Infra-only
  releases accumulate a count under `state/loop-guard/infra/<id>` but there is
  no threshold — infra faults never permanently exclude a ticket. This counter
  is purely for observability and diagnosis.

- **Fail-on-revert test (d1).** The test suite includes a revert simulation:
  it copies `loop-guard.sh`, surgically removes the `infra_reason` guard with
  `sed`, and asserts that an infra-fault record then DOES quarantine on the 2nd
  release. If the infra exemption is removed (reverted), this test goes RED.

## Test results

```
fleet/tests/loop-guard-infra-exempt.test.sh: 36 passed, 0 failed
fleet/tests/claim-loop-guard.test.sh:         9 passed, 0 failed  (regression-free)
```

## Follow-on

Wire `fleet-droid.sh`'s four `loop-guard.sh record` call sites to pass the
appropriate `--reason` based on the run outcome (e.g., read `CHARON_RUN_RESULT`
from the outlog when the agent exits non-zero; pass `--reason exhausted` when
`EXHAUSTED`/`ALL-EXHAUSTED` appears). That is a separate ticket — touching
`fleet-droid.sh` from this ticket would collide with its own `owns:` list.
