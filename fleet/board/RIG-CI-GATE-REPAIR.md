repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: ci-infra
branch: fix/rig-ci-gate-repair
owns: fleet/state/tier-drift-red.txt, fleet/state/service-registry.tsv, fleet/tests/tier-drift.test.sh, fleet/tests/board-file-ratchet.test.sh, fleet/tests/board-correctness.test.sh, fleet/watchdog/monit.d
depends_on:
serial_justified: |
  One defect class (gate SSOTs absent from every CI checkout) across four files that must land
  as a single commit — the RED set and the registry are each read BY the suites changed here, so
  splitting them means landing a suite that reds until its sibling PR merges. Not decomposable.
substrate: N/A — no build-vs-adopt choice arises; every mechanism here is ALREADY adopted
substrate-novel: |
  This ticket writes NO new tool and NO non-trivial new module. It ships two DATA files that
  the rig's existing gates already read, and repairs two existing suites' fixtures:
    * monit is already the ADOPTED supervisor — fleet/watchdog/generate-monit-config.sh renders
      its config; this commit supplies the registry row data that generator consumes, and
      regenerates one stanza. No liveness loop is hand-rolled.
    * the tier-drift gate (validate_board 2f + fleet/capability/tier_classify.py), the rig-ci
      allowlist, and verify-restart-cmds.sh all already exist and are unmodified in behaviour.
  The novel slice is exactly "the file our own gate reads was never committed" — there is no
  external tool that commits your repository's own configuration for you.
accept: |
  rig-ci is GREEN on this PR, with no gate weakened, baselined away or `|| true`-ed.
  1. fleet/state/tier-drift-red.txt is COMMITTED and non-vacuous; tier-drift.test.sh (a1)(a2)(a3)
     pass. Fail-on-revert: delete the file or its .gitignore negation -> (a1/a2/a3) RED.
  2. NEW (a4) anti-padding: every RED-set id resolves to a real ticket on a security surface.
     Fail-on-revert: append a fabricated id -> (a4) RED (proved).
  3. fleet/state/service-registry.tsv is COMMITTED and passes verify-restart-cmds --static-only;
     generate-monit-config.sh --check reports IN SYNC. Fail-on-revert: restore any restart_cmd to
     its root-unsafe seed -> verify-restart-cmds.test.sh case 8 RED.
  4. tier-drift.test.sh is HERMETIC: it reads no fleet/board/*.md and pins CHARON_REPO, so
     archiving/retiring/re-tiering any real ticket cannot red it.
  5. board-file-ratchet.test.sh passes BOTH standalone and with RIG_CI_TESTS_ACTIVE=1 set (the
     way rig-ci actually runs it). The fork-bomb guard is unmodified and now carries its own
     fail-on-revert assertion: delete the RIG_CI_TESTS_ACTIVE short-circuit -> RED.
scope: |
  Rig CI merge-gate repair. rig-ci was RED on every open rig PR, so the gate was effectively OFF
  and every merge was a judgement call. Fixes the CAUSES (missing committed gate SSOTs; two suites
  coupled to mutable live state) rather than the symptoms. Does NOT touch fleet/checks/rig-ci-scope.sh
  (contended by HANDOFF-GATE-NONBYPASSABLE + REVIEWER-TAB-POOL) or the priority-validator cause
  (owned by a concurrent ticket). [[gates-must-actually-run]] [[security-is-a-ratchet-gate]]
  [[fleet-selfcheck-forkbomb-class]] [[fix-root-cause-never-workaround]]
ds: |
  ## Dependencies & sequence
  - depends_on: NONE. File-disjoint from every open rig PR: no other live ticket owns
    fleet/state/tier-drift-red.txt, fleet/state/service-registry.tsv, fleet/tests/tier-drift.test.sh,
    fleet/tests/board-file-ratchet.test.sh or fleet/watchdog/.
  - SEQUENCE: land FIRST, ahead of the open-PR queue. Until it lands every other PR is RED for
    reasons that have nothing to do with its own diff, so no PR in the queue can be judged on merit.
  - The priority-validator RED (6 tickets carrying a non-integer `priority:`) is a SEPARATE cause
    owned by a concurrent ticket; both must land before rig-ci is fully green.
