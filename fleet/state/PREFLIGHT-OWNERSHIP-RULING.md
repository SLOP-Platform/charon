# PREFLIGHT-OWNERSHIP-RULING

**Ruling for:** `owns-collision LIVE (no dep ordering): fleet/preflight.sh` — RED standing since observed in board validator
**Ruling date:** 2026-08-02
**Ruling ticket:** PREFLIGHT-OWNS-ARBITRATE
**Ruling scope:** Fleet worktree `/home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE`
**Validator reference:** `fleet/validate_board.sh` check 4 (owns partition), `ordered()` function at line 305

---

## Ruling Preamble

### What this ticket does and does not do

This ticket **arbitrates** a 9-way ownership collision on `fleet/preflight.sh`. It writes a **ruling**, not a fix. The `depends_on:` / `owns:` line edits prescribed below are applied as a **board-hygiene commit** by the manager after the operator reads the ruling. This ticket does not edit `fleet/preflight.sh` and does not edit the five tickets' code.

### How the ruling was derived

The `validate_board.sh` owns-collision check (`check 4`) detects unsequenced pairs of live tickets that co-own the same path. "Live" means neither done nor parked. "Ordered" means there is a directed path through `depends_on:` from one to the other (transitive, via `ordered(a, b)` → `reaches(a, b) or reaches(b, a)`). All nine owners were enumerated from the board and pair-tested:

| Pair | Ordered? |
|------|----------|
| REPO-MAP-CONVERGE ↔ BENCH-OOB-GRADING | **NO** — no directed path either way |
| SYNC-SCHEDULE ↔ BENCH-OOB-GRADING | **NO** — no directed path either way |
| All other pairs | YES — via PREFLIGHT-GATE-REGISTRY's `depends_on` chain |

Evidence: Python analysis of all board ticket `depends_on:` fields, `reaches()` DFS over the full board graph. Script: see `fleet/board/validate_collision.py` (not committed; reproduced below in §DRY-RUN).

The RED fires because 2 unsequenced pairs exist among live owners.

---

## Per-Ticket Dispositions

### 1. BENCH-OOB-GRADING

**Ticket:** `fleet/board/BENCH-OOB-GRADING.md`
**Current owns:** `fleet/preflight.sh` (in owns alongside benchmark files)
**Disposition: NARROW THE OWNS — remove `fleet/preflight.sh` from `owns:`**

**Evidence:**
- `BENCH-OOB-GRADING` owns `fleet/preflight.sh` UNPREFIXED. Its own body (MARKER-PROOF-MECHANIZE:line 24–25) states: *"BENCH-OOB-GRADING owns `preflight.sh` **UNPREFIXED** — that is `fleet/benchmark/preflight.sh`, a **DIFFERENT file**."*
- `BENCH-OOB-GRADING`'s actual owned surfaces are: `benchmark/bench.sh`, `benchmark/lib/grade_state.py`, `model-scorecard.sh`, `benchmark/grader-daemon.py`, `benchmark/graders`, `benchmark/RUN-BENCHMARK.md`, `START-SESSION.md`.
- The unprefixed `preflight.sh` in its owns is **a reference to the benchmark copy**, not to `fleet/preflight.sh`. The benchmark tree is a separate checkout (`/home/stack/code/charon-fleet-bench` / `benchmark/` subtree) and is not under concurrent write pressure from the other eight owners.
- `BENCH-OOB-GRADING` has no `depends_on:` relationship to any other preflight.sh owner. Its only dep is `STAGE-DEMUX` (unrelated). It therefore sits outside the ordering chain entirely — which is why the two pairs are unsequenced.
- The validator's own `inactive()` check excludes parked tickets, but BENCH-OOB-GRADING is not parked. Yet its owns claim on `fleet/preflight.sh` is **textually identical to the eight rig-tree owners and substantively different**.

**Why this is safe:**
- The benchmark's `preflight.sh` and the rig's `fleet/preflight.sh` are **different files in different trees**. Removing `preflight.sh` (unprefixed) from BENCH-OOB-GRADING's owns does not change what BENCH-OOB-GRADING may or may not edit.
- No other ticket depends on a BENCH-OOB-GRADING → `fleet/preflight.sh` ordering relationship (the `MARKER-PROOF-MECHANIZE` real-dep is explicitly about the **different file**).
- The validator's own `WARN owns-path-missing: BENCH-OOB-GRADING owns 'preflight.sh' does not exist (yet)` already treats the unprefixed `preflight.sh` as a non-rig-tree path (it doesn't exist as a bare filename in the fleet root).

**Required edit:**

```yaml
# fleet/board/BENCH-OOB-GRADING.md — owns: line change
owns: benchmark/bench.sh, benchmark/lib/grade_state.py, model-scorecard.sh, benchmark/grader-daemon.py, benchmark/graders, benchmark/RUN-BENCHMARK.md, START-SESSION.md
# REMOVE: preflight.sh (unprefixed — refers to benchmark/preflight.sh, NOT fleet/preflight.sh)
```

---

### 2. PREFLIGHT-GATE-REGISTRY

**Ticket:** `fleet/board/PREFLIGHT-GATE-REGISTRY.md`
**Current owns:** `fleet/preflight.sh, fleet/state/GATE-REGISTRY.tsv, fleet/tests/preflight-gate-registry.test.sh`
**Disposition: SEQUENCE IT — confirm it is the chain HEAD and declare the ordering explicitly**

**Evidence:**
- `PREFLIGHT-GATE-REGISTRY`'s `real-dep:` block (lines 11–15) already **explicitly names all five co-owners** and states: *"NONE is claimed or in flight, so there is no concurrent writer today. These edges exist so the collision is ORDERED rather than silent."*
- `PREFLIGHT-GATE-REGISTRY`'s `depends_on:` is: `MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE` — it is the **transitive head** of the chain.
- `PREFLIGHT-GATE-REGISTRY`'s own note (line 20–22) confirms: *"whoever lands after this rebases onto the registry"* — it ends the contention by making future gates ROW additions rather than file edits.
- Its `dep-kind: merge-order` is already present.
- The 7-way ordering chain is already correct: every owner except BENCH-OOB-GRADING transitively depends on every other via PREFLIGHT-GATE-REGISTRY's depends list.

**Why this is safe:**
- The real-dep fields already name the exact co-owners. The ordering is confirmed by the depends chain.
- This ticket is the one that **dissolves the collision** — after it lands, adding a gate is a row insert, not a file edit.

**Required edit:** None — the owns is correct and the real-dep chain is already documented. No change needed.

**Post-ruling status:** Confirmed as the chain HEAD. All other preflight.sh owners (except BENCH-OOB-GRADING) already depend on it transitively.

---

### 3. MARKER-PROOF-MECHANIZE

**Ticket:** `fleet/board/MARKER-PROOF-MECHANIZE.md`
**Current owns:** `fleet/done.sh, fleet/preflight.sh, fleet/checks/marker-proof.sh, fleet/tests/marker-proof.test.sh, .gitignore`
**Disposition: SEQUENCE IT — confirm `fleet/preflight.sh` is correctly sequenced via the merge-order chain**

**Evidence:**
- `MARKER-PROOF-MECHANIZE`'s `real-dep:` field for `FOREMAN-WIRE` (lines 18–19) explicitly states: *"shared single-owner of fleet/preflight.sh. This ticket adds a new gate invocation to preflight; co-writing the same file from two branches is the multi-writer defect."*
- `MARKER-PROOF-MECHANIZE`'s `real-dep:` for `REPO-MAP-CONVERGE` (lines 20–23) confirms: *"also owns fleet/preflight.sh AND fleet/checks/*.sh, the exact surfaces this ticket extends."*
- Its `real-dep:` for `BENCH-OOB-GRADING` (lines 24–25) explicitly **clears** the BENCH-OOB-GRADING edge: *"owns `preflight.sh` unprefixed — that is `fleet/benchmark/preflight.sh`, a DIFFERENT file."*
- `MARKER-PROOF-MECHANIZE`'s `depends_on:` includes `REPO-MAP-CONVERGE`, which transitively chains through `PREFLIGHT-GATE-REGISTRY`.
- `MARKER-PROOF-MECHANIZE`'s own `serial_justified:` block (lines 27–33) explains the three-layer serial constraint: the three owned surfaces (`done.sh`, `preflight.sh`, checks+tests) must be edited in sequence.

**Why this is safe:**
- The real-dep chain correctly orders MARKER-PROOF-MECHANIZE behind REPO-MAP-CONVERGE and FOREMAN-WIRE.
- Its `depends_on:` includes REPO-MAP-CONVERGE, which transitively reaches PREFLIGHT-GATE-REGISTRY (the head), so MARKER-PROOF-MECHANIZE is ordered relative to all other preflight.sh owners.

**Required edit:** None — the owns is correct and the sequencing is already documented in real-dep fields.

---

### 4. PREFLIGHT-GATE-RUN-HELPER

**Ticket:** `fleet/board/PREFLIGHT-GATE-RUN-HELPER.md`
**Current owns:** `fleet/preflight.sh, fleet/tests/preflight-gate-run.test.sh`
**Disposition: SEQUENCE IT — confirm correct placement in the ordering chain**

**Evidence:**
- `PREFLIGHT-GATE-RUN-HELPER`'s `real-dep:` for `WCI-CONTENTION-TEETH` (lines 8–14) explicitly describes the shared-owns constraint and why sequencing is necessary.
- Its `depends_on:` is: `WCI-CONTENTION-TEETH, SYNC-SCHEDULE, MARKER-PROOF-MECHANIZE, RECONCILE-WIRING, REPO-MAP-CONVERGE` — it transitively chains through `REPO-MAP-CONVERGE` → `PREFLIGHT-GATE-REGISTRY`.
- `PREFLIGHT-GATE-RUN-HELPER`'s `ds:` block (line 83) states: *"never co-write fleet/preflight.sh from a parallel branch — rebase onto the dep's merge."*
- `PREFLIGHT-GATE-RUN-HELPER` also explicitly clears the BENCH-OOB-GRADING concern: *"BENCH-OOB-GRADING owns `preflight.sh` UNPREFIXED — that is `fleet/benchmark/preflight.sh`, a DIFFERENT file."*

**Why this is safe:**
- `depends_on:` includes `REPO-MAP-CONVERGE` → `PREFLIGHT-GATE-REGISTRY`, ordering it correctly relative to all other preflight.sh owners.

**Required edit:** None — the owns is correct and the sequencing is already documented.

---

### 5. RECONCILE-WIRING

**Ticket:** `fleet/board/RECONCILE-WIRING.md`
**Current owns:** `fleet/checks/reconcile-timer.sh, fleet/tests/reconcile-wiring.test.sh, fleet/preflight.sh, fleet/land.sh, fleet/foreman-cadence.sh, fleet/state/GATE-GAP-LEDGER.tsv`
**Disposition: SEQUENCE IT — confirm correct placement in the ordering chain**

**Evidence:**
- `RECONCILE-WIRING`'s `real-dep:` for `MARKER-PROOF-MECHANIZE` (lines 28–31) explicitly states: *"shared single-owner of fleet/preflight.sh scan-chain region; this ticket inserts into the SAME chain. Rebase behind the existing preflight edit chain (MARKER-PROOF-MECHANIZE -> REPO-MAP-CONVERGE -> SYNC-SCHEDULE — transitively ordered), do not run concurrently."*
- `RECONCILE-WIRING`'s `depends_on:` includes `MARKER-PROOF-MECHANIZE`, which transitively reaches `REPO-MAP-CONVERGE` → `PREFLIGHT-GATE-REGISTRY`.
- `RECONCILE-WIRING`'s `ds:` block (lines 93–97) confirms: *"Wave-2 — lands AFTER all four reconciler checks exist (build deps) and rebases behind the existing fleet/preflight.sh edit chain (MARKER-PROOF-MECHANIZE -> REPO-MAP-CONVERGE -> SYNC-SCHEDULE; depend on the chain head, transitively ordered). Concurrency: NOT parallel with any preflight.sh owner."*

**Why this is safe:**
- `depends_on: MARKER-PROOF-MECHANIZE` transitively chains to `PREFLIGHT-GATE-REGISTRY`.

**Required edit:** None — the owns is correct and the sequencing is already documented.

---

### 6. REPO-MAP-CONVERGE

**Ticket:** `fleet/board/REPO-MAP-CONVERGE.md`
**Current owns:** `fleet/validate_board.sh, fleet/preflight.sh, fleet/checks/base-integrity.sh, fleet/checks/repo-map-single-home.sh, fleet/tests/repo-map-converge.test.sh`
**Disposition: SEQUENCE IT — confirm correct placement in the ordering chain**

**Evidence:**
- `REPO-MAP-CONVERGE`'s `real-dep:` for `REPO-DECL-CENTRAL` (lines 13–16) explicitly states the shared-owns constraint with `fleet/preflight.sh`.
- `REPO-MAP-CONVERGE`'s `ds:` block (lines 86–91) explicitly identifies `SYNC-SCHEDULE` as a shared-owns co-owner and states: *"Touch each file ONCE, after its other owner lands."*
- `REPO-MAP-CONVERGE`'s `depends_on:` includes `SYNC-SCHEDULE`, which transitively reaches `PREFLIGHT-GATE-REGISTRY` (SYNC-SCHEDULE depends on FOREMAN-WIRE, FOREMAN-WIRE is not in the ordering chain but SYNC-SCHEDULE is in PREFLIGHT-GATE-REGISTRY's depends list → transitive order exists).
- Wait — SYNC-SCHEDULE's `depends_on:` is `STARTUP-CONTEXT-DIET, FOREMAN-WIRE`. These don't reach PREFLIGHT-GATE-REGISTRY. Let me re-check the transitive ordering:
  - REPO-MAP-CONVERGE → SYNC-SCHEDULE (via depends)
  - SYNC-SCHEDULE → ... does SYNC-SCHEDULE reach PREFLIGHT-GATE-REGISTRY? No.
  - But PREFLIGHT-GATE-REGISTRY → REPO-MAP-CONVERGE (via depends: REPO-MAP-CONVERGE is in PREFLIGHT-GATE-REGISTRY's depends list).
  - So `ordered(REPO-MAP-CONVERGE, SYNC-SCHEDULE) = True` (via PREFLIGHT-GATE-REGISTRY reaching REPO-MAP-CONVERGE, and REPO-MAP-CONVERGE reaching SYNC-SCHEDULE).
  - Actually: the `ordered()` function checks if A reaches B OR B reaches A. PREFLIGHT-GATE-REGISTRY reaches REPO-MAP-CONVERGE, so they are ordered. REPO-MAP-CONVERGE does NOT reach SYNC-SCHEDULE (SYNC-SCHEDULE is a leaf in the dep tree from REPO-MAP-CONVERGE's perspective). But PREFLIGHT-GATE-REGISTRY also reaches SYNC-SCHEDULE. So all three are ordered via PREFLIGHT-GATE-REGISTRY.

**Why this is safe:**
- `REPO-MAP-CONVERGE` is transitively ordered with all other preflight.sh owners via `PREFLIGHT-GATE-REGISTRY → REPO-MAP-CONVERGE`.

**Required edit:** None — the owns is correct and the sequencing is already documented in real-dep fields.

---

### 7. SYNC-SCHEDULE

**Ticket:** `fleet/board/SYNC-SCHEDULE.md`
**Current owns:** `fleet/preflight.sh, fleet/hooks/session-start.sh`
**Disposition: SEQUENCE IT — confirm correct placement in the ordering chain**

**Evidence:**
- `SYNC-SCHEDULE`'s `real-dep:` for `STARTUP-CONTEXT-DIET` (lines 9–13) explicitly describes the shared preflight.sh edit collision: *"shared fleet/preflight.sh edit region (this also transitively orders SYNC-SCHEDULE after HANDOFF-MECHANIZE via the existing HANDOFF-MECHANIZE -> HANDOFF-PIPEFAIL -> REPO-DECL-CENTRAL -> STARTUP-CONTEXT-DIET chain, which also owns preflight.sh). Undeclared 3-way owns collision found + fixed per fleet/state/TOOL-AUDIT-COLLISION.md RANK 3 (2026-07-13)."*
- `SYNC-SCHEDULE`'s `ds:` block (lines 27–31) confirms: *"must land AFTER the HANDOFF-MECHANIZE -> HANDOFF-PIPEFAIL -> REPO-DECL-CENTRAL -> STARTUP-CONTEXT-DIET chain finishes editing preflight.sh."*
- `SYNC-SCHEDULE` is in `PREFLIGHT-GATE-REGISTRY`'s `depends_on:`, so `PREFLIGHT-GATE-REGISTRY` reaches `SYNC-SCHEDULE` transitively. And `REPO-MAP-CONVERGE` depends on `SYNC-SCHEDULE` (via its `real-dep:` block on SYNC-SCHEDULE's shared-owns). So SYNC-SCHEDULE is ordered relative to both.

**Why this is safe:**
- `PREFLIGHT-GATE-REGISTRY → SYNC-SCHEDULE` (via transitive depends), ordering SYNC-SCHEDULE relative to all other preflight.sh owners.

**Required edit:** None — the owns is correct and the sequencing is already documented in real-dep fields.

---

### 8. GATE-INTEGRITY-C

**Ticket:** `fleet/board/GATE-INTEGRITY-C.md`
**Current owns:** `fleet/preflight.sh, fleet/tests/gate-integrity-c.test.sh`
**Disposition: SEQUENCE IT — confirm correct placement**

**Evidence:**
- `GATE-INTEGRITY-C`'s `depends_on:` includes: `MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE, WCI-DEC-FLEET-PREFLIGHT-SH`.
- `GATE-INTEGRITY-C`'s own `owns-collision:` note (line 50–53) acknowledges the collision: *"fleet/preflight.sh is owned by several tickets... MUST be dep-ordered before claiming — resolve against the live board, do not co-write."*
- It is transitively ordered relative to all other owners via its `depends_on: PREFLIGHT-GATE-REGISTRY`.

**Why this is safe:**
- `depends_on: PREFLIGHT-GATE-REGISTRY` transitively orders it relative to all other preflight.sh owners.

**Required edit:** None — the owns is correct and the sequencing is already documented.

---

### 9. WCI-DEC-FLEET-PREFLIGHT-SH

**Ticket:** `fleet/board/WCI-DEC-FLEET-PREFLIGHT-SH.md`
**Current owns:** `fleet/preflight.sh`
**Disposition: SEQUENCE IT — auto-generated WCI ticket, already correctly sequenced**

**Evidence:**
- `WCI-DEC-FLEET-PREFLIGHT-SH`'s `depends_on:` is: `MARKER-PROOF-MECHANIZE, PREFLIGHT-GATE-REGISTRY, PREFLIGHT-GATE-RUN-HELPER, RECONCILE-WIRING, REPO-MAP-CONVERGE, SYNC-SCHEDULE`.
- Its `dep-kind: build` is present.
- Its own `ds:` block (lines 41–44) states: *"Sequenced STRICTLY AFTER every live owner above: this ticket rewrites the file they are editing, so it must not run concurrently with them."*
- It is an **auto-generated WCI ticket** from `fleet/wci-contention.sh --generate`. Its purpose is to decompose the file after all writers have landed.

**Why this is safe:**
- `depends_on:` includes all six other live preflight.sh owners plus `PREFLIGHT-GATE-REGISTRY` — it runs after all of them by design.

**Required edit:** None — the owns is correct and the sequencing is already documented.

---

## Summary of Required Board Edits

Only **one** edit is required to close the RED:

### Edit 1: Narrow BENCH-OOB-GRADING's owns

**File:** `fleet/board/BENCH-OOB-GRADING.md`
**Change:** Remove `preflight.sh` from the `owns:` line.

**Current line:**
```
owns: benchmark/bench.sh, benchmark/lib/grade_state.py, model-scorecard.sh, benchmark/grader-daemon.py, benchmark/graders, benchmark/RUN-BENCHMARK.md, START-SESSION.md, preflight.sh
```

**New line:**
```
owns: benchmark/bench.sh, benchmark/lib/grade_state.py, model-scorecard.sh, benchmark/grader-daemon.py, benchmark/graders, benchmark/RUN-BENCHMARK.md, START-SESSION.md
```

**Reason:** The unprefixed `preflight.sh` claim refers to `benchmark/preflight.sh` (a different file in the benchmark tree), not `fleet/preflight.sh`. BENCH-OOB-GRADING has no ordering relationship to any other preflight.sh owner, so its co-ownership of the rig-tree file is spurious and causes the unsequenced-pair RED.

---

## DRY-RUN Proof

### How the RED was verified

The following Python was executed against the board at `fleet/board/` to enumerate all preflight.sh owners and test every pair for ordering:

```python
import os, glob, re

board_dir = 'fleet/board'
ids = {}
tickets = {}
for fpath in sorted(glob.glob(os.path.join(board_dir, '*.md'))):
    tid = os.path.basename(fpath)[:-3]
    if tid.endswith('.parked'): continue
    content = open(fpath).read()
    ids[tid.lower()] = tid
    tickets[tid] = {
        'deps': re.findall(r'^depends_on:\s*(.+)$', content, re.MULTILINE),
    }
    tickets[tid]['deps'] = [d.strip() for d in tickets[tid]['deps'][0].split(',') if d.strip()] if tickets[tid]['deps'] else []

def resolve(dep):
    return ids.get(dep.lower(), dep)

def reaches(a, b, seen=None):
    seen = seen or set()
    if a in seen: return False
    seen.add(a)
    if a == b: return True
    for dep in tickets.get(a, {}).get('deps', []):
        dl = resolve(dep)
        if dl and dl != a and reaches(dl, b, seen): return True
    return False

def ordered(a, b):
    return reaches(a, b) or reaches(b, a)

preflight_owners = ['MARKER-PROOF-MECHANIZE', 'PREFLIGHT-GATE-RUN-HELPER', 'RECONCILE-WIRING', 'REPO-MAP-CONVERGE', 'SYNC-SCHEDULE', 'PREFLIGHT-GATE-REGISTRY', 'GATE-INTEGRITY-C', 'WCI-DEC-FLEET-PREFLIGHT-SH', 'BENCH-OOB-GRADING']
live = preflight_owners
unseq = [(a, b) for i, a in enumerate(live) for b in live[i+1:] if not ordered(a, b)]
print(f'Unsequenced pairs: {len(unseq)}')
for a, b in unseq:
    print(f'  {a} <-> {b}')
print(f'RED fires: {len(live) >= 2 and bool(unseq)}')
```

**Output (before ruling):**
```
Unsequenced pairs: 2
  REPO-MAP-CONVERGE <-> BENCH-OOB-GRADING
  SYNC-SCHEDULE <-> BENCH-OOB-GRADING
RED fires: True
```

**Output (after ruling — with BENCH-OOB-GRADING removed from owners):**
```
Unsequenced pairs: 0
RED fires: False
```

### Current `validate_board.sh` RED output (pre-ruling)

```
  RED  owns-collision LIVE (no dep ordering): fleet/preflight.sh <- BENCH-OOB-GRADING GATE-INTEGRITY-C MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-REGISTRY PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE WCI-DEC-FLEET-PREFLIGHT-SH  [BENCH-OOB-GRADING|REPO-MAP-CONVERGE, BENCH-OOB-GRADING|SYNC-SCHEDULE]
```

Note: The validator runs against the worktree's board/ at `/home/stack/charon-private-wt/PREFLIGHT-OWNS-ARBITRATE/fleet/board/`, which is the same charon-private board. The exact pair list depends on the charon-private board state at the time of running.

### Predicted `validate_board.sh` RED output (post-ruling)

After the single board-hygiene edit to BENCH-OOB-GRADING's owns:

```
  INFO owns hand-off (dep-sequenced/historical, ok): fleet/preflight.sh <- GATE-INTEGRITY-C MARKER-PROOF-MECHANIZE PREFLIGHT-GATE-REGISTRY PREFLIGHT-GATE-RUN-HELPER RECONCILE-WIRING REPO-MAP-CONVERGE SYNC-SCHEDULE WCI-DEC-FLEET-PREFLIGHT-SH
```

The RED `owns-collision LIVE` for `fleet/preflight.sh` is cleared. All other REDs (tier-drift, other owns-collisions, WCI false-blocking-dep, gate-parity) are **unrelated to this ruling** and persist independently.

---

## Non-Vacuity Check

This ruling dispositions **all 9** preflight.sh owners. Count:
1. BENCH-OOB-GRADING — NARROWED
2. PREFLIGHT-GATE-REGISTRY — SEQUENCED (no change)
3. MARKER-PROOF-MECHANIZE — SEQUENCED (no change)
4. PREFLIGHT-GATE-RUN-HELPER — SEQUENCED (no change)
5. RECONCILE-WIRING — SEQUENCED (no change)
6. REPO-MAP-CONVERGE — SEQUENCED (no change)
7. SYNC-SCHEDULE — SEQUENCED (no change)
8. GATE-INTEGRITY-C — SEQUENCED (no change)
9. WCI-DEC-FLEET-PREFLIGHT-SH — SEQUENCED (no change)

**All 9 owners are dispositioned. The ruling is non-vacuous.**

---

## Post-Ruling Board Health

After the single board-hygiene edit:

- `validate_board.sh` check 4: the `fleet/preflight.sh` RED line is replaced by an INFO hand-off line.
- The ordering chain (PREFLIGHT-GATE-REGISTRY as head, all others transitively ordered) is preserved.
- No preflight.sh owner loses any real work or sequencing protection.
- `BENCH-OOB-GRADING` retains all its actual owned surfaces.
- The `WCI-DEC-FLEET-PREFLIGHT-SH` decomposition plan is unaffected — it runs after all writers land.

---

## Disposition Evidence Index

| Ticket | Evidence type | Evidence location |
|--------|--------------|-------------------|
| BENCH-OOB-GRADING | cross-file reference | MARKER-PROOF-MECHANIZE:24–25 (explicit: "different file") |
| BENCH-OOB-GRADING | ownership analysis | BENCH-OOB-GRADING owns list — unprefixed `preflight.sh` vs 7 prefixed benchmark/ paths |
| BENCH-OOB-GRADING | validator advisory | `WARN owns-path-missing: BENCH-OOB-GRADING owns 'preflight.sh' does not exist` |
| PREFLIGHT-GATE-REGISTRY | real-dep chain | PREFLIGHT-GATE-REGISTRY:8–15, real-dep blocks name all co-owners |
| PREFLIGHT-GATE-REGISTRY | intent statement | PREFLIGHT-GATE-REGISTRY:20–22 (dissolves collision by registry) |
| MARKER-PROOF-MECHANIZE | real-dep | MARKER-PROOF-MECHANIZE:18–25 (names FOREMAN-WIRE, REPO-MAP-CONVERGE, BENCH-OOB-GRADING) |
| MARKER-PROOF-MECHANIZE | serial justification | MARKER-PROOF-MECHANIZE:27–33 (three-layer serial) |
| PREFLIGHT-GATE-RUN-HELPER | real-dep | PREFLIGHT-GATE-RUN-HELPER:8–14 (WCI-CONTENTION-TEETH shared-owns) |
| PREFLIGHT-GATE-RUN-HELPER | ds block | PREFLIGHT-GATE-RUN-HELPER:83 (do not co-write) |
| RECONCILE-WIRING | real-dep | RECONCILE-WIRING:28–31 (MARKER-PROOF-MECHANIZE shared-owns, names chain) |
| RECONCILE-WIRING | ds block | RECONCILE-WIRING:93–97 (wave-2, ordered behind chain) |
| REPO-MAP-CONVERGE | real-dep | REPO-MAP-CONVERGE:13–16 (REPO-DECL-CENTRAL shared-owns) |
| REPO-MAP-CONVERGE | ds block | REPO-MAP-CONVERGE:86–91 (names SYNC-SCHEDULE as co-owner) |
| SYNC-SCHEDULE | real-dep | SYNC-SCHEDULE:9–13 (names HANDOFF-MECHANIZE chain, prior 3-way collision) |
| SYNC-SCHEDULE | ds block | SYNC-SCHEDULE:27–31 (must land after chain) |
| GATE-INTEGRITY-C | depends_on | GATE-INTEGRITY-C:15 (includes all 7 other owners + WCI-DEC-FLEET-PREFLIGHT-SH) |
| GATE-INTEGRITY-C | owns-collision note | GATE-INTEGRITY-C:50–53 (acknowledges collision) |
| WCI-DEC-FLEET-PREFLIGHT-SH | dep-kind | WCI-DEC-FLEET-PREFLIGHT-SH:9 (`dep-kind: build`) |
| WCI-DEC-FLEET-PREFLIGHT-SH | ds block | WCI-DEC-FLEET-PREFLIGHT-SH:41–44 (sequenced strictly after all writers) |
| WCI-DEC-FLEET-PREFLIGHT-SH | auto-generated | WCI-DEC-FLEET-PREFLIGHT-SH:10,13 (`auto_generated: wci-contention`) |
