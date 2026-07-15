repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/eval-grader-provision
depends_on:
serial_justified: provisioning the bench-grader runtime + fixing the snapshot perms + the MUST-PASS/MUST-FAIL controls are one environment fix; the controls can't be proven until the runtime runs.
owns: fleet/benchmark/graders/preflight.py, fleet/benchmark/selftest/test_grader_env.sh, fleet/state/GRADER-PROVISION-NOTE.md
accept: |
  BLOCKER (review F2): the MODEL-PREFLIGHT synthetic battery has NEVER validly discriminated — the OOB controls
  fail-closed on grader INFRA (grader PermissionError on the snapshot + the `bench-grader` user has no pytest, per
  CONTROLS-STATUS.md / deepseek-flash.log), so EVERY model gets 'detained' for infra reasons, not quality. No Chunk-D
  per-task discrimination proof exists. The whole synthetic battery is dead weight until this runs.
  DO:
  - Provision the bench-grader runtime so it can actually grade: install pytest (+ deps) available to the bench-grader
    user; fix the worktree/snapshot PERMISSIONS + excludes so graders/preflight.py can read what it needs without a
    PermissionError. This is partly an OPERATOR action (bench-grader is a dedicated unix user, needs sudo) — document
    the exact commands in GRADER-PROVISION-NOTE.md as an operator step; the droid does everything runnable as its own
    user + the self-test.
  - Prove it: a fleet/benchmark/selftest/test_grader_env.sh that runs a KNOWN-GOOD fixture through graders/preflight.py
    and asserts it grades PASS (not infra-detain), and a KNOWN-BAD fixture grades FAIL. This is the missing control panel.
  FAIL-ON-REVERT: the self-test's MUST-PASS control PASSES and MUST-FAIL control FAILS through the real OOB grader path
  (revert the perm/pytest fix → both collapse to infra-detain → self-test fails). Ties into EVAL-PROMOTION-GATE (which
  consumes this control-panel split as the discrimination proof). [operator-action: bench-grader sudo provisioning]
