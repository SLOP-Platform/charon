repo: charon-private
tier: strong
priority: 1
difficulty: 2
work_class: ci-infra
branch: fix/board-frontmatter-gate
owns: fleet/board-lock.sh, fleet/tests/board-lock-frontmatter.test.sh, fleet/tests/board-write-lock.test.sh
serial_justified: One guard on the board-write chokepoint plus its fail-on-revert suite, plus the sibling suite whose fixture the guard necessarily changes.
substrate: PyYAML
substrate-retest: |
  Not needed — PyYAML already carries an ADOPT verdict in EVAL-REGISTRY ("ADOPT — shipped, pinned
  PyYAML 6.0.3") scoped to exactly this job (parsing rig YAML), and this ticket adds no new use of
  it beyond calling the module that already parses board frontmatter.
depends_on: NO-LOCAL-MASTER-COMMITS
note: |
  MEASURED 2026-08-01: FIVE board tickets were committed with unparseable YAML frontmatter in a
  single session — LOOP-GUARD-REASON-WIRE, CAPTURE-WIRING-TIMEOUT-FIX, MODEL-HARDCODE-PURGE,
  REVIEWER-TAB-POOL, LAUNCHER-GATE-SETE-KILL. All the same shape: prose containing `: ` or a
  backtick written as a plain scalar instead of a block scalar.

  Each was caught only at PUSH time, 1-3 commits after it was written, costing a full push cycle
  to discover and fix. Detection existed; it was just at the wrong END of the loop.

  THE FIX: bind the parse check to `board-lock.sh commit`, which already gates EVERY sanctioned
  board write. Reuses the parser of record by CALLING it (`substrate_first_gate.read_frontmatter`),
  not by copying it — so split rule, parser, error text and fix wording are identical by
  construction and cannot drift.

  TWO CORRECTIONS THE BUILD TURNED UP (both contradict how this was originally briefed):

  1. `validate_board.sh` does NOT parse YAML. It reads fields with a line-prefix `field()`
     (:24), and `rig-ci-scope.sh` uses a sed `_field()` (:267). NEITHER can detect a parse error.
     The ONLY YAML parse in the rig is `checks/substrate_first_gate.py:104 parse_frontmatter()`,
     reached via `rig-ci-scope.sh:_check_ticket` -> `substrate-first-gate.sh check`. That is the
     gate of record, and what this binds to.

  2. **GATE DISAGREEMENT (verified, NOT fixed here).** `rig-ci-scope.sh:279` calls `_is_parked` —
     a sed read, which happily works on text that does not parse — and RETURNS BEFORE invoking the
     substrate gate. So a `parked: true` ticket with unparseable frontmatter is **GREEN in CI**,
     while `substrate-first-gate.sh check` on the same file exits 1 with a parse RED. The
     pre-filter and the parser of record disagree.
     board-lock sides with the parser and checks parked tickets too. The direction is safe
     (strictly stricter — nothing that passes here can fail there for parse reasons) and it stops a
     parked ticket carrying a latent RED until the day someone unparks it. Not fixed because
     `fleet/checks/*` was out of scope; wants a follow-up ticket.

  yamllint was CONSIDERED AND REJECTED on merit, not on "adds a dependency": it is a STYLE linter
  (indentation, line length, truthy, comment spacing) and the gate cares only about
  PARSEABILITY. It would fire on legal tickets and catch nothing new, while adding a second
  verdict source. (Separately worth knowing: yamllint is installed at ~/.local/bin/yamllint and is
  wired into NOTHING — 2 prose mentions across both repos, no EVAL-REGISTRY row. Same for
  actionlint, which has a config at .github/actionlint.yaml that no workflow invokes.)
accept: |
  - `board-lock.sh commit` REFUSES (non-zero, loud) when any staged `fleet/board/*.md` has
    unparseable frontmatter, naming the file, the line, the parse error, and the fix
    ("quote the value or make it a block scalar (`key: |`)") in wording identical to the
    downstream gate.
  - Checks ONLY the board files in THIS commit — a pre-existing broken ticket elsewhere must never
    block an unrelated board write.
  - Path scope is `rig-ci-scope.sh`'s `_scoped_board_files` regex verbatim: `^fleet/board/[^/]+\.md$`
    (top level only; `board/archive/` excluded, matching downstream).
  - Reuses `substrate_first_gate.read_frontmatter` by CALL, never by copy.
  - Bypassable via the file's existing audited `BOARD_LOCK_BYPASS` escape — a genuinely broken
    pre-existing ticket must not permanently wedge the board.
  - Fail-closed on missing python3 / PyYAML / rule module (refuse, exit 7, name the escape).
  - New exit code 7 = unparseable frontmatter, documented in the header.
verified: |
  Delivered 2026-08-01 by a sub-session:
    * 61 assertions, 61 pass / 0 fail.
    * Red-proof, 4 INDEPENDENT reverts: drop the wire line -> 20 FAIL; drop the bypass branch ->
      15 FAIL; widen the path regex -> 4 FAIL; hand-roll the parse instead of reusing the module ->
      9 FAIL (including the agreement assertions, which is the point).
    * shellcheck -S error clean on all three files.
    * Fixture honesty note: the first `D&S` fixture PARSED CLEANLY — a one-line `- k: v` is a legal
      nested mapping. The real defect is the multi-line WRAP, so the fixture was rebuilt from the
      actual pre-fix ticket at `13c538a^`.
    * Self-caused regression found and fixed: `board-write-lock.test.sh` went PASS -> FAIL (10)
      because its hermetic fleet had no `fleet/checks/` and its SEED.md body was the bare string
      `seed`. Fixture repaired (same precedent as `board-correctness.test.sh`); back to PASS.

## Dependencies & Sequence

- **depends_on: (none).** One guard plus tests.
- **Sequence: now.** Every board write until it lands can mint another latent parse RED — five did
  today.
- **Blocks / unblocks:** removes a recurring push-cycle tax on ALL board work.
- **owns-collision:** `fleet/board-lock.sh` and `fleet/tests/board-write-lock.test.sh` are also
  owned by NO-LOCAL-MASTER-COMMITS. Sequenced behind it (`depends_on`) so the file stays
  single-writer; this change is confined to the `commit` path's staged-file check, which that
  ticket does not touch.
- **Deliberate deviations, flagged rather than hidden:**
  (a) `set -uo pipefail` kept (NOT `-e`): `board-lock.sh` returns documented exit codes and `-e`
      would break that contract. Follows each file's own convention over the brief's boilerplate.
  (b) The check runs on the `commit` path only, not the `pre-commit` arm — every sanctioned board
      write goes through `commit`, and a `BOARD_LOCK_BYPASS` commit intentionally skips both.
  (c) The new suite is auto-collected by `fleet/gate.sh`'s glob so it runs locally, but is NOT in
      `CI_SUITES` — registering it means editing `fleet/checks/rig-ci-scope.sh`, owned elsewhere.
      `board-write-lock.test.sh` has the same gap. Follow-up.
- **Follow-up ticket wanted:** the parked-ticket pre-filter disagreement at `rig-ci-scope.sh:279`.
