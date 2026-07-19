# SESSION-END-PUSH-GATE — Review Log

## Ticket
SESSION-END-PUSH-GATE: extend end-session.sh to REFUSE to print CLOSED unless
(a) the working tree is clean (ALL session work committed, not just the handoff)
AND (b) local HEAD is not ahead of origin/master — push via the sanctioned
land-push (autonomous-gated) or refuse LOUDLY with the exact command.

## What was done
- **fleet/end-session.sh** (Phase-2 close path, after the handoff commit succeeds):
  - **(a) Dirty-tree gate**: `git -C "$PRIV" status --porcelain` must be empty.
    A dirty entry = uncommitted session work that would strand. Refuses LOUDLY
    with the porcelain listing and a "fix and re-run" instruction. Done AFTER
    the handoff commit so a clean tree literally means "all session work is in
    git" (the handoff commit covers the handoff file; everything else must also
    be committed).
  - **(b) Ahead-of-origin gate**: if `origin/<branch>` ref is unknown, refuse
    with a `git fetch` instruction. If HEAD != origin/<branch>, push via the
    sanctioned `land-push.sh` (autonomous-gated). If `land-push` refuses (e.g.
    AUTONOMOUS=off), the script surfaces the operator's exact command instead
    of silently closing with work stranded.
  - New `END_SESSION_PUSH=0` knob: skip the auto-push and refuse loud (used by
    tests and for manual operator-controlled close).
  - The embedded `--selftest` git-stub was extended to fake the new
    status/rev-parse calls so the existing (A)-(E) tests still pass unchanged
    (no regression in the baseline; the baseline `B1`/`B4` failures predate
    this change — see "Pre-existing" below).

- **fleet/tests/end-session-push.test.sh** (new, dedicated FAIL-ON-REVERT rig):
  - Stands up a real `$D/rig` (local git repo on master) + a local bare
    `$D/origin.git` (origin remote). commit_handoff uses real `git`; only
    handoff.sh / handoff-check.sh / land-push.sh are stubbed.
  - **(A) dirty tree** → REFUSE, no CLOSED, handoff commit still happens but
    the leftover scratch-note is preserved in the rig (operator can fix).
  - **(B) unpushed commit + `END_SESSION_PUSH=0`** → REFUSE, no push, handoff
    file NOT on origin.
  - **(C) unpushed commit + fake `land-push.sh` refuses (rc=3)** → REFUSE,
    land-push was invoked with `master + rig`, handoff NOT on origin.
  - **(D) clean + already pushed** (real push via stubbed `land-push.sh`) →
    CLOSED, handoff IS on origin/master, working tree still clean.
  - **(E) FAIL-ON-REVERT**: explicit assertion that reverting the dirty check
    flips (A) to a CLOSED — the gate is what keeps (A) from closing.

## Key decisions
- **Dirty check AFTER the handoff commit, not before**: doing it before would
  always refuse (the handoff file is uncommitted at that point). Doing it after
  means "clean tree" = "everything is committed" — which is what we actually
  want to enforce.
- **Auto-push via `land-push.sh` (autonomous-gated), not just refuse**: the
  session-end script is the close ritual; asking the operator to push and
  re-run defeats mechanization. `land-push.sh` already self-gates on AUTONOMOUS
  and prints the operator command when off, so the script inherits that
  contract — refusing loud on AUTONOMOUS=off and pushing on AUTONOMOUS=on.
- **Bare `END_SESSION_PUSH=0` knob (not a no-autonomous toggle)**: needed by
  tests AND by operators who want to gate push at a different layer (e.g. CI).
  Does not bypass the refuse itself; it just skips the auto-attempt and
  surfaces the operator's exact command.
- **Sourced land-push.sh check (`-x`)**: a 4xx chmod/oops on land-push.sh
  should never close silently. Test/operator sees "FIX land-push.sh" and can
  recover.

## Self-test results
```
22 passed, 0 failed
ALL END-SESSION-PUSH TESTS PASS
```

## Pre-existing (NOT a regression from this ticket)
- `fleet/tests/deploy-session-end.test.sh` t5 fails (branch-guard refuses on
  the stubbed non-git `$d` dir). Pre-existing; the branch-guard was added in
  commit `b193381` AFTER the deploy test was written. Not in `owns:`, not
  addressed here.
- `end-session.sh --selftest` (B)/(D) fail (same branch-guard, same
  pre-existing break).
- `capture-wiring.test.sh` timeout failure (unrelated infra test).

These are the same failures `bash fleet/gate.sh` shows on `master` without my
changes; this ticket introduces zero new failures.

## FAIL-ON-REVERT proof
- Removing the dirty-tree check → A1, A2, A3, E1 all flip to FAIL (verified
  by `cp /tmp/end-session-test.sh` into the test rig). The test catches it.
- Removing the ahead-of-origin / push check → B1-B3, C1-C4, D3-D4 all flip
  to FAIL (verified by `cp /tmp/end-session-no-push.sh` into the test rig).
  The test catches it.

## Scope check
Changed/new files (all in `owns:`):
- `fleet/end-session.sh` (modified)
- `fleet/tests/end-session-push.test.sh` (new)
- `docs/review-log/SESSION-END-PUSH-GATE.md` (this fragment — allowed)
