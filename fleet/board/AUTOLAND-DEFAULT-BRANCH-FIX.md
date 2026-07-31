repo: charon
tier: economy
difficulty: 1
work_class: tests
priority: 0
branch: fix/autoland-default-branch
depends_on:
owns: tests/test_autoland.py
serial_justified: |
  ONE fixture defect with one cause. All 8 failures share the same root.
execution: |
  Off-Claude via fleet-droid.sh, own worktree. PRODUCT repo (/home/stack/code/charon).
source: |
  Found 2026-07-31 (session tott-doneeta) landing GATE 2's ADR-0021. The product gate came back
  RED with 8 test_autoland.py failures. Verified PRE-EXISTING on product master f87d4ae — the
  branch being landed was clean. This RED blocks EVERY product land.
note: |
  ## FACTS (verified 2026-07-31)
  - `PYTHONPATH=src python3 -m pytest tests/test_autoland.py -q` on product master `f87d4ae`:
    **8 failed, 8 passed**. Not caused by any in-flight branch.
  - Root cause, from the failure itself:
    `subprocess.CalledProcessError: Command '['git','-C','/tmp/pytest-of-stack/pytest-13/
    test_gitleaks_leak_holds0/repo','rev-parse','master']' returned non-zero exit status 128`
  - **`git config init.defaultBranch` = `main`** on this host (git 2.43.0). The fixtures create a
    throwaway repo and then address `master`, which does not exist in it.
  - So the suite silently depends on a GLOBAL, PER-HOST git setting. On a host configured for
    `master` it passes; here it cannot. That is the failure, not anything about autoland's logic.

  ## WHY IT MATTERS BEYOND THESE 8 TESTS
  `charon.cli gate` is the product's merge gate. While these fail, `land.sh`/`land-push.sh` REFUSE
  every product land — ADR-0021 (docs+test, zero runtime risk) is already stuck behind it. A red
  that blocks all landing is P0 regardless of how small the fix is.

  ## SCOPE
  Make the fixtures independent of the host's `init.defaultBranch`. Preferred: create fixture repos
  with an EXPLICIT initial branch (`git init -b master`, or `git init` + `git symbolic-ref`), or
  derive the branch name instead of hard-coding it. Do NOT "fix" this by changing the developer's
  global git config — a test that only passes under a particular global setting is the defect.
  Check the WHOLE file for the same assumption, not just the 8 that happen to fail.

  ## CLASS (fix the class, not the instance)
  Environment-coupled test: passes or fails on a global host setting nothing declares. Sweep
  `tests/` for other fixtures that hard-code `master` or otherwise assume host git config, and
  report them even if currently green — they are the same latent bug.

  ## DONE CONTRACT — RED then GREEN, breaks EXTERNALLY SPECIFIED
    a. With `init.defaultBranch=main` set, the full `tests/test_autoland.py` suite is GREEN.
    b. With `init.defaultBranch=master` set, it is STILL GREEN (the fix must not just invert the
       assumption — prove BOTH, this is the whole point).
    c. `PYTHONPATH=src python3 -m charon.cli gate` reaches GREEN on this red, or any remaining
       failure is a DIFFERENT named cause, reported.
  Report the before/after counts verbatim.

D&S — Deps & Sequence:
  - Depends on: nothing. Do it FIRST — it unblocks every product land including GATE 2's ADR-0021.
