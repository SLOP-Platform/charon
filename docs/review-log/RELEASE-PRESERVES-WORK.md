# REVIEW-LOG: RELEASE-PRESERVES-WORK

## Decision notes (2026-08-01, adversarial review of prior droid's commit 291ef85)

- **release.sh** was already rewritten by a prior droid before this session.
  The commit 291ef85 landed the full fix: `_release_block()` guard that checks
  worktree dirty state + unlanded commit count, fails safe on unresolvable paths,
  writes `needs-push` marker, retains claim, and prints the recovery command.
  I verified this by reading the final file — the implementation matches the spec.
- **release-preserves-work.test.sh** (188 lines, 5 cases a–e, 26 assertions) covers
  all five DONE CONTRACT cases. (a) and (b) use isolated fixture repos + worktrees;
  (c) tests both no-branch and branch-absent paths; (d) passes /nonexistent paths;
  (e) uses the real claim.sh + loop-guard.sh to prove the stranded ticket is NOT
  re-offered. All 26 assertions pass.
- **Ruff false-positive**: ruff is configured to lint `.sh` files in this repo but
  produces ~190 syntax errors on the bash scripts. This is a pre-existing repo issue
  (ruff does not parse bash). ShellCheck is the correct linter for shell and produces
  only info-level notes (SC1091/SC2015), no errors or warnings.
- **Scope**: my commit 291ef85 touches only `fleet/release.sh` and
  `fleet/tests/release-preserves-work.test.sh` — exactly the `owns:` line.
