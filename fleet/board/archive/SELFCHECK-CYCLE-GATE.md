repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/selfcheck-cycle-gate
depends_on:
owns: fleet/checks/selfcheck-cycle.sh, fleet/tests/selfcheck-cycle.test.sh
accept: |
  PROBLEM (this cycle reached ~18,900 procs — a REAL incident). A gate that runs tests which invoke the
  gate is a fork-bomb. HALF of this is ALREADY FIXED — verified 2026-07-16, do NOT redo it:
    - `fleet/gate.sh:29` -> `export CHARON_GATE_ACTIVE=1` (guard EXISTS, confirmed today)
    - `fleet/handoff.sh:312-317` -> skips its embedded gate when the flag is set
  What is MISSING is everything that keeps it fixed:
    (a) NO FAIL-ON-REVERT TEST. `ls fleet/tests/ | grep -iE 'reentr|forkbomb|gate_guard'` -> NOTHING.
        The only related file is handoff-mechanize.test.sh — which is the script that CAUSES the cycle
        (`:42` runs the real `$SRC/handoff.sh`). **Revert the gate.sh:29 export today and NOTHING goes
        red.** The guard is one careless edit from silently vanishing.
    (b) NO DETECTOR for the OTHER instances of the class. 12 files under fleet/tests/ shell out to real
        fleet scripts: deploy-session-end, leg-sandbox-isolation, reviewer-dogfood, test_land_safe_sync,
        dogfood-to-scorecard, budget-derive, done-gate, log-model-report, branch-reaper, foreman,
        capture-wiring, parked-claim-e2e. FOUR invoke handoff/gate/preflight/foreman/land DIRECTLY. Any
        one of these becoming a gate-run edge RE-ARMS the same bomb — the guard only covers the one
        edge that already exploded.
  WHY IT MATTERS: this exact cycle reached ~18,900 procs (load >2000, fork-starved boot) AND blew the
  GitHub GraphQL cap in the same incident. Memory directive [[fleet-selfcheck-forkbomb-class]] is
  explicit: "reentrancy-guard EVERY self-referential loop" — not just the one that bit us.

  DO:
    (a) fleet/checks/selfcheck-cycle.sh — build the script -> test -> script CALL GRAPH and FAIL on any
        cycle edge that lacks a reentrancy guard. Generalize the class; do NOT special-case the
        handoff.sh<->gate.sh pair. The 12 files above are your real-world corpus: the checker must
        classify each as guarded / not-a-cycle / UNGUARDED-CYCLE and be RIGHT about all 12.
    (b) Wire it so it actually runs (preflight/CI). [[gates-must-actually-run]]: a gate that is not on an
        execution path is decoration. State in the PR body WHERE it runs and paste the line proving it.
    (c) REENTRANCY-GUARD THE CHECKER ITSELF. selfcheck-cycle.sh analyses scripts that invoke gates; if it
        ever EXECUTES what it analyses it becomes the very bomb it detects. Static analysis only — do not
        run the scripts under test.

  FAIL-ON-REVERT (fleet/tests/selfcheck-cycle.test.sh — REQUIRED, all three):
    (1) THE CORE ASSERTION (the test that does not exist today): assert the handoff.sh -> gate.sh edge
        does not re-enter the suite. REVERT the `gate.sh:29` CHARON_GATE_ACTIVE export -> RED. Restore ->
        GREEN. This is the test whose absence is defect (a); without it this ticket has not shipped.
    (2) DETECTOR CATCHES A NEW CYCLE: feed the checker a FIXTURE pair (script A runs test B, test B runs
        script A) with NO guard -> RED. Add the guard -> GREEN. Revert the checker -> fixture stops
        failing -> test fails.
    (3) NO FALSE POSITIVE: a guarded fixture cycle and a plain acyclic script -> GREEN. A checker that
        reds the whole rig gets disabled within a day.
    SAFETY: test (1) must assert the guard's EFFECT statically or in a hard-bounded sandbox (proc cap /
    timeout). Do NOT prove reentrancy by actually letting it recurse — that is how the 18,900 procs
    happened. A test that fork-bombs CI is not a passing test.

  GREEN-IS-NOT-PROOF (explicit): the rig suite is green RIGHT NOW, and it would STAY green if you
  deleted the gate.sh:29 guard outright — that is precisely defect (a). Green here is not weak evidence,
  it is ZERO evidence: no test in the tree exercises the reentrancy edge at all. This session already
  shipped PRs at 19/19 and 40/40 green while the real path was broken because every test used fixtures;
  the same trap applies double here, since the ONE existing file that touches this area
  (handoff-mechanize.test.sh:42) passes BY TRIGGERING the dangerous edge rather than by guarding it.
  Reviewer: confirm test (1) genuinely goes RED with the export reverted, and that no test can recurse
  unbounded.
scope: |
  Generalize the fork-bomb reentrancy guard from a one-off into a mechanized class gate. The
  gate.sh:29 / handoff.sh:312 guard exists but has NO fail-on-revert test (revert it and nothing goes
  red) and NO detector for the other 12 fleet/tests/ files that shell out to real fleet scripts, 4 of
  which invoke handoff/gate/preflight/foreman/land directly. Build a static call-graph cycle checker
  that fails on any unguarded self-referential edge, wire it to run, and lock the existing guard with
  the test it never had. The cycle previously reached ~18,900 procs and blew the GitHub GraphQL cap.
  [[fleet-selfcheck-forkbomb-class]] [[gates-must-actually-run]] [[never-ignore-preexisting-issues]]
  [[slowness-triggers-investigation]]
ds: |
  ## Dependencies & sequence
  depends_on: (none) — owns TWO NEW files only (fleet/checks/selfcheck-cycle.sh,
    fleet/tests/selfcheck-cycle.test.sh). Nothing to collide with.
  not-covered-by (checked, genuinely disjoint): `grep -inE 'reentran|fork-bomb|forkbomb|self-referen|
    CHARON_GATE_ACTIVE' fleet/board/*.md` -> ONE hit, LAUNCHER-CRASH-PARTIAL-DETECT.md:16, and it is
    INCIDENTAL PROSE ("fork-bomb this session") about partial-work auto-commit. That ticket owns
    fleet/fleet-droid.sh + fleet/tests/test_launcher_crash_partial.sh — disjoint files, different
    defect. It does NOT cover the cycle guard. No coverage anywhere on the board.
  reads-only (analysed, NOT owned, NOT edited — this is what keeps the ticket zero-dep): fleet/gate.sh
    (:29 guard), fleet/handoff.sh (:312-317 skip), and the 12 fleet/tests/*.sh shell-out files. The
    checker ANALYSES these statically; it must not edit them. NOTE: fleet/handoff.sh is owned by
    STARTUP-CONTEXT-DIET + FOREMAN-MULTI-TRIGGER (both in review) and by GH-SEAM-CHOKEPOINT — do NOT
    edit it here or this ticket acquires three needless blockers. If the checker finds handoff.sh needs
    a code change, report it; do not make it.
  concurrency: RUNS NOW, zero-dep, parallel-safe with every live ticket including GH-SEAM-CHOKEPOINT
    (which edits handoff.sh; this ticket only reads it).
  wave: strong refill 2026-07-16. Frontier may claim down. Best-value strong item for an idle tab: it is
    the only zero-dep strong ticket in this batch.
  repo: charon-private (rig).
note: Created 2026-07-16 from fleet/session-notes/2026-07-16-evidence/audit-harvest.md item 3
  (GITHUB-RUNAWAY-POSTMORTEM rec#3 + [[fleet-selfcheck-forkbomb-class]]). Zero-dep, NEW files only —
  READY NOW, no blockers. Guard half already landed; the missing TEST + class detector are the work.
</content>
</invoke>
