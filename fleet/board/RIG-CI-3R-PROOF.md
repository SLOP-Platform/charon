repo: charon-private
tier: strong
priority: 0
difficulty: 2
work_class: ci-infra
branch: fix/rig-ci-3r-proof
owns: fleet/tests/rig-ci.test.sh
substrate: |
  N/A — no external tool can decide WHAT a red-proof in this rig is supposed to assert. The change
  is entirely inside this rig's own fail-on-revert suite: it restates one assertion about this
  rig's own `cmd_board` scoping policy. No dependency is added; the suite's only subprocess is git,
  as before.
substrate-novel: |
  The novel slice is the PROOF DESIGN: identifying that "off the diff" became a strict subset of
  "grandfathered" once semantic grandfathering landed, therefore that the old revert-the-scoping
  assertion is now unfalsifiable, and choosing the replacement claim that is still falsifiable
  (teeth on a genuinely-in-scope ticket) without loosening either layer. That is a judgement about
  this rig's gate semantics; no library models it.
substrate-retest: |
  Not needed — nothing adopted, no new dependency.
note: |
  BLOCKER, MEASURED 2026-08-01: `fleet/tests/rig-ci.test.sh` test (3r) failed on CLEAN master —
  1 failed / 10 passed, identical on master and on every branch — so it red every rig PR.

  ROOT CAUSE (not a regression in the gate). (3r) neutered the diff-scoping into a whole-board
  `ls fleet/board/*.md` scan and asserted the unscoped variant went RED on an off-diff,
  done-but-unmarked ticket. The SEMANTIC grandfathering that landed in `_ticket_grandfathered`
  (TICKET-CHECK-SCOPE-SEMANTIC, PR #367) now SKIPS that ticket, so the unscoped variant stays
  green. The test was CORRECT to fail: it was reporting that its own red-proof had gone VACUOUS.

  THE OLD CLAIM IS NOW A THEOREM-LEVEL IMPOSSIBILITY, not merely inconvenient:
      a board file NOT in the base..head diff is byte-identical to the base blob
      => its `_ticket_fingerprint` is identical => it is grandfathered => it is SKIPPED.
  "Off the diff" is a strict SUBSET of "grandfathered". On any clean checkout the whole-board scan
  therefore reaches the SAME VERDICT as the scoped scan, and reverting the diff-scoping alone can
  never produce a RED. Diff-scoping is still load-bearing for SELECTION/COST; grandfathering now
  carries the VERDICT.

  THE FIX IS A RESTATEMENT, NOT A RELAXATION. (3r) is not deleted, is not relaxed to match current
  behaviour, and the grandfathering is NOT weakened to resurrect the dead assertion — the
  grandfathering is correct and exists so a meaning-preserving reformat cannot re-open years of
  unrelated debt. (3r) now asserts, in two parts:
    (3r-a) SELECTION — the unscoped variant CONSIDERS the off-diff ticket (narrates it as
           grandfathered) while the scoped variant never sees it at all. The scoping is doing real
           work; it is simply no longer the only thing between (3) and a false RED.
    (3r-b) TEETH — the SAME old, non-conforming, done-but-unmarked ticket, made GENUINELY IN SCOPE
           (this PR edits `branch:`, a substrate-relevant key, so grandfathering legitimately does
           not apply), REDs under the REAL unmodified scope script with
           "OLD-DONE-TICKET: missing 'work_class:' field" and is NOT narrated as grandfathered.

  WHY (3r-b) IS STRICTLY STRONGER THAN WHAT IT REPLACES: the failure mode that actually matters for
  test (3) is "cmd_board's green is vacuous because the per-ticket checks red NOTHING". The old
  (3r) never covered that — it only compared two scan widths. (3r-b) closes it directly, and it
  doubles as the tripwire against the one loosening that would be tempting here: over-grandfathering.

  The complementary direction — a ticket whose FILE is touched but whose MEANING is not stays
  grandfathered and green — is already owned by `fleet/tests/ticket-check-scope.test.sh` (a)/(b)/(c)
  and is deliberately NOT duplicated here.
accept: |
  - `bash fleet/tests/rig-ci.test.sh` -> 12 passed, 0 failed (was 10 passed / 1 failed on master).
  - FAIL-ON-REVERT, both assertions independently proven to fire against a broken IMPLEMENTATION
    (the test file untouched in both runs):
      REVERT A — `_scoped_board_files` reverted to a whole-board `ls fleet/board/*.md` in the REAL
        `fleet/checks/rig-ci-scope.sh`: "FAIL: (3r-a) could not build the reverted (unscoped)
        variant — the real _scoped_board_files is already unscoped" (10 passed, 2 failed).
      REVERT B — `_ticket_grandfathered` forced to `return 0` (grandfather EVERY ticket), i.e. the
        exact loosening this work refused to make: "FAIL: (3r-b) an in-scope done-but-unmarked
        ticket did NOT red (rc=0) — test 3 proves nothing:  skip OLD-DONE-TICKET (grandfathered …)"
        (10 passed, 2 failed).
    `fleet/checks/rig-ci-scope.sh` restored byte-identical after each revert (empty `git diff`).
  - `bash -n` clean; `shellcheck -S error` clean.
  - HERMETIC / REENTRANT [[fleet-selfcheck-forkbomb-class]]: the new (3r-b) fixture is another
    `mktemp -d` `git init` repo. It never reads the live board, never touches `fleet/state/`, never
    hits the network, and never calls land*.sh / preflight.sh / gate.sh.

## Dependencies & Sequence

- **depends_on: (none) to build.** It is downstream IN MEANING of `TICKET-CHECK-SCOPE-SEMANTIC`
  (PR #367), which is already on master — that landing is what made the old (3r) vacuous.
- **Sequence: land FIRST, ahead of every other open rig PR.** (3r) is in `CI_SUITES`, so while it
  fails, `rig-ci` is RED on every branch regardless of that branch's content. Nothing else in the
  rig can land cleanly until this does.
- **owns-collision: NONE.** `fleet/tests/rig-ci.test.sh` is claimed by no other live ticket (only
  by two ARCHIVED ones). `fleet/checks/rig-ci-scope.sh` — which several live tickets do own — is
  NOT touched by this change; it was only modified transiently, in-worktree, to produce the
  fail-on-revert evidence above, and restored byte-identical.
