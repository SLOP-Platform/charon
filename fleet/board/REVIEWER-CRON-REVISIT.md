repo: charon-private
tier: economy
priority: 2
difficulty: 2
work_class: rig-meta
branch: feat/reviewer-cron-revisit
depends_on:
owns: fleet/checks/reviewer-cron-trigger.sh, fleet/tests/reviewer-cron-trigger.test.sh, fleet/state/REVIEWER-CRON-REVISIT.md
serial_justified: |
  One trigger predicate and its red-proof. Splitting the predicate from its test is the failure
  this ticket exists to prevent.
substrate: N/A
substrate-novel: |
  No tool to adopt. This is a DEFERRED-DECISION TRIGGER over this rig's own scripts - it asks
  whether five named defects in fleet/review-pool.sh are closed. No external tool can answer a
  question about our own source. The cadence substrate (cron) is already adopted and already
  running two jobs; this registers a third predicate into it rather than building any scheduler.
source: |
  OPERATOR-DECIDED 2026-08-02, option C1 - the PR-draft cadence produces a WORKLIST ONLY and does
  NOT launch reviewers. Operator, verbatim - "BUT i want the revisit in a ticket with a trigger."
  This ticket is that trigger. It exists because a deferral with no firing condition is how work
  goes stale [[detection-ticketed-never-built]].
note: |
  ## WHY THE REVIEWER HALF IS NOT CRONNED TODAY
  `fleet/review-pool.sh` has FIVE open defects. The decisive one - its dispatch calls
  `main_loop "$CMD"` and SILENTLY DROPS `--wait` and `--retries`. MEASURED 2026-08-02 - a reviewer
  tab launched with `--wait 5` reached `cycle 461/0` in minutes, each cycle issuing a `gh` GraphQL
  call. That drained GraphQL from 5000 to 0 and stalled every merge fleet-wide; killing the pools
  restored it to 3784/5000 immediately.
  **Never automate, unattended, a component whose known failure mode is an unattended runaway.**
  That is the entire reason for the deferral - not doubt about the value.

  ## THE TRIGGER - what must be TRUE before the reviewer half may be cronned
  All five must hold. The check is fail-CLOSED - unknown counts as NOT met.
  1. `review-pool.sh` HONOURS `--wait` and `--retries` end to end (the `main_loop "$CMD"` drop is
     fixed), proven by a suite that goes RED when the fix is reverted.
  2. That suite is in the LITERAL `CI_SUITES` allowlist in `fleet/checks/rig-ci-scope.sh`. A suite
     outside the allowlist has never executed in CI [[gates-must-actually-run]].
  3. The done-marker-on-INFRA-failure defect is closed - an infra fault must never permanently
     retire a PR. 16 PRs hit this on 2026-08-02 and were quarantined by hand.
  4. `queue_gen` is idempotent and locked, OR `review-pool.sh` has been cut over to
     `fleet/pr-queue.sh` (landed as PR #392, REST + ETag, zero-quota steady state).
  5. The stale model chain in `review-pool.sh` is refreshed - the catalog is LIVE DATA and a
     pinned chain rots [[MANAGER-OPERATING-RULES sec.14]].

  ## HOW IT FIRES
  `fleet/checks/reviewer-cron-trigger.sh` evaluates the five conditions and prints a one-line
  verdict. While ANY condition is unmet it exits 0 and stays quiet - a nagging check gets muted,
  and a muted check is a dead check. When ALL five are met it exits NON-ZERO, prints
  `REVIEWER-CRON-TRIGGER - FIRED`, and escalates via `fleet/pending.sh` so the OPERATOR is asked
  to re-decide C1. It never enables anything itself - the decision returns to the human who
  deferred it, which is the point of a trigger rather than an auto-enable.

  Register it on the SAME cron cadence that already runs `stranded-work-cron.sh`. Do NOT create a
  new scheduler. Verify BOTH legs [[F8]] - registered AND executing (heartbeat under 20 min old);
  a registered job that never runs reads as clean, which is the failure mode.
accept: |
  a. `fleet/checks/reviewer-cron-trigger.sh` implements all five conditions, fail-closed.
  b. RED-PROOF, both directions - with the defects present the check is QUIET and exits 0; with
     all five conditions satisfied in a fixture it FIRES and exits non-zero. A trigger that has
     never been seen to fire proves nothing.
  c. Anti-false-fire - satisfying only FOUR conditions must NOT fire. Assert each of the five
     individually holds the trigger closed.
  d. Registered on the existing cron cadence, with BOTH legs verified - `crontab -l` shows it AND
     a heartbeat file is under 20 minutes old.
  e. On firing, an entry appears via `fleet/pending.sh` naming this ticket and asking the operator
     to re-decide C1.
  f. Hermetic - no network, no live `gh` call, no live gateway call. Fixtures only.
scope: |
  The trigger predicate, its test, and its cron registration. Does NOT fix any review-pool.sh
  defect (those are E4 and belong to their own tickets) and does NOT enable the reviewer cron.

## Dependencies & Sequence

- **depends_on: none.** The trigger is built against the CURRENT broken state - that is what makes
  its quiet path testable today.
- **Does NOT block the PR-draft triage cadence.** That cadence is worklist-only by decision C1 and
  ships without any reviewer automation.
- Sequenced AFTER `MERGE-QUEUE-ADOPT-CHECK`, which may shrink the cadence enough to change what a
  reviewer lane is even for. Ordering only, not a build prereq.
- The five conditions reference `review-pool.sh` defects tracked as E4 in
  `fleet/state/PRIORITY-TODO.md`. This ticket OBSERVES them; it does not own or fix them.
