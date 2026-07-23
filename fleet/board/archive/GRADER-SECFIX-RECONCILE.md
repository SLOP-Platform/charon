repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/grader-secfix-reconcile
depends_on: BENCH-OOB-GRADING
dep-kind: build
substrate: N/A
substrate-novel: |
  Reconciling two in-tree grader lineages and preserving verified security hardening (sandbox
  confinement, argv shell=False, false-green guard) built on stdlib subprocess/os. No external library
  adopts "merge two divergent branches" or "run a check command safely as argv" — the safe-subprocess
  pattern IS the fix, not a dependency. bandit (adopted separately) is the DETECTOR of this class, not
  the remediation.
real-dep: |
  BENCH-OOB-GRADING build (shared fleet/benchmark/grader-daemon.py, graders/, selftest/) — this
  reconciles TWO divergent grader lineages that both edited those files after their shared base b14f084:
  (1) feat/bench-oob-grading @ e879957 = the SECURITY-HARDENED grader (F1 sandbox-confine via _confine/
  SandboxError, F2 shell=False+argv, F5 pre-fix false-green guard, + 3 fail-on-revert security tests —
  independently VERIFIED 2026-07-10), and (2) feat/fragility-tickets = its own grader-daemon.py/
  test_grader_daemon.py evolution. A plain cherry-pick conflicts (add/add on test_grader_daemon.py).
  Shared-file reconciliation, JUSTIFIED.
owns: fleet/benchmark/grader-daemon.py, fleet/benchmark/graders/reds_replay.py, fleet/benchmark/selftest/test_grader_daemon.py
serial_justified: |
  reconciling two divergent lineages (feat/bench-oob-grading security-hardened vs
  feat/fragility-tickets) that both edited the SAME grader-daemon.py/reds_replay.py after shared
  base b14f084 is one merge-conflict resolution across both files, not two independent builds —
  splitting by file would let the two lineages' edits to shared functions diverge again instead
  of being reconciled (already noted inline above: "Shared-file reconciliation, JUSTIFIED").
ds: |
  ## Dependencies & sequence
  - depends_on: BENCH-OOB-GRADING (dep-kind: build) — reconciles the two lineages that both edited the
    shared grader-daemon.py / graders/ / selftest/ after base b14f084; grafts the verified F1/F2/F5
    hardening (feat/bench-oob-grading @ e879957) onto master's canonical function-daemon.
  - DISJOINT from GRADER-REAL-SHELL-INJECTION-FIX: that ticket owns graders/real.py (the live shell=True
    at real.py:54); THIS ticket owns grader-daemon.py / reds_replay.py / test_grader_daemon.py and does
    NOT touch real.py. No file overlap, so the two can land independently.
  - concurrency: single-writer on fleet/benchmark/ — must not run concurrently with any other grader ticket.
accept: |
  cd fleet/benchmark && PYTHONPATH=. python3 -m pytest selftest/test_grader_daemon.py -q
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
