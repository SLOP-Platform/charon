repo: charon-private
tier: frontier
priority: 0
difficulty: 5
work_class: ci-infra
branch: feat/fleet-status-board
depends_on:
owns: fleet/session-status.sh, fleet/state/CHECK-REGISTRY.tsv, fleet/tests/session-status.test.sh, fleet/state/FLEET-STATUS-BOARD.md, docs/review-log/FLEET-STATUS-BOARD.md
serial_justified: |
  The registry, the runner and the bidirectional meta-check are ONE mechanism — a registry with
  no runner is a list, a runner with no meta-check is another thing that can silently stop. Any
  split ships a half that reads as protection while providing none, which is the exact class
  this ticket exists to end.
substrate: N/A
substrate-novel: |
  Every DETECTOR already exists and stays adopted as-is: stranded-work.sh, gate-integrity.sh,
  validate_board.sh, reap-orphans.sh, rescue-push.sh, check_inert_code.py. Nothing new detects
  anything. The novel slice is the REGISTRY plus the bidirectional assertion that every
  registered check produced a verdict and every verdict maps to a registered check — i.e. making
  the checks themselves a tracked class. No external tool models your fleet's check inventory.
accept: |
  WHY: measured 2026-08-02, at least a dozen CLASSES accumulate silently — claims (dead owners
  never released), worktrees (17 dirty, no live claim), tickets (merged but live), proof suites
  (101 declaring red-proof, never run in CI, count ROSE 91->101 in one day), gates (9 inert, 1
  fake-done owning 2 files that do not exist), tools (3 never committed; graphify affected at 0
  call sites), reviews (35 untracked), operator actions (30 and climbing), config SSOT
  (SPILL_UP_COST_CEILING absent so spill-up fails closed fleet-wide), deployed artifacts (4-LOM
  on an old build_sha), catalog/pricing rot (10 of 861 priced), daemons slated for retirement
  still running — and the SCHEDULED CHECKS THEMSELVES (the crontab entry is untracked
  machine-local config).
  Common shape: anything with a lifecycle and no terminal gate accumulates.
  Done contract:
  1. `fleet/state/CHECK-REGISTRY.tsv` — one row per check: name, command, cadence, heartbeat
     path, owner. Tracked in git.
  2. `fleet/session-status.sh` — runs every registered check, prints a COMPACT verdict table.
     Each check emits exactly one of: OK | FINDING(n) | STALE | BROKEN.
     STALE = the check's own heartbeat is older than its cadence (registered but not executing —
     the two-leg rule proven live tonight). BROKEN = the check failed to execute. Both are
     DISTINCT from clean; neither may be reported as OK.
  3. BIDIRECTIONAL META-CHECK — every registry row must produce a verdict line, and every
     verdict line must map to a registry row. A check deleted, renamed, or silently stopped
     shows as MISSING. **This is the load-bearing property**: it is what would have caught the
     reviewer pool sitting at ZERO for hours, gate.sh being unrunnable for weeks, and 101 proof
     suites never executing.
  4. Wire into the GIT-TRACKED `fleet/hooks/session-start.sh`, NOT
     `.claude/settings.local.json` — that file is machine-local and untracked, so a fresh clone
     or another box loads nothing (PRIORITY-TODO §F2). The doctrine is durable; its LOADING is
     not, and that is the gap.
  5. Escalate findings to `fleet/state/OPERATOR-ACTIONS.md` via `pending.sh add --key` (keyed
     upsert, so a cadence over a standing backlog updates in place instead of appending ~72
     rows/day — measured).
  6. FAIL-ON-REVERT, all three: (a) delete a registry row -> its check must show MISSING, not
     vanish; (b) stop a check's heartbeat -> STALE, not OK; (c) make a check exit non-zero ->
     BROKEN, not OK. Report all three verbatim.
  Registry seed (each already has a working detector): stranded-work, gate-integrity,
  validate_board, rescue-push at-risk, reap-orphans claims, needs-push markers, dirty worktrees,
  proof-suite enforcement (G5), inert code, deploy drift (4-LOM build_sha vs master),
  operator-action age.

## Dependencies & Sequence

P0. No inbound deps. This is the META-gate: it does not detect anything new, it ensures the
things that DO detect are still running and still visible. Every other detector on the board is
worth less without it, because today proved that a check can stop working for weeks and nobody
notices.
Sequence inside: registry (1) -> runner (2) -> meta-check (3) TOGETHER as one landing (see
serial_justified), then the hook wiring (4), then escalation (5). Seed the registry with checks
that ALREADY WORK — do not add a row for anything not yet proven to fire.
