# GATE-PARITY-LAND-VS-LAUNCH — review log

**Built by:** quinlan-vos (deepseek-v4-pro)
**Date:** 2026-07-23
**Root cause:** 2026-07-23 deadlock RCA — strong pool deadlocked because
SUBSTRATE-FIRST-OWNS-BASE-REF landed unlaunchable (no `serial_justified`) then spun
claim->no-op->release and was loop-guard-quarantined.

## What changed

### New files
- `fleet/checks/gate-parity.sh` — LAND-LAUNCH PARITY GATE. Re-runs launch-refusal
  predicates at LAND time and FAILS HARD if a board ticket would be refused at launch.
  Delegates predicate P1 (parallelizability) to `parallelizability-gate.sh check <tid>`.
  Predicate set is an explicit bash array (`GATE_PREDICATES`) — extensible by adding a
  `pred_<name>` function and appending to the array. Fail-CLOSED: a missing/malfunctioning
  predicate script => RED, never silently pass through.
- `fleet/tests/gate-parity.test.sh` — Control-plane flow-canary. Hermetic seed->assert->revert
  pattern (mirrors flow-canary.test.sh). 20 test cases covering:
  - F1: splittable-unjustified RED, add `serial_justified` GREEN, revert RED
  - F2: board-wide scan: one offender RED, fix GREEN, revert RED
  - F3: non-splittable ticket GREEN (no false alarm)
  - F4: decomposed ticket GREEN
  - F5: CLI `--serial-justified` baseline
  - F0: fail-closed (missing predicate script => RED)
- `docs/review-log/GATE-PARITY-LAND-VS-LAUNCH.md` — this file

### Wiring anchor (not part of this change — `owns:` excludes validate_board.sh)

To wire `gate-parity.sh` into the LAND path, replace `validate_board.sh` lines 385-399
(the WCI-ADVISORY parallelizability-gate scan) with a HARD gate-parity check:

```python
# F46 → GATE-PARITY: HARD land-launch parity check (replaces the advisory parallelizability
# scan at lines 385-399). Delegates to fleet/checks/gate-parity.sh scan, which re-runs EVERY
# launch-refusal predicate and FAILS HARD if a ticket would be refused at launch.
try:
    _gp = subprocess.run(
        ["bash", os.path.join(fleet, "checks", "gate-parity.sh"), "scan"],
        capture_output=True, text=True, timeout=30
    )
    if _gp.returncode != 0:
        for _line in (_gp.stdout.strip() + "\n" + _gp.stderr.strip()).splitlines():
            if _line.strip():
                red.append(f"gate-parity: {_line.strip()}")
except Exception as e:
    red.append(f"gate-parity-check-failed: could not run gate-parity.sh — {e}")
```

The existing real board is already GREEN under the new gate (all live tickets are currently
justified or not-splittable).

## Design decisions

1. **Predicate set is explicit + extensible** — `GATE_PREDICATES` bash array. Start with
   parallelizability (P1, the direct cause of the deadlock). Future predicates (assign.py
   availability, context-fit) can be added by defining a `pred_<name>` function and appending.
2. **Delegates, doesn't reimplement** — `pred_parallelizability` calls
   `parallelizability-gate.sh check <tid>` with `PARALLEL_GATE_BOARD`/`PARALLEL_GATE_DONE_DIR`
   env vars passed through. Single source of truth for the parallelizability check logic.
3. **Fail-CLOSED by default** — any unrunnable predicate (missing script, exit 2 error) => RED.
   A gate that silently passes when its dependencies are broken is worse than no gate.
4. **Test proves RED-then-GREEN** — every fault case seeds a fault, proves the gate REDs,
   then reverts and proves the gate returns GREEN. "GREEN-is-not-proof" — the canary ensures
   the gate actually detects its target fault class.
5. **No `validate_board.sh` edit** — the `owns:` line is the single source of truth.
   `validate_board.sh` is owned by other tickets. This change ships the check + test; the
   one-line wiring anchor is documented above for the manager/operator.

## Verification

- `bash fleet/tests/gate-parity.test.sh` — all 20 cases PASS
- `bash fleet/checks/gate-parity.sh scan` — GREEN on the real board (all live tickets justified)
- `bash fleet/validate_board.sh` — still GREEN on the real board
