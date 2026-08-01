repo: charon-private
tier: economy
priority: 1
difficulty: 1
work_class: bugfix
branch: fix/validate-board-path-truncation
owns: fleet/validate_board.sh, fleet/tests/validate-board-path-truncation.test.sh
serial_justified: One off-by-one plus its regression test.
substrate: N/A
substrate-novel: |
  A one-character slice bug in our own parser of `git status --porcelain`. Nothing to adopt; the
  correct fix is to stop hand-slicing the porcelain format by index and parse it properly
  (`-z` + NUL split, or split on the first space after the 2-char status field).
depends_on: REPO-MAP-CONVERGE
note: |
  MEASURED 2026-08-01. `fleet/validate_board.sh:598-601` does:

      status = line[:2]
      path   = line[3:].strip()

  against `git status --porcelain` output, and EMITS A TRUNCATED PATH. Observed live:

      RED  uncommitted-work: dirty tracked file 'rc/charon/routing_policy/catalog_refresh.py'

  The real file is `src/charon/routing_policy/catalog_refresh.py` — the leading `s` is eaten.

  WHY THIS IS NOT COSMETIC: this is the rig's WORK-LOSS warning, and it is a GOOD detector — it
  found a killed droid's 222 uncommitted lines unprompted at session close on 2026-08-01, which a
  hand-written sweep had missed. A detector that fires correctly but prints a path nobody can
  `cd` to, grep for, or paste is a detector whose finding gets ignored. The one message that must be
  actionable is the one telling you work is about to be lost.

  Fix the parse, do not patch the index: porcelain paths can contain spaces and may be quoted or
  renamed (`R  old -> new`), so index-slicing is wrong in more ways than this one. Use `-z` with NUL
  separators.
accept: |
  - The reported path exactly equals the real path — assert byte-equality against a seeded dirty
    file, not a substring match.
  - Handles: unstaged (` M`), staged (`M `), both (`MM`), deleted (` D`/`D `), paths WITH SPACES,
    and renames (`R  old -> new`).
  - fail-on-revert test: restore the `line[3:]` slice -> test RED. Report both counts.
  - No behaviour change to WHICH files are flagged — this is a reporting fix only.

## Dependencies & Sequence

- **depends_on: (none).** One file, one function.
- **Sequence: quick win, do it early.** It is small, and it makes every future work-loss warning
  actionable — including the ones the KILL-PATH-WORK-GUARD sweep will emit.
- **owns-collision:** `fleet/validate_board.sh` is also owned by REPO-MAP-CONVERGE — sequenced behind it via depends_on; this change is confined to the uncommitted-work reporting block.
- **Provenance:** found while verifying a claim the manager had asserted from a single line of
  output without checking. It was nearly filed as a prose footnote inside another P0 ticket, where
  by the manager's own estimate it had roughly a 20% chance of ever being actioned. Operator caught
  that. Small real bugs need their own ticket, not a sentence inside someone else's.
