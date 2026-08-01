repo: charon-private
tier: strong
priority: 2
difficulty: 3
work_class: rig-meta
branch: feat/wip-close-gate
owns: fleet/end-session.sh
depends_on: SESSION-END-PUSH-GATE, SESSION-END-GATE-REPAIR
accept: |
  MECHANIZE the pre-existing-WIP catch — turn "noted" into "ticketed + scheduled" by
  construction. THE RECURRING ROOT CAUSE: session-start ALREADY prints
  "N uncommitted file(s) — prior session left WIP", but sessions IGNORE it and the WIP goes
  stale across handoffs. Concrete evidence: three untracked files
  (fleet/state/FREE-TIER-LIMITS.tsv, fleet/state/REACHABILITY-AUDIT.md, .ksf/) sat across
  multiple sessions — a prior session ("ahsoka") ignored them and THIS session almost did
  too. Noting is not enough; the operator directive is NEVER ignore pre-existing — every
  issue gets a TICKET and is SCHEDULED, or it goes stale.

  DO:
  1. Add a mechanized close-gate to `fleet/end-session.sh` (a new check, e.g.
     fleet/checks/no-untracked-wip.sh, wired in): a session CANNOT close cleanly while any
     untracked/uncommitted path exists UNLESS each such path is one of:
       (a) committed, (b) gitignored, or (c) covered by an OPEN board ticket whose `owns:`
       names it (a LIVE, non-parked ticket — so it schedules into a wave).
  2. On any uncovered WIP path, FAIL the close with the exact path(s) and the three
     resolutions, so the session must commit / ignore / file-a-ticket before ending.
  3. FAIL-ON-REVERT test: introduce an untracked file with no covering ticket -> gate RED;
     add a board ticket that `owns:` it -> gate GREEN.

  DO NOT hand-roll blindly: this is an instance of the meta-gate / enforcement theme.
  EVALUATE it inside the upcoming meta-gate ADOPT deep-dive (reuse the existing gate-registry
  + gate-runner substrate rather than a bespoke one-off). [[substrate-check-fires-at-decision-time]]
  [[gates-must-actually-run]]

  ACCEPT: fleet/end-session.sh blocks a clean close when untracked/uncommitted WIP is not
  committed, gitignored, or ticketed; the ownership-coverage check reads the board's `owns:`
  frontmatter; FAIL-ON-REVERT test proves it fires.
scope: |
  Rig-meta process enforcement. Closes the "session-start warns but nothing enforces" gap
  that lets pre-existing WIP go stale across handoffs. Compose the existing gate substrate;
  do not build a parallel gate framework. [[detection-ticketed-never-built]]
  [[mechanized-handoff-gate]] [[session-end-hardening]]
ds: |
  ## Dependencies & sequence
  depends_on: none to START, but the MECHANISM CHOICE waits on the meta-gate ADOPT
  deep-dive (adopt substrate vs hand-roll) — do not build the check blindly before that
  decision lands. Reuse the gate-registry / gate-runner the other fleet checks already use.
  Blast radius: end-session close path (gates a handoff) — adversarial review REQUIRED; the
  gate must actually fire (a self-referential close-gate must be reentrancy-safe).
  wave: rig meta-gate.
