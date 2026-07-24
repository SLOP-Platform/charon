repo: charon-private
tier: strong
priority: 0
difficulty: 4
work_class: rig-meta
branch: feat/issue-self-heal-rules
owns: fleet/issue-heal.sh, fleet/state/self-heal-allowlist.tsv, fleet/tests/issue-heal.test.sh
depends_on: ISSUE-BOARD-SURFACE
real-dep: ISSUE-BOARD-SURFACE — self-heal consumes the issue-board's verdicts; the board must exist + emit
  a stable schema before a rule layer can act on it. dep-kind: build.
serial_justified: the rule engine + the per-class allowlist + the fail-closed test are one gated capability;
  splitting ships an actuator with no safety allowlist (dangerous) or an allowlist with no actuator.
source: SG-ISSUE-CONTROL-PLANE slice 3 (SELF-HEAL leg) — operator: "ideally it will have self-fixing
  features (can launch work to SG tab)."
note: |
  The gated SELF-HEAL leg (ArgoCD opt-in-per-app analog). For each issue on the board, a rule maps class ->
  remediation; if the class is on the safe_to_auto_fix ALLOWLIST, it AUTO-LAUNCHES the fix as work to the
  SG droid tab: verdict -> remediation ticket -> fleet/lease-enqueue.sh (exactly-once claim) ->
  review-pool.sh (reviewer != builder, fail-closed BOUNCE). DEFAULT is REPORT-ONLY; acting stays a manager
  decision except for allowlisted classes. HARD: an auto-fix NEVER goes direct-to-master — always through
  review (closes the --commit-dirty sweep hazard [[commit-dirty-sweeps-subagent-wip]]).
accept: |
  - per-class safe_to_auto_fix allowlist (data rows); non-allowlisted classes are report-only.
  - an allowlisted issue auto-mints a remediation ticket + enqueues via lease-enqueue.sh (exactly-once,
    no double-launch) + routes the result through review-pool (BOUNCE on any doubt).
  - e2e DOGFOOD: seed a real allowlisted issue (e.g. a stale claim) -> a fix is auto-launched -> lands ONLY
    after review passes; seed a non-allowlisted issue -> report-only, no launch.
  - fail-on-revert: an auto-fix that bypasses review is REFUSED (test proves the review gate is load-bearing).
  - ADVERSARIAL REVIEW (reviewer != builder) — auto-remediation that bypasses review is a critical hazard.
scope: |
  The rule engine + allowlist + the launch-through-review path. Reuses lease-enqueue + review-pool (do NOT
  rebuild them). Detection = the other slices; this only ACTS, gated.
ds: |
  ## Dependencies & sequence
  P0, slice 3 (LAST — needs the board to act on). depends_on ISSUE-BOARD-SURFACE. Composes lease-enqueue
  (exactly-once) + review-pool (reviewer firewall).
