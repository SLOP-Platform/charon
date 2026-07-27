repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
branch: feat/startup-context-diet
depends_on: REPO-DECL-CENTRAL
owns: /home/stack/charon-private/fleet/MANAGER-OPERATING-RULES.md, /home/stack/charon-private/fleet/handoff.sh, /home/stack/charon-private/fleet/handoff-check.sh, /home/stack/charon-private/fleet/preflight.sh, /home/stack/charon-private/fleet/START-SESSION.md
serial_justified: the deliverable is ONE aggregate startup-token-budget measurement (before/after)
  and ONE regression check spanning all 5 tracked artifacts — the budget is a SUM across files, so
  a cut in one artifact changes the total the shared budget-gate checks against the others;
  splitting by file would make the budget-check ticket read files another ticket is concurrently
  trimming, racing on the aggregate invariant itself.
accept: |
  AUDIT everything that loads/reads at session start + the work process, and cut context/token cost
  WITHOUT losing rigor. In scope: the SessionStart hook cat (MANAGER-OPERATING-RULES.md — it is
  growing), the handoff FORMAT + size (per-session files accrete), preflight verbosity, the MEMORY.md
  index + recalled memories, START-SESSION, and the boot sequence a fresh session runs.
  Deliverables: (1) a before/after measurement of startup context (byte/token count of what a fresh
  session ingests), (2) concrete cuts applied (dedupe rules, slim/roll-up old handoffs, tighten
  preflight output, demote verbose memories to pointers), (3) a documented STARTUP BUDGET + a check
  that flags when startup context regresses past it. Fail-on-revert: a test/check that the budget
  gate fires when the tracked startup artifacts exceed the budget.
scope: |
  Operator ask (2026-07-10): make startup + the work process faster with LESS context/token use;
  clean up and optimize the handoff/rules/etc. Rigor (adversarial review, fail-on-revert tests, live
  verify) is NOT to be trimmed — cut manager NARRATION/overhead and artifact bloat, per
  MANAGER-OPERATING-RULES §9 (token-economy is DEFAULT).
ds: Now (rig-only, disjoint from product). The NEXT session should do this early.
