repo: charon-private
tier: economy
priority: 0
difficulty: 1
work_class: bugfix
branch: fix/board-lock-staged-commit
depends_on: NO-LOCAL-MASTER-COMMITS
owns: fleet/board-lock.sh, fleet/worktree-commit-and-land.sh, fleet/tests/board-lock-staged-commit.test.sh
serial_justified: |
  One precondition and its red-proof, in one file. Splitting the guard from its test is how a
  guard ends up unproven.
substrate: N/A
substrate-novel: |
  No tool to adopt — this is a one-line precondition bug in a rig-local script that wraps git.
  The wrapper itself is the adopted-substrate decision already made (git's own `commit --only`
  does the isolation; board-lock adds the lock + base-pin). Nothing external models "commit only
  these paths under a base-pinned board lock".
source: |
  Operator, 2026-08-02 - "ticket and fix the board-lock.sh commit defects", after the manager was
  forced to use BOARD_LOCK_BYPASS twice in one session for routine deletions.
note: |
  ## THE DEFECT — one line, `fleet/board-lock.sh:395`
  ```
  git add -- "$@" || { _die "board-lock: 'git add' failed (nothing staged ...)"; return 6; }
  if [ -z "$(git diff --cached --name-only -- "$@")" ]; then _die "no staged change ..."; fi
  ```
  The SECOND check is the authoritative one and is CORRECT — it asks "is there staged content
  under this pathspec?", which is exactly the right question. The FIRST line hard-fails whenever
  `git add` exits non-zero, and `git add` legitimately exits non-zero for paths that are
  **already correctly staged**:
    1. a deletion staged by `git rm --cached` — the path no longer exists on disk, so
       `git add <path>` reports "did not match any files" and returns non-zero.
    2. a path staged by `git mv` (the source side) — same shape.
    3. a path that is gitignored but force-staged earlier — `git add` refuses it.
  In all three the content IS staged and the commit SHOULD proceed. The guard rejects it.

  ## WHY IT MATTERS MORE THAN A ONE-LINE BUG
  MEASURED 2026-08-02: this forced `BOARD_LOCK_BYPASS=1` TWICE in a single session, for commits
  that were pure deletions. **A safety tool that forces its own bypass on routine operations
  trains the operator to bypass it**, and a bypass habit is exactly what board-lock exists to
  prevent. The lock's whole value is that it is never routine to go around it.

  ## WHAT MUST NOT CHANGE — do not "simplify" the design
  `git commit --only -- <paths>` is CORRECT and load-bearing. It exists because a bare
  `git commit` takes the WHOLE index and has already swept another lane's staged `git mv` out of
  the shared main-checkout index (see this file's own header, defect (a)). Keep it. Keep the
  base-pin. Keep the staged-content precondition. Change ONLY the `git add` failure handling.

  ## A MISDIAGNOSIS TO RECORD, so it is not re-derived
  The manager also reported a third defect - "board-lock silently no-ops on
  `fleet/state/OPERATOR-ACTIONS.md`". **That was WRONG.** The `####` banner was `_loud` printing
  `BASE MOVED UNDER THE BOARD LOCK — REFUSING TO COMMIT`, which is CORRECT behaviour with a
  documented remedy (`release` then `acquire`). It read as a silent failure only because the
  output was truncated with `tail -1`. Do NOT "fix" the base-pin check
  [[confirm-dont-trust-documentation]]. If anything is wanted there it is ergonomics: make the
  base-moved refusal survive truncation by leading with a single-line summary before the banner.

  ## THE BIGGER DEFECT, FOUND WHILE FIXING THE FIRST — A REMEDY THAT DOES NOT EXIST
  MEASURED 2026-08-02. `board-lock.sh commit` ALSO refuses any commit made directly on local
  master, with sound reasoning it prints itself: a PR merge on GitHub wraps content in a MERGE
  commit while local master holds it BARE, so local master ends up simultaneously ahead AND
  behind origin — "divergence by construction". That analysis is CORRECT and explains why this
  session needed a `git rebase` after nearly every board commit.
  It then directs the caller to the ergonomic path:
      bash fleet/worktree-commit-and-land.sh --session <s> -m '<msg>' -- <paths>
  **THAT FILE DOES NOT EXIST.** `ls fleet/worktree-commit-and-land.sh` -> No such file.
  So the guard refuses the direct path and points at a remedy that is absent, leaving
  `BOARD_LOCK_BYPASS` as the ONLY way through. **The bypass habit is therefore STRUCTURAL, not
  carelessness** — the tool leaves no compliant path. This is the same class as a safety property
  asserted in prose that the code does not implement, and as the 9 inert checks: guidance with no
  mechanism behind it.
  REQUIRED: either BUILD `fleet/worktree-commit-and-land.sh` (scratch worktree -> commit -> land,
  keeping local master pure), or DELETE the recommendation and state the real supported path.
  A guard whose advice cannot be followed teaches operators to ignore guards.
accept: |
  a. `git add` non-zero no longer aborts the commit BY ITSELF. Capture its output; let the
     authoritative staged-content check decide. If add fails AND nothing is staged under the
     pathspec -> still REFUSE, and surface `git add`'s real stderr rather than a generic message.
  a2. EITHER `fleet/worktree-commit-and-land.sh` EXISTS and works, OR board-lock stops
     recommending it. Assert the recommended command is resolvable — a test that runs
     `command -v` / `[ -f ]` on every path board-lock suggests.
  b. RED-PROOF, hermetic (`mktemp -d`, offline), one case per shape, each SEEN to fail then pass:
       - stage a deletion with `git rm --cached`, then `board-lock.sh commit -- <path>` SUCCEEDS.
         Revert the fix -> RED.
       - stage a `git mv` source path, commit through board-lock SUCCEEDS. Revert -> RED.
       - ANTI-OVER-FIX: a pathspec with genuinely NOTHING staged still REFUSES and still exits
         non-zero. This is the case that keeps the guard a guard; a fix that makes this pass is a
         regression and the test must catch it.
       - the `--only` isolation still holds: with OTHER paths staged, the commit contains ONLY
         the named pathspec. This is the property the whole file exists for — assert it.
  c. The base-pin refusal is UNCHANGED and still fires (assert it, to prove the fix did not
     weaken it).
  d. Register the suite in the LITERAL `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh`,
     or it has never executed in CI [[gates-must-actually-run]].
  e. `bash fleet/validate_board.sh` GREEN.
scope: |
  The `git add` failure handling in `board-lock.sh commit`, plus its red-proof. Does NOT change
  the `--only` commit, the lock protocol, or the base-pin check.

## Dependencies & Sequence

- **depends_on: none.** Self-contained one-file fix.
- No owns-collision: verified against the live board 2026-08-02 — no live ticket owns
  `fleet/board-lock.sh`.
- Cheap and high-leverage: every board commit in the rig goes through this path, and the bypass
  habit it creates undermines a gate the whole fleet depends on.
