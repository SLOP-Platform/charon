# PREFLIGHT-OWNERSHIP-RULING — 2026-07-26

Arbitration of the five-way `fleet/preflight.sh` owns-collision RED.
Ruled by mace-windu (deepseek-v4-pro, charon/* gateway).

## EVIDENCE — PREFLIGHT-GATE-RUN-HELPER IS THE ANCHOR

PREFLIGHT-GATE-RUN-HELPER appears in all four collision pairs because it is the ONLY one of
the five that is NOT transitively connected to the existing preflight.sh edit chain. The other
four form a chain: SYNC-SCHEDULE → REPO-MAP-CONVERGE → MARKER-PROOF-MECHANIZE → RECONCILE-WIRING.
PG-R-H depends only on WCI-CONTENTION-TEETH (archived/done — terminal), leaving it disconnected
from every member of the chain. Confirmed from the tickets, not assumed.

Every ticket was READ, not pattern-matched. Every one genuinely needs fleet/preflight.sh for the
edits it describes. None can be narrowed, none can be merged, none can be retired. The single
missing edge is: PG-R-H must precede the chain. It rewrites the gate-run infrastructure (fail-open
→ fail-closed, `|| true` mask removal, vacuity guard) that the chain members' gate insertions
(MARKER-PROOF-MECHANIZE, RECONCILE-WIRING) and call-site fixes (REPO-MAP-CONVERGE, SYNC-SCHEDULE)
should be built on top of.

## DISPOSITIONS

### 1. PREFLIGHT-GATE-RUN-HELPER → SEQUENCE
**Evidence:** AC §L rewrites how ALL gate legs in preflight.sh invoke checks (fail-open → fail-closed),
§M removes the `|| true` mask on `cmd_add`, §N adds a vacuity guard on the scan chain. These are the
gate-run INFRASTRUCTURE that gate-inserting tickets (MARKER-PROOF-MECHANIZE, RECONCILE-WIRING) must
build on. Already properly sequenced after WCI-CONTENTION-TEETH (archived — decomposition complete).
No edit needed to this ticket. It is the new chain HEAD.

### 2. SYNC-SCHEDULE → SEQUENCE
**Evidence:** AC §1 adds sync-checkouts.sh invocation at the top of preflight.sh — a real edit to the file.
Already the chain head of the existing four-ticket chain. Must be sequenced AFTER PG-R-H so the sync
wiring is applied on top of fail-closed infrastructure. **Edit required** — add PG-R-H to `depends_on:`.

### 3. REPO-MAP-CONVERGE → SEQUENCE
**Evidence:** AC §b makes `_vm_refresh` ticket-aware at preflight.sh:383, :438 — real call-site edits
inside `detect_needs_push` and `done_merge_gate`. Already properly depends_on SYNC-SCHEDULE. The
transitive ordering through SYNC-SCHEDULE → PG-R-H is sufficient; no edit needed.

### 4. MARKER-PROOF-MECHANIZE → SEQUENCE
**Evidence:** LAYER 2 inserts `fleet/checks/marker-proof.sh` into the preflight.sh scan chain at :841 —
a real gate insertion. Already properly depends_on REPO-MAP-CONVERGE (real-dep). The transitive
ordering through REPO-MAP-CONVERGE → SYNC-SCHEDULE → PG-R-H is sufficient; no edit needed.

### 5. RECONCILE-WIRING → SEQUENCE
**Evidence:** §3(1) inserts four reconcile-*.sh calls into the preflight.sh:841 scan chain — real gate
insertions. Already properly depends_on MARKER-PROOF-MECHANIZE (real-dep). The transitive ordering
through MARKER-PROOF-MECHANIZE → REPO-MAP-CONVERGE → SYNC-SCHEDULE → PG-R-H is sufficient; no edit
needed.

## REQUIRED EDIT — apply verbatim

In `fleet/board/SYNC-SCHEDULE.md`, change line 13 from:

```
depends_on: STARTUP-CONTEXT-DIET, FOREMAN-WIRE
```

to:

```
depends_on: STARTUP-CONTEXT-DIET, FOREMAN-WIRE, PREFLIGHT-GATE-RUN-HELPER
```

And add after the existing `real-dep: STARTUP-CONTEXT-DIET` block (after line 17) a new real-dep block:

```
real-dep: PREFLIGHT-GATE-RUN-HELPER — shared single-owner of fleet/preflight.sh, and a real build
  prereq: it rewrites the gate-run infrastructure (fail-open -> fail-closed, cmd_add || true mask
  removal, vacuity guard) that this ticket's preflight.sh wiring sites (sync-checkouts at top of
  preflight) must land on top of. Without it, the sync invocation would run inside a chain that
  still fails open — a new gate leg inheriting the very class of defect this wave exists to close.
  dep-kind: build.
```

No other ticket edits. The transitive ordering becomes:

```
WCI-CONTENTION-TEETH (done) → PREFLIGHT-GATE-RUN-HELPER → SYNC-SCHEDULE → REPO-MAP-CONVERGE → MARKER-PROOF-MECHANIZE → RECONCILE-WIRING
```

## DRY-RUN PROOF

### Current validate_board.sh RED output (pre-ruling)

```
RED  owns-collision LIVE (no dep ordering): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE  [MARKER-PROOF-MECHANIZE|PREFLIGHT-GATE-RUN-HELPER, PREFLIGHT-GATE-RUN-HELPER|RECONCILE-WIRING, PREFLIGHT-GATE-RUN-HELPER|REPO-MAP-CONVERGE, PREFLIGHT-GATE-RUN-HELPER|SYNC-SCHEDULE]
```

### Predicted post-ruling output

The `fleet/preflight.sh` owns-collision RED line is **CLEARED** — all five tickets are transitively
ordered via `depends_on` edges. It will report as INFO:

```
INFO owns hand-off (dep-sequenced/historical, ok): fleet/preflight.sh <- MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE
```

### Remaining REDs (NOT caused by this collision, UNCHANGED by this ruling)

```
RED  owns-collision LIVE (no dep ordering): fleet/fleet-droid.sh <- DROID-CLIENT-PREFLIGHT-PATH DROID-LIFECYCLE-REAP FLEET-DEMAND-BROKER FLEET-DEMAND-DRIVEN-ROUTING LAUNCHER-CRASH-PARTIAL-DETECT
RED  gate-parity: GATE-PARITY: parallelizability: WIRE-GRAPHIFY-FRESHNESS would be refused at launch ...
```

These are separate tickets, separate files, separate rulings.
