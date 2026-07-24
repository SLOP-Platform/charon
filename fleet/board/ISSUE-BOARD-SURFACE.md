repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/issue-board-surface
owns: fleet/issue-board.sh, fleet/state/issue-board.tsv, fleet/tests/issue-board.test.sh
depends_on:
serial_justified: the aggregator + its board schema + the SessionStart-wire + fail-on-revert test are one
  atomic capability (a surfacer with no wire, or a wire with no aggregator, ships nothing).
source: SG-ISSUE-CONTROL-PLANE slice 1 (SURFACE leg) — the genuinely-missing piece + operator's #1 pain
  ("makes issues visible to manager sessions; no red ever silently normalized").
note: |
  The SURFACE leg. A thin aggregator that unions ALL existing DISCOVER detectors' verdicts (check_inert_code,
  plane-canary reconcile, reconcile-stale-claims, loop-guard, failing gate-tests/reds, done-but-unmerged)
  into ONE fleet/state/issue-board.tsv (severity|class|issue|source_detector|first_seen|age) + emits a
  SessionStart summary line to manager/supervisor sessions. first_seen/age ESCALATION makes silent
  normalization structurally impossible (an issue that persists gets louder). Level-triggered refresh via
  foreman-cadence.sh. A live prototype already dogfooded the detectors — build the real one on that.
accept: |
  - fleet/issue-board.sh aggregates every registered detector (fail-LOUD if a detector errors, never
    silent-empty); writes issue-board.tsv; prints the SessionStart line.
  - WIRED into the SessionStart hook (manager/supervisor sessions see it automatically — no manual run).
  - age-escalation: a persisting issue's severity/visibility rises with age (anti-normalization).
  - e2e DOGFOOD: seed a real inert + a real stale-claim + a real red -> all three appear on the board +
    in the summary line, on a real run.
  - fail-on-revert test: unregister a detector -> its issue class vanishes from the board -> RED.
  - ADVERSARIAL REVIEW (reviewer != builder).
scope: |
  The aggregator + SessionStart surface only. Detectors already exist; this UNIONS them. Self-heal is a
  separate slice (ISSUE-SELF-HEAL-RULES); discovery of NEW detectors is KS29-DISCOVERY-LEG.
ds: |
  ## Dependencies & sequence
  P0, slice 1 (do FIRST — operator wants to SEE surfacing). No hard prereq (detectors exist). Feeds
  ISSUE-SELF-HEAL-RULES. Consider folding into UNIFIED-RECONCILIATION-GATE per the design.
