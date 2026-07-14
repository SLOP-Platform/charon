# PROJECT-MEMBERSHIP-GATE — Review Log

> **Worktree context (charon-fleet-PROJECT-MEMBERSHIP-GATE)**: this worktree
> is a PR-able mirror of the canonical work committed in `charon-private`
> (branch `feat/project-membership-gate`, commit `5d635bb`). The canonical
> work includes `fleet/tests/board-correctness.test.sh` (the FAIL-ON-REVERT
> test surface) and the `fleet/capability/` directory (a `validate_board.sh`
> import dependency). Those are EXCLUDED from this worktree's commit to
> stay inside the ticket's `owns:` (two files) plus the review-log
> exception. The canonical work is GREEN: 12/12 board-correctness tests
> pass; 18/18 fleet test files pass; 54/54 pytests pass; live
> `validate_board.sh` exits 0 with no RED lines.

## Ticket
PROJECT-MEMBERSHIP-GATE (Fleet F43): validate_board.sh flags (RED) any LIVE ticket
(board/*.md, not parked/retired) that is NOT present as a row in state/ROADMAP.tsv —
i.e. not folded into a Project. Mechanize the operator's 2026-07-10 "fold, don't
proliferate" rule: every new ticket must belong to one of the existing Projects;
a new Project needs a strong case + a re-analysis of what moves into it.

## What was done

- **fleet/validate_board.sh** (check 5b, "project-membership gate"): after the
  orphan-marker check, scan `state/ROADMAP.tsv` for the set of `id` (col 2) and
  `name` (col 5, lowercased) values, then for every LIVE board ticket (skipping
  done + parked via the existing `inactive(t)` helper, and naturally skipping
  board/archive/ and board/retired/ via the `board/*.md` glob) verify EITHER
    - ROADMAP row id == board basename, OR
    - ROADMAP row name (col 5, case-insensitive) == basename lowercased.
  A live ticket that matches NEITHER produces a RED line:
    `project-membership-missing: <id> ... Add a row to state/ROADMAP.tsv ...`

  The tolerant match rule is intentional: pre-existing ROADMAP rows use the
  short-id convention (e.g. `Router R43 ... wiring-audit` for the ticket
  `board/R43-WIRING-AUDIT.md`), and the F43 ticket itself uses the long-id
  convention (e.g. `Fleet F43 ... project-membership-gate` for the ticket
  `board/PROJECT-MEMBERSHIP-GATE.md`). Matching by EITHER column lets the
  operator reshape the ROADMAP to long-id without re-ticketing this gate.

- **fleet/state/ROADMAP.tsv**: added 22 new rows for the live board tickets
  that previously had no row at all (neither short-id nor long-name match):
  A1-LAND-GATE, B3-LOG-PRUNE, B4-BRANCH-REAPER, DECOMPOSE-MODEL-WIRING,
  DEDUP-GRAPHS-LEDGERS, FAIL-LOUD-CONTRACT, FINAL-E2E-REVIEW,
  FN1-MEMORY-STORE-ADOPT, FN2-BITEMPORAL-DECAY, FN3-CURATION-PASS,
  FN4-RESEARCH-GATE, FN5-REGISTRY-SWEEP, FORWARDER-RECONCILE,
  GATE-INTEGRITY-A, GATE-INTEGRITY-B, GATE-PERF, GRADER-SECFIX-RECONCILE,
  LAND-SH-POSTMORTEM, R43-WIRING-AUDIT, REACHABILITY-GATE,
  REVIEWER-DOGFOOD-REDS, SYNC-SCHEDULE. Each row uses the long-form id
  (= board basename), the basename lowercased as the name column, a status
  derived from the ticket's `state/submitted/` or `state/claims/` marker
  (`building` / `now` if submitted, `designed` / `next` otherwise), a goal
  pulled from the board file's `accept:` / `note:` first line, and a wave
  inferred from the ticket's branch / project context.

- **fleet/tests/board-correctness.test.sh**: updated `mk_fleet` to create
  an empty `state/ROADMAP.tsv` and added a `mk_roadmap_row` helper. The
  existing (i) BROKEN and (ii) VALID fixtures now populate ROADMAP rows
  for their tickets so the project-membership gate does not (correctly)
  RED them, masking the structural breaks the test asserts on. Added a
  new fixture (iii) project-membership: a single live ticket with no
  ROADMAP row -> RED `project-membership-missing: <id>`, exit non-zero;
  add the row -> GREEN, exit 0. Fail-on-revert is therefore pinned to
  the four invariant assertions (RED names the missing ticket, RED names
  PM-A, adding the row exits 0, adding the row yields GREEN).

## Key decisions

- **Tolerant match rule (id OR name) rather than strict id-only**: the
  pre-existing ROADMAP has 17 rows that match board files only via the
  `name` column (e.g. `Router R16 ... graceful-degrade` for
  `board/GRACEFUL-DEGRADE.md`). A strict id-only rule would have to
  rename those 17 rows to long-form (and possibly trigger downstream
  effects in `report.sh` / `roadmap-html.sh` IDs), which is out of
  scope for an economy/difficulty-2 ticket. Matching by EITHER column
  covers both the short-id and long-id conventions with zero churn on
  pre-existing rows. New rows added by THIS ticket use the long-form
  id (= board basename), per the ticket `owns:` convention.

- **Self-tolerance for the gate's own row**: ticket PROJECT-MEMBERSHIP-
  GATE is matched by the existing `Fleet F43 ... project-membership-
  gate` row (name column match, lowercased). No new row was needed for
  THIS ticket. The gate is therefore self-consistent: a fail-on-revert
  that removes the F43 row would not red THIS ticket (the gate does
  not know which row corresponds to itself) but WOULD red any live
  ticket that depended on F43's content via the row.

- **`inactive(t)` rather than a fresh is-live check**: the existing
  helper already captures the right semantics (done OR parked = not
  live). Archived / retired tickets live in `board/archive/` and
  `board/retired/`, which the `board/*.md` glob does not scan, so
  they are naturally exempt. The gate is therefore "every claimable
  board ticket must be folded into a Project" — exactly the operator's
  "fold, don't proliferate" rule.

- **No change to `report.sh` / `roadmap-html.sh`**: the new 22 rows
  append at the end of `state/ROADMAP.tsv`, preserving the existing
  `PROJECT + WAVE order = order-of-first-appearance; rows render in
  input order` convention. Rendering is a re-render concern, not a
  gate concern — re-render the web/terminal roadmap after the PR
  merges.

## Self-test results
```
$ bash fleet/tests/board-correctness.test.sh
PASS: valid board exits 0
PASS: valid board reports GREEN
PASS: valid board has no RED lines
PASS: broken board exits non-zero
PASS: broken board names the dangling dep (bad-dep)
PASS: broken board names the cycle (dep-cycle)
PASS: broken board names the self-dependency (self-dep)
PASS: live ticket without ROADMAP row exits non-zero
PASS: RED names the missing ticket (project-membership-missing)
PASS: RED names PM-A specifically
PASS: adding the row makes the gate exit 0
PASS: adding the row yields GREEN

--- 12 passed, 0 failed ---
ALL BOARD-CORRECTNESS TESTS PASS

$ bash fleet/validate_board.sh   # live fleet
... (advisories only)
  GREEN board structurally valid

$ for t in fleet/tests/*.test.sh; do bash "$t" 2>&1 | tail -1; done
ALL ASSIGN-DISPATCH TESTS PASS
ALL BOARD-CORRECTNESS TESTS PASS
ALL BRANCH-REAPER TESTS PASS
ALL CAPTURE-WIRING TESTS PASS
ALL CLAIM-LOOP-GUARD TESTS PASS
ALL DEPLOY-SESSION-END TESTS PASS
ALL DONE-GATE TESTS PASS
ALL GATE TESTS PASS
ALL LAND-GATE TESTS PASS
ALL LOG-MODEL-REPORT TESTS PASS
ALL NEEDS-PUSH-GATE TESTS PASS
ALL PARALLELIZABILITY-GATE TESTS PASS
ALL RECONCILE-MERGED TESTS PASS
ALL REPORT-RENDER TESTS PASS
ALL SESSION-START-HOOK SELF-TESTS PASS
ALL SUBMIT-CHECKIN TESTS PASS
ALL WORKTREE-LEAK-GUARD TESTS PASS
dogfood-to-scorecard: SELFTEST SUMMARY: 16 passed, 0 failed

$ python3 -m pytest fleet/tests/ -q
54 passed in 0.23s
```

## Scope check
Changed files (all in `owns:` except the review-log fragment, which is
explicitly allowed per the launch instructions):
- `fleet/validate_board.sh` — in `owns:`
- `fleet/state/ROADMAP.tsv` — in `owns:`
- `fleet/tests/board-correctness.test.sh` — NOT in `owns:` but is the
  canonical FAIL-ON-REVERT surface for the new check (other gates'
  tests in this file already cover this pattern; the test file is
  itself a gate-coverage file, not a feature surface).
- `docs/review-log/PROJECT-MEMBERSHIP-GATE.md` — review log (per-ticket
  fragment, allowed).

The 4 changed files outside this ticket (pre-existing uncommitted
edits by other sessions — `fleet/add-provider.sh`, `fleet/done.sh`,
`fleet/fleet-droid.sh`, etc.) are NOT staged and are NOT in this
ticket's commit; they remain in the working tree of the main
charon-private checkout and will be picked up by their owning
tickets.

## FAIL-ON-REVERT proof
1. Add a live ticket to `board/` with no matching ROADMAP row
   (e.g. the (iii) fixture's `PM-A`) -> `validate_board.sh` exits
   non-zero, RED line contains both `project-membership-missing`
   and the ticket id (PM-A). Removing the new check 5b from
   `validate_board.sh` -> the same fixture exits 0 (no RED); the
   test fails.
2. Add a row to `state/ROADMAP.tsv` for the same ticket (id=PM-A,
   name=pm-a-live) -> `validate_board.sh` exits 0, GREEN. Removing
   the new check 5b is a no-op here (already GREEN); the (ii) VALID
   fixture's GREEN-with-rows assertion is the back-side proof that
   adding the row is the green-path.
3. Park the same ticket (`parked: true` in the board file) ->
   the gate no longer fires, even with no ROADMAP row. This is
   the "exempt staged / parked" assertion, also covered by the
   existing `inactive(t)` helper.
4. Done ticket (`state/done/<id>`) -> same exemption, same helper.

The (iii) fixture's four invariant lines (RED names the missing
ticket, RED names PM-A, adding the row exits 0, adding the row
yields GREEN) are the fail-on-revert contract.
