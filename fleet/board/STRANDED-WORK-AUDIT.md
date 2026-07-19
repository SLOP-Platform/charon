repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/stranded-work-detect
depends_on:
owns: fleet/checks/stranded-work.sh, fleet/tests/stranded-work.test.sh
accept: |
  RECURRING, TRIGGER-WIRED stranded-work DETECTOR. Report-only; it never deletes, pushes, or mutates a PR.

  HISTORY — the one-shot half is DONE, do not rebuild it. The full adversarial hand audit ran on 2026-07-14/15 and
  its ranked recovery table is `fleet/state/STRANDED-WORK-AUDIT.md`. The park condition on this ticket ("run only
  AFTER the in-flight EVAL + memory FN* sessions land") was SATISFIED 2026-07-16, so `parked: true` is removed.
  What remained — and what this ticket is — is the RECURRING half: [[dynamic-tools-never-on-demand]] says a
  dynamic-data tool must fire on a cadence + triggers. A hand-run audit is a snapshot, not a control; that is
  exactly why every session kept re-discovering the same backlog by hand.

  DETECT (each shape was real on this rig; each carries a fail-on-revert test):
  1. unpushed-branch    — local branch with commits reachable from NO remote ref.
  2. dirty-worktree     — worktree with uncommitted/untracked work and no live claim (state/claims|needs-push).
  3. pushed-no-pr       — remote branch, unmerged into base, with no PR of any state.
  4. closed-pr-unlanded — CLOSED (not merged) PR whose head branch still carries commits absent from base.
                          "Closed" != "abandoned": rig #81/#57/#56/#104 were all closed over real unlanded work.
  5. pr-no-checks       — OPEN PR with ZERO CI checks. checks=0 renders as mergeable, the same FALSE-RECEIPT
                          class as a proofless done-marker. Every rig PR predated the rig CI workflow.

  CONTRACTS:
  - NEVER-FALSE-GREEN: shapes 3-5 need PR state. gh missing/offline/rate-limited/non-github remote => report
    UNDETERMINED and exit 3. It must never print a clean receipt for something it could not determine.
  - FRESH-CHECKOUT SAFE: fleet/state/ is gitignored and ABSENT in CI — a missing claims dir means "no claims",
    never "flag everything", and a repo key with no checkout on the box is SKIPPED, not flagged.
  - CHEAP: local git only, plus ONE cached gh list per repo (TTL-bounded, stale cache still usable).
  - REENTRANCY [[fleet-selfcheck-forkbomb-class]]: never invokes preflight/validate_board/land*/branch-reaper;
    STRANDED_WORK_ACTIVE short-circuits any nested run.

  WIRED (the load-bearing requirement): `detect_stranded_work` in `fleet/preflight.sh` cmd_detect, riding the
  EXISTING detector dispatch — so it fires on every preflight (session start and every gate/land cycle), with no
  new scheduler invented. Advisory (`|| true`): report-only backlog must not block a session.
  `fleet/tests/stranded-work.test.sh` is added to the literal CI_SUITES allowlist in checks/rig-ci-scope.sh
  (new suites are excluded BY DEFAULT there), and the suite asserts BOTH wirings so silently unwiring it goes RED.

## Dependencies & Sequence

- Depends on: nothing. Reads fleet/repo-registry.sh (path SSOT) and fleet/state markers; writes only a gh cache file.
- Does NOT touch fleet/validate_board.sh (contended by four live tickets) or branch-reaper.sh / land-push.sh /
  leak-guard.sh (all changed 2026-07-19).
- Sequenced AFTER: the 2026-07-14 one-shot audit (done) and the EVAL-* / memory FN* landings (done 2026-07-16).
- Recovery of what it finds stays a human/`fleet/land.sh` decision, or the already-guarded fleet/branch-reaper.sh.
  This ticket deliberately ships NO --apply mode.
