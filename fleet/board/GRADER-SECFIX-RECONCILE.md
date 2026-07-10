tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/grader-secfix-reconcile
depends_on: BENCH-OOB-GRADING
real-dep: BENCH-OOB-GRADING build (shared fleet/benchmark/grader-daemon.py, graders/, selftest/) — this
  reconciles TWO divergent grader lineages that both edited those files after their shared base b14f084:
  (1) feat/bench-oob-grading @ e879957 = the SECURITY-HARDENED grader (F1 sandbox-confine via _confine/
  SandboxError, F2 shell=False+argv, F5 pre-fix false-green guard, + 3 fail-on-revert security tests —
  independently VERIFIED 2026-07-10), and (2) feat/fragility-tickets = its own grader-daemon.py/
  test_grader_daemon.py evolution. A plain cherry-pick conflicts (add/add on test_grader_daemon.py).
  Shared-file reconciliation, JUSTIFIED.
owns: fleet/benchmark/grader-daemon.py, fleet/benchmark/graders/reds_replay.py, fleet/benchmark/selftest/test_grader_daemon.py
accept: cd fleet/benchmark && PYTHONPATH=. python3 -m pytest selftest/test_grader_daemon.py -q
  # ALL green, AND the 3 security tests (F1 traversal-rejected, F2 injection-neutralized, F5
  # already-green-scores-0) still go RED on revert of their guard. The security fixes are NON-NEGOTIABLE
  # and MUST survive the reconcile — verify by re-running the fail-on-revert proof.
prompt: /home/stack/charon-private/prompts/grader-secfix-reconcile.md
scope: >-
  Weave the VERIFIED security hardening (feat/bench-oob-grading @ e879957) into the canonical grader on
  the active RIG branch — do NOT let it rot on a side branch. Produce ONE grader-daemon.py + reds_replay.py
  + test_grader_daemon.py that carries BOTH lineages' intent: the security fixes (F1/F2/F5 — mandatory) AND
  whatever fragility-branch grader edits are worth keeping. Where the two edits touch the same code, the
  security-hardened version wins for the security-relevant paths. Land it on the active branch; retire
  feat/bench-oob-grading once merged. This is the #26 OOB-grader's last mile — it gates real benchmark
  scoring (the ranking brain pivot), so it should sequence right after BENCH-OOB-GRADING, not linger.
