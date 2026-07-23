repo: charon-private
tier: strong
difficulty: 3
work_class: bugfix
branch: fix/grader-real-shell-injection
substrate: N/A
substrate-novel: |
  Removing a live shell=True command-injection surface in existing stdlib subprocess code
  (fleet/benchmark/graders/real.py). No external library adopts "run a data-derived check command
  safely" — correct argv usage with shell=False (or shlex.quote of the untrusted substitution) plus
  realpath confinement of the {worktree} path IS the fix, not a dependency. bandit (being adopted
  separately as a rig CI SAST) is the DETECTOR of this class, never the remediation; adopting a tool
  here would be a category error. [[adopt-substrate-build-only-novel-slice]]
depends_on:
owns: fleet/benchmark/graders/real.py, fleet/benchmark/selftest/test_real_shell_injection.py
serial_justified: |
  The one-file fix and its fail-on-revert canary ship together: the test asserts a crafted malicious
  check_cmd / snapshot path can no longer inject (shell metacharacters treated as literal argv or safely
  quoted, not interpreted by a shell) and goes RED if the shell=False / quoting guard is reverted.
  Splitting ships an unproven security fix — the exact zero-work-green defect the ratchet forbids.
work_class_note: |
  security-ratchet — a live shell=True on a data-derived command (check_cmd from $KEYS/reds-replay.tsv
  with the untrusted {worktree} snapshot path substituted in). RANK-0 / Priority-1.
ds: |
  ## Dependencies & sequence
  - depends_on: (none — hard). DISJOINT owns from GRADER-SECFIX-RECONCILE: that ticket owns
    grader-daemon.py / graders/reds_replay.py / selftest/test_grader_daemon.py; this owns
    graders/real.py + a NEW selftest. No file overlap, so no build-order dependency.
  - soft sequence (preference, not a block): land AFTER GRADER-SECFIX-RECONCILE so this fix can REUSE
    the _confine()/SandboxError + argv/shell=False pattern that ticket establishes (F1/F2) instead of
    re-deriving it. If it lands first, replicate the pattern inline.
  - concurrency: single-writer on fleet/benchmark/graders/ — do NOT build concurrently with
    GRADER-SECFIX-RECONCILE (adjacent files; that ticket declares a conservative single-writer on
    fleet/benchmark/).
accept: |
  fleet/benchmark/graders/real.py no longer runs a data-derived command through a shell in a way that
  lets the untrusted {worktree} snapshot path (or a hostile check_cmd) inject. The builder MUST first
  inspect the real check_cmd values in $KEYS/reds-replay.tsv to determine whether any legitimately need
  shell features:
    - if not: execute as an argv list (shlex.split) with shell=False;
    - if shell features are genuinely required: keep the trusted template but neutralize the injection
      vector (shlex.quote the {worktree} substitution) AND realpath-confine the snapshot path (reject
      ../ escape / absolute-path discard), mirroring the GRADER-SECFIX-RECONCILE F1/F2 pattern.
  Legitimate checks still grade identically (exit 0 -> MERGE/100, non-zero -> BLOCK/0).
  FAIL-ON-REVERT (fleet/benchmark/selftest/test_real_shell_injection.py — REQUIRED): a snapshot path /
  check_cmd carrying shell metacharacters (e.g. a path containing `; touch PWNED` or `$(...)`) does NOT
  execute the injected command; revert the guard -> the test goes RED. Legit check_cmd still grades
  correctly. [[gates-must-actually-run]] [[security-is-a-ratchet-gate]]
  VERIFY: cd fleet/benchmark && PYTHONPATH=. python3 -m pytest selftest/test_real_shell_injection.py -q
scope: |
  Kill the live shell=True command-injection at fleet/benchmark/graders/real.py:54 (data-derived
  check_cmd with an untrusted {worktree} substitution) — the ONE execution site GRADER-SECFIX-RECONCILE
  does not own. RANK-0 security ratchet, Priority-1 (operator-mandated 2026-07-22).
  [[security-is-a-ratchet-gate]] [[monitored-preflight-failure-attribution]]
impl: |
  DONE on fix/grader-real-shell-injection (2026-07-22): grade_reds_replay now runs check_cmd as an
  argv list with shell=False; the {worktree} snapshot path is substituted per-token so it can never
  inject; a check_cmd carrying shell metacharacters is refused with an explicit BLOCK/error verdict
  (never run through a shell). Fail-on-revert proof: fleet/benchmark/selftest/test_real_shell_injection.py
  (test_shell_injection_is_neutralized goes RED if shell=True is reintroduced). bandit (diff) + semgrep
  clean; grader selftests green.
