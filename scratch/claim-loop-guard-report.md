# Claim-loop durable fix + tests (2026-07-09)

RIG-ONLY. No product source touched. Not committed/pushed. Live `fleet/state` not disturbed
(all runtime writes go to temp dirs in tests; `state/loop-guard/` is created only at droid
runtime and does not exist now).

## Root cause (recap)
`claim.sh` skipped a board ticket only if it had a `state/claims|submitted|done/<id>` marker.
It did NOT honor PARK. `BENCH-OOB-GRADING.md` carried `note: PARKED` but no marker, so it was
offered forever: a droid claimed it → build refused (parked → 0 commits) → `release.sh`
deleted `claims/<id>` → the `fleet-droid.sh` loop re-claimed the SAME id → infinite no-commit
spin that also starved the next ready ticket (`NORMALIZE-CASE-QUANT-FIX`).

## Changes

### 1. First-class PARK in `fleet/claim.sh` (claim.sh:34-43)
In the claim loop, right after the marker checks, added three data-only skips (awk `meta`,
no Python under the flock):
- `case "$(meta parked "$f" | tr A-Z a-z) in true|yes|1) continue` — clean `parked: true` field.
- `case "$(meta note "$f") in *PARKED*) continue` — fallback: a `note:` containing PARKED.
- `[ -e "$STATE/loop-guard/$id" ] && continue` — loop-guard quarantine marker (fix 2).

### 2. Loop-guard in `fleet/fleet-droid.sh` + new `fleet/loop-guard.sh`
- `loop-guard.sh` (new): `record <id> <droid> [N=2] | clear <id> | list`. Per-run counter at
  `state/loop-guard/runs/<droid>/<id>` (droid id carries the PID → per-run). On the Nth
  zero-commit release of the SAME id it writes a durable `state/loop-guard/<id>` marker,
  prints a `LOOP-GUARD ESCALATION:` line, and exits 2. `clear` removes the marker.
- `fleet-droid.sh`: calls `loop-guard.sh record` on BOTH zero-commit release paths — the
  "produced NO commits" path (fleet-droid.sh:~91-97) and the non-zero-exit path
  (fleet-droid.sh:~118-124). After N=2, claim.sh skips the id (marker) so the loop falls
  through to the next ticket instead of spinning; escalation is always emitted (never silent).
  Normal empty-board retry (`--wait`/`--retries`) is untouched. `cleanup()` (fleet-droid.sh:~42-46)
  removes the per-run counter dir on exit; the durable quarantine marker persists for the manager.

### 3. `fleet/validate_board.sh` checks (validate_board.sh)
- Added `is_parked(d)` (matches claim.sh's rule exactly) + `inactive(t) = done or parked`;
  parked tickets are now exempt from the live-ticket gates (missing-prompt, work_class,
  owns-collision, WCI, D&S) — a parked ticket may have an unwritten prompt / provisional owns.
- New PARK section (before D&S):
  - **PARK-1 parked-but-claimed**: parked ticket that also holds a `state/claims/<id>` marker → RED.
  - **PARK-2 parked-note-only**: parked via `note:` text but no explicit `parked: true` field → RED
    (the exact inconsistency that caused the loop; drives the clean field).
  - **PARK-3 build-after-unenforced**: a NON-parked live ticket whose `build-after` predecessor
    is not done (or itself parked) → RED (claim.sh ignores build-after → premature claim).
    Resolves predecessors that live only as `*.md.parked` too.

### 4. `fleet/preflight.sh` detector (preflight.sh, `detect_claim_loop`, wired into `cmd_detect`)
Active detector: reports any `state/loop-guard/<id>` quarantine marker (the runtime signature
of "same droid re-claimed+released the same id with 0 commits") as unregistered risk, with the
manager remediation hint. Reports `clean: claim-loop` when none. Never mutates state.

### 5. Fail-on-revert tests — `fleet/tests/claim-loop-guard.test.sh`
Self-contained bash (matches the rig's selftest style). Builds an isolated TEMP fleet (copies
claim.sh/_lib.sh/loop-guard.sh/release.sh + fixture board + fixture state) — never touches live
`fleet/state`. 9 assertions, all PASS:
- **(a1)** `parked: true` field skipped → claims the next ready ticket (parked sorts first, so a
  reverted skip claims the parked ticket → FAIL).
- **(a2)** `note: PARKED` fallback skipped likewise.
- **(b1-b5)** `loop-guard record` counts 1/2 (exit 0, no marker), then quarantines at 2 (exit 2,
  marker written, escalation emitted).
- **(b6)** claim.sh skips the quarantined id → claims the next ticket (reverted guard/skip →
  claims the quarantined id → FAIL).
- **(b7)** `clear` removes the marker.

**Fail-on-revert proven** by stripping each fix in a temp copy: reverted park-skip → claim
returns `PARKED-FIELD` (test expects `READY-A`); reverted guard (stub `loop-guard.sh`) → no
marker + claim returns `LOOPY` (test expects `MNEXT`).

Pass output:
```
PASS: a1 parked:true field is skipped -> claims READY-A
PASS: a2 note: PARKED fallback is skipped -> claims ZZZ-READY
PASS: b1 first record exits 0 (no quarantine yet)
PASS: b2 no marker after 1st release
PASS: b3 second record exits 2 (quarantined)
PASS: b4 quarantine marker written
PASS: b5 escalation line emitted
PASS: b6 claim.sh skips quarantined id -> claims MNEXT
PASS: b7 clear removes marker
--- 9 passed, 0 failed ---
ALL CLAIM-LOOP-GUARD TESTS PASS
```

### 6. BENCH-OOB-GRADING re-represented (RESTORED)
Verified claim.sh skips `parked: true` (test a1) → restored
`fleet/board/BENCH-OOB-GRADING.md.parked` → `fleet/board/BENCH-OOB-GRADING.md` and added
`parked: true` (kept the existing note + build-after Q1/#20 gating). `validate_board.sh` after
restore shows only the SAME 6 pre-existing orphan-markers (unrelated, pre-existing) — no new
reds, no traceback; the parked ticket is exempt from liveness checks and skipped by claim.sh.

## Regression / live-droid safety
- `validate_board.sh` before and after = identical 6 pre-existing orphan-markers (not mine).
- No live `fleet/state` writes; `state/loop-guard/` still absent.
- claim.sh/release.sh remain backward-compatible: running droids invoke them fresh each loop
  and pick up the new (additive) skips; their in-flight tickets are neither parked nor
  quarantined, so nothing they were doing is affected.

## Files
- M `fleet/claim.sh`, `fleet/fleet-droid.sh`, `fleet/validate_board.sh`, `fleet/preflight.sh`,
  `fleet/board/BENCH-OOB-GRADING.md`
- A `fleet/loop-guard.sh`, `fleet/tests/claim-loop-guard.test.sh`
