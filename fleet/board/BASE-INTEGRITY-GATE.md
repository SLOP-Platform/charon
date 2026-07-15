repo: charon-private
tier: strong
difficulty: 3
work_class: ci-infra
branch: feat/base-integrity-gate
depends_on:
owns: fleet/checks/base-integrity.sh, fleet/tests/base-integrity.test.sh
accept: |
  MECHANIZE the fix for the recurring WRONG-BASE bug (operator directive: "nothing GATES base-integrity at launch"). Root
  cause this session: origin/master went 17 commits stale behind an unpushed integration branch, so tabs built base=master on
  the gap -> PRs #56/#57 were base-invalid. DO: fleet/checks/base-integrity.sh — before a tab/session builds a ticket, VERIFY
  the base (master or declared base) contains the ticket's prerequisite commits (its depends_on merges + the integration HEAD);
  REFUSE/warn on a stale base. Wire into fleet-droid.sh (tabs) + launch-plan.sh + the PreToolUse:Agent hook (sub-sessions).
  Also flag an unpushed local integration branch that origin/master lacks (don't hoard integration off-origin).
  FAIL-ON-REVERT (fleet/tests/base-integrity.test.sh): a ticket whose base lacks a prereq commit is REFUSED (revert gate -> builds on stale base -> RED).
