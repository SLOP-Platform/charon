# SELFCHECK-CYCLE-GATE — Review Log

## Ticket
SELFCHECK-CYCLE-GATE: mechanize the [[fleet-selfcheck-forkbomb-class]] gate
(generalize the handoff.sh <-> gate.sh reentrancy guard into a static cycle
detector that fails on any unguarded self-referential edge) and lock the
existing guard with the fail-on-revert test it never had.

## Root cause being fixed

The 2026-07-15 fork-bomb incident (`handoff.sh` -> `gate.sh` -> test suite ->
`handoff-mechanize.test.sh` -> `handoff.sh` ...) reached ~18,900 procs, load
>2000, and in the same incident blew the GitHub GraphQL cap. Half of the fix
landed (gate.sh:29 exports `CHARON_GATE_ACTIVE`, handoff.sh checks it and
skips) — but the other half was MISSING:

- **No fail-on-revert test for the existing guard.** Revert `gate.sh:29` ->
  nothing goes red. The guard is one careless edit from silently vanishing,
  and the rig stays "all green" while the actual fork-bomb path is back.
- **No detector for the OTHER instances of the class.** `fleet/tests/` has
  ~12 files that shell out to real fleet scripts; FOUR of those invoke
  handoff/gate/preflight/foreman/land directly. Any one of those becoming
  a gate-run edge RE-ARMS the same bomb — the guard only covers the one
  edge that already exploded.

The defect: green-rig != guard-present. A checker that "always passes" is
invisible; a checker that "always fails" gets disabled within a day. What
this ticket ships is a class-level gate that catches BOTH directions of
drift.

## What was built

Two new files (ownership = `owns:` line of the ticket; no other files
touched):

1. **`fleet/checks/selfcheck-cycle.sh`** — static analyzer.
   - Builds a script -> script call graph from every `fleet/*.sh` and
     `fleet/tests/*.test.sh` file, scanning the first 400 lines for
     `bash` invocations targeting the real fleet root.
   - Classifies each path as a "real edge" iff the leading path component
     is a known fleet-root variable (`$SRC`, `$FLEET`, `$HERE`, ...).
     Fixture copies rooted at temp-dir variables (`$D`, `$WORK`, `$F`, ...)
     are NOT real edges — running a copy of `gate.sh` under `/tmp` cannot
     recurse into the real test suite.
   - Injects a synthetic "test-runner" edge: any script that does
     `for test_file in *.test.sh; do bash ...` is treated as a parent of
     every test (since the static call-site doesn't name individual tests).
     This is what makes the `gate.sh` <-> `handoff-mechanize.test.sh`
     cycle visible to the analyzer.
   - Runs bounded DFS (depth <= 8) over the graph to enumerate every
     simple cycle, dedups by sorted node-set.
   - **Dataflow guard model**: a cycle is GUARDED iff some node on the
     cycle path CHECKS a reentrancy flag (`${F:-}`) AND some node on the
     cycle path (same or different) SETS that flag (`export F=...` or
     inline `F=val bash ...`). The check + set halves must BOTH be
     present — that's the dataflow that makes the cycle safe at runtime.
     This catches the case where the existing `gate.sh:29` export is
     silently removed: the `handoff` node still has its check, but no
     node on the cycle sets the flag, so the cycle flips to UNGUARDED.
   - Recognized reentrancy-flag name suffixes: `_ACTIVE`, `_RUNNING`,
     `_LOCK`, `_BUSY`, `_REENTER`, `_NESTED`, `_RECURSE`, `_GUARD`.
     Plus `FLEET_TESTS_DIR` (the hermetic-test override convention used
     by `gate.test.sh` to redirect `gate.sh`'s test discovery — a real
     runtime cycle-breaker that would otherwise be a false positive).
   - Pure static analysis — does NOT execute any analyzed script. A
     checker that runs the scripts it inspects is the same fork-bomb
     trap at the meta level.

2. **`fleet/tests/selfcheck-cycle.test.sh`** — three required
   fail-on-revert tests, plus a canary.
   - **(1) CORE ASSERTION**: `gate.sh:29` exports `CHARON_GATE_ACTIVE=1`
     AND `handoff.sh` checks `${CHARON_GATE_ACTIVE:-}` AND the live
     cycle-checker reports GREEN with the handoff<->gate cycle in the
     "guarded" list. Revert ANY of the three -> RED.
   - **(2) DETECTOR CATCHES A NEW CYCLE**: builds a temp fleet fixture
     with `cycle-a.sh` <-> `cycle-b.test.sh` and proves: (a) unguarded
     pair -> RED with both cycle names reported, (b) add
     `export FIXTURE_GUARD_ACTIVE=1` + `${FIXTURE_GUARD_ACTIVE:-}` check
     -> GREEN, (c) remove the guard again -> RED. (c) is the proof that
     the guard was what made it GREEN — not some other accidental
     signal.
   - **(3) NO FALSE POSITIVE**: guarded fixture cycle, plain acyclic
     fixture (one-way call), and a single-file fleet all return GREEN.
   - Safety: `ulimit -u 256` at the top so a buggy future checker that
     DOES recurse is killed before it can fork-bomb the host. The test
     does not depend on this — it asserts statically — but the cap is
     a second line of defense.

## Verification (live fleet, current master)

```
$ bash fleet/checks/selfcheck-cycle.sh
selfcheck-cycle: fleet root = /home/stack/charon-private-wt/SELFCHECK-CYCLE-GATE/fleet
selfcheck-cycle: nodes = 134, edges = 131, guarded scripts = 3
selfcheck-cycle: guarded cycles = 5, UNGUARDED cycles = 0

selfcheck-cycle: GREEN — no unguarded self-referential edges.
  guarded cycles (safe by guard, but worth knowing about):
    - gate -> gate.test -> gate
    - handoff -> gate -> handoff-mechanize.test -> handoff
    - handoff-mechanize.test -> handoff -> gate -> handoff-mechanize.test
    - gate -> handoff-mechanize.test -> handoff -> gate
    - gate.test -> gate -> gate.test
```

The 5 guarded cycles are EXACTLY the ones that exist on the real fleet
(2 from `gate.sh` <-> `gate.test.sh` via `FLEET_TESTS_DIR`; 3 from
`gate.sh` <-> `handoff.sh` via `CHARON_GATE_ACTIVE`). All 12 files
listed in the ticket as "shell out to real fleet scripts" are correctly
classified as `not-in-any-cycle` (they use fixture copies).

## Fail-on-revert confirmation

| Mutation                                  | checker rc | selfcheck-cycle.test.sh rc |
|-------------------------------------------|-----------:|---------------------------:|
| (none — baseline)                         | 0          | 0 (11 pass)                |
| Revert `gate.sh:29` (export gone)         | 1          | 1 (1a/1b/1c fail)          |
| Revert `handoff.sh` (check gone)          | 1          | 1 (1a/1b/1c fail)          |
| Revert BOTH (the full guard)              | 1          | 1 (1a/1b/1c fail)          |

In all revert cases the test rig goes RED on the SAME 3 assertions
(1a, 1b, 1c). 1d ("checker reports the handoff<->gate cycle") still
passes — the analyzer still SEES the cycle, it just classifies it
correctly as unguarded.

## Wire-it-into-the-rig proof

The new test file `fleet/tests/selfcheck-cycle.test.sh` is picked up
automatically by `gate.sh`. Proof:

```
$ grep -n '\*.test\.sh' fleet/gate.sh
33:  tests=("$TESTS_DIR"/*.test.sh)
```

gate.sh:33 globs every `*.test.sh` in `fleet/tests/` and runs them
concurrently. The new test runs on every gate invocation, exactly like
the rest of the rig suite. No additional wiring required (and per
the ticket, I cannot edit preflight.sh — that file is not in my owns).
This satisfies `[[gates-must-actually-run]]`: a gate that is not on
an execution path is decoration, and this one is on the path.

## False-positive audit (the 12 files)

| File                                | Real fleet root?  | Result   |
|-------------------------------------|-------------------|----------|
| `deploy-session-end.test.sh`        | copy to `$d/`     | not-cycle |
| `leg-sandbox-isolation.test.sh`     | copy to `$D/`     | not-cycle |
| `reviewer-dogfood.test.sh`          | copy to fixture   | not-cycle |
| `test_land_safe_sync.sh`            | copy to fixture   | not-cycle |
| `dogfood-to-scorecard.test.sh`      | copy to fixture   | not-cycle |
| `budget-derive.test.sh`             | copy to fixture   | not-cycle |
| `done-gate.test.sh`                 | copy to fixture   | not-cycle |
| `log-model-report.test.sh`          | copy to fixture   | not-cycle |
| `branch-reaper.test.sh`             | copy to fixture   | not-cycle |
| `foreman.test.sh`                   | copy to fixture   | not-cycle |
| `capture-wiring.test.sh`            | copy to fixture   | not-cycle |
| `parked-claim-e2e.test.sh`          | copy to fixture   | not-cycle |

All 12 are correctly classified as "not a cycle" — they hermetically
copy the script under test to a temp dir and run the copy. Re-entering
a copy of `gate.sh` under `/tmp` cannot recurse into the real test
suite, so these edges are safe by construction.

## Risk / open questions

- **Heuristic guard detection.** The checker uses regex pattern-matching
  to find `${F:-}` and `export F=` patterns. A guard that uses a more
  exotic form (e.g., a function that reads the env var indirectly) would
  be missed. The class of cycle-detected failures is bounded by
  `[[:alnum:]_]` flag names and the documented suffixes — a real
  reentrancy guard in this rig would have to deliberately hide from
  grep to evade detection. The test fixtures intentionally exercise
  the false-positive case so future drift goes RED instead of silently
  misclassifying.
- **FLEET_TESTS_DIR as a "config guard".** Recognized as a guard because
  it is the convention `gate.test.sh` uses to break the
  `gate.sh` <-> `gate.test.sh` cycle at runtime. If a future test
  needs a different env-var override to be recognized as a guard, the
  GUARD_SETTER_EXTRACTOR is the place to add it.
- **Curate.test.sh is flaky in `gate.sh`** (this is pre-existing,
  unrelated to this change — the same flake appears on master without
  my files). The new test does not interact with curate.

## Notes for reviewer

- The diagnostic block in the checker is gated by `SELFCHECK_DIAG=1`
  and is OFF by default. It's there so future drift in the
  classification heuristic is debuggable. To exercise: `SELFCHECK_DIAG=1
  bash fleet/checks/selfcheck-cycle.sh`.
- The `ulimit -u 256` in the test is a defense-in-depth, not a load-
  bearing assertion. The test asserts the guard's effect statically;
  the ulimit is a fallback if a future change accidentally lets the
  test recurse.
- The test (1) line numbers (gate.sh:29, handoff.sh:292) are
  approximate — they're "near these lines". The test asserts the
  PATTERNS (`export CHARON_GATE_ACTIVE=` and `${CHARON_GATE_ACTIVE:-}`)
  not exact line numbers, so future reformatting doesn't break it.
