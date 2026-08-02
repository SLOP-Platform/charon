# Review: 220@charon
**PR:** chore(AUTOLAND-DEFAULT-BRANCH-FIX): launcher auto-commit — droid exited without committing (review for completeness)
**URL:** https://github.com/SLOP-Platform/charon/pull/220
**Date:** 2026-08-02T15:08:18Z
**Reviewer:** reviewer-tab-2541120
**Author:** charon-bot

## Verdict
NEEDS-REVISION

## Findings
- Partial fix: sweep identified 5 files with hard-coded "master" branch references; only test_autoland.py is patched. The other 4 (test_land.py lines 224/229, test_work_land.py line 111) will still fail on hosts with init.defaultBranch=main, making the claimed "16 passed" verification misleading.
- No git version guard: git init -b requires git >=2.28; hosts on older git (e.g. CentOS 7 with git 1.8.x) will get silent failure or opaque errors with no fallback.
- Fixture shadowing parity gap: the local git_repo fixture shadows conftest.py's shared fixture but omits any teardown hooks, staging-area setup, or git config overrides (e.g. commit.gpgsign) that the shared fixture provides, silently degrading test isolation.
- Root cause deferred: the review-log explicitly acknowledges gitutil.init_repo() is the systemic problem but leaves it untouched. This is a deliberate technical-debt injection — production callers of init_repo() and other test files remain broken.
- "Ticket scope" as regression cover: the 4 other failing test files are left unfixed citing ownership boundaries, meaning the gate remains broken under main-default-branch hosts.

## Fail-on-revert check
Reverting would reveal that test_autoland.py still passes, but would drop the signal that test_land.py and test_work_land.py have the same root-cause bug — hiding 4 of 5 known defects.

## Status
Pending Manager dispensation
