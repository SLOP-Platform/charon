repo: charon-private
tier: strong
priority: 0
difficulty: 5
work_class: rig-meta
branch: feat/sg-issue-control-plane
owns: fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md
serial_justified: DESIGN umbrella — the design of record + the 3 build-slices (ISSUE-BOARD-SURFACE,
  ISSUE-SELF-HEAL-RULES, KS29-DISCOVERY-LEG) are the decomposition; this ticket tracks the whole, the
  slices are the parallel work. Not a single serial job.
depends_on:
source: operator 2026-07-24 (approved) + adopt-first investigation fleet/state/DESIGN-SG-ISSUE-CONTROL-PLANE.md.
  Supersedes/absorbs UNIFIED-PLANE-CANARY-FRAMEWORK, gate-test-health-on-master, loud-failure-monitor.
note: |
  THE universal DISCOVER -> SURFACE -> SELF-HEAL control plane: auto-discover every recurring failure
  CLASS (inert/not-wired, failing/RED, stale/drift, quarantined-good, junk-commit, done-but-unmerged,
  un-registered component), SURFACE them LOUDLY to manager/supervisor/operator so none is ever silently
  normalized, and (gated, per-class) AUTO-LAUNCH the fix to the SG droid tab.
  ARCHITECTURE = closed-loop event-driven auto-remediation control plane (sensors -> rule -> gated action,
  level-triggered on cadence, over graphify's relations graph). ADOPT THE PATTERN (StackStorm sensor->rule
  ->action + ArgoCD opt-in self-heal + K8s level-triggered + Backstage/Dagster facts->checks->scorecard/
  freshness); ADOPT NO TOOL (all service-shaped, wrong for a solo bash/python fleet). ~85% is already owned.
  Recommendation (from design): fold DISCOVER+SURFACE into the existing UNIFIED-RECONCILIATION-GATE axis,
  not a second reconciler. [[reviews-use-our-own-tools]] [[gates-must-actually-run]]
accept: |
  - The 3 slices land + wire together into one live loop; the plane is FULLY + COMPLETELY wired (no
    built-but-inert leg), proven by an e2e DOGFOOD: seed a real issue of each class -> it appears on the
    issue-board -> surfaces at SessionStart -> (for a safe class) auto-launches a reviewed fix.
  - ADVERSARIAL REVIEW (reviewer != builder) of the whole loop before it is trusted — a control plane
    that fake-greens is worse than none.
  - fail-on-revert: unwire any detector/leg -> the issue it would catch goes UNDETECTED -> a canary of the
    control-plane itself goes RED (who-tests-the-tester, closes the board-correctness class).
scope: |
  Umbrella + design; the work is the 3 slice tickets. Per-class detectors/remediations are DATA rows in
  the registries (anti-accretion KS20), not new code per class.
ds: |
  ## Dependencies & sequence
  P0 (operator SG-readiness north-star). Slices: ISSUE-BOARD-SURFACE (surface, do first — operator's #1
  pain) -> KS29-DISCOVERY-LEG (discover, highest-risk new build) -> ISSUE-SELF-HEAL-RULES (self-heal,
  gated, last). Composes graphify + the 6 existing detectors + lease-enqueue + review-pool.
