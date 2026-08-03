# RIG-CI-3R-PROOF — review/decision fragment

## What this ticket actually changed

`fleet/tests/rig-ci.test.sh` only. `(3r)` was restated, not deleted and not relaxed.
The semantic grandfathering in `_ticket_grandfathered` (TICKET-CHECK-SCOPE-SEMANTIC,
PR #367) was NOT weakened — it is correct and stays.

## Why the old (3r) was unfalsifiable (judgement)

A board file that is NOT in `base..head` diff is byte-identical to the base blob →
its `_ticket_fingerprint` is identical → it is grandfathered → it is SKIPPED by
`cmd_board`. "Off the diff" is therefore a strict subset of "grandfathered".
With the real script + a clean fixture, the unscoped (whole-board) scan and the
scoped (diff-only) scan reach the same verdict: every off-diff ticket is
narrated as grandfathered by the unscoped scan and skipped entirely by the
scoped scan, and both arrive at GREEN. Reverting `_scoped_board_files` to a
whole-board `ls` cannot, on any clean checkout, produce a RED. Diff-scoping is
still load-bearing — for SELECTION (asserted in 3r-a) and for the per-ticket
check cost — but the VERDICT now belongs to grandfathering.

This was demonstrated empirically: a REVERT-A run (whole-board `ls` substituted
into the REAL `fleet/checks/rig-ci-scope.sh`) yields `10 passed, 2 failed`
with (3r-a) failing exactly because the regex cannot neuter the real script
(it is already unscoped), and the other failure being the (5r) sibling whose
revert shape breaks when the same regex change cascades. That is the desired
fingerprint of "the assertion truly depended on the diff-scoping being real".

## Why 3r-b is strictly stronger than what it replaces

The failure mode that actually matters for test (3) is "cmd_board's green is
vacuous because per-ticket checks red NOTHING". The old (3r) compared two scan
widths and never touched that. 3r-b does: the SAME non-conforming,
done-but-unmarked ticket, made genuinely in scope (the `branch:` field is in
`_SUBSTRATE_RELEVANT_KEYS`, so grandfathering legitimately does NOT apply),
REDs under the REAL unmodified scope script with the exact substring
`OLD-DONE-TICKET: missing 'work_class:' field` and is NOT narrated as
grandfathered. A REVERT-B run (force `_ticket_grandfathered` to `return 0`)
yields `10 passed, 2 failed` with (3r-b) failing with the exact substring
`skip OLD-DONE-TICKET (grandfathered` — the loose-end loosening this work
refused to make.

## Layering after this change

- diff-scoping: SELECTION/COST (3r-a proves the set is strictly smaller).
- grandfathering: VERDICT (3r-b proves a genuinely in-scope ticket is
  actually checked, not waved through).
- These are independent. Either one alone is bypassable; together they close
  the failure mode the old (3r) never covered.

## Acceptance evidence (re-runnable)

- `bash fleet/tests/rig-ci.test.sh` → `12 passed, 0 failed`.
- REVERT A (neutered real script, restored byte-identical after):
  `10 passed, 2 failed`, message contains
  `(3r-a) could not build the reverted (unscoped) variant`.
- REVERT B (neutered real script, restored byte-identical after):
  `10 passed, 2 failed`, message contains
  `(3r-b) an in-scope done-but-unmarked ticket did NOT red … skip OLD-DONE-TICKET (grandfathered`.
- `bash -n fleet/tests/rig-ci.test.sh` → clean.
- `shellcheck -S error fleet/tests/rig-ci.test.sh` → clean.
- Scope self-check: `git diff --name-only master...HEAD` returns only
  `fleet/board/RIG-CI-3R-PROOF.md` (this ticket's own board entry — the rig
  requires every in-flight ticket to have one) and `fleet/tests/rig-ci.test.sh`
  (the `owns:` file). Nothing else.

## Hermeticity

3r-b fixture is another `mktemp -d` `git init` repo. It never reads the live
board, never touches `fleet/state/`, never hits the network, and never calls
`land*.sh` / `preflight.sh` / `gate.sh`. Re-entrant.
