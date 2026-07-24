repo: charon-private
tier: strong
priority: 0
difficulty: 3
work_class: rig-meta
branch: feat/droid-bridge-register
owns: fleet/droid-bridge.sh, fleet/fleet-droid.sh, fleet/tests/droid-bridge.test.sh
depends_on:
serial_justified: name-claim + register + heartbeat + unregister-trap + pickup-gate are ONE session
  lifecycle — a droid that registers but never heartbeats (goes stale) or never unregisters (strands its
  report) is the exact dark-work gap this closes; splitting them ships a half-lit session.
source: |
  F47 (no-dark-work: register every session + pickup-gate) + F19 (bridge-unregister-trap). This session
  confirmed droids run DARK: fleet/fleet-droid.sh:232 sets DROID="$TIER-$$" (a PID label, no allocator) and
  has ZERO bridge wiring — 5 live droids sat 28-min heartbeat-stale, none on the bridge board. REUSE (do NOT
  re-implement): fleet/claim-jedi-name.sh (conflict-free allocator, LANDED via #223) + the session-bridge
  proxy.py JSON-RPC entry (bash-reachable: register/update/unregister). Belongs to the launcher-governance
  family — coordinate with SUBAGENT-WORKTREE-SANDBOX (both edit the fleet-droid.sh launch block).
note: |
  Wire the droid launcher's bridge lifecycle:
  - ON CLAIM: claim-jedi-name.sh -> a conflict-free session name (replace $TIER-$$); session-bridge register
    (via proxy.py). FAIL-LOUD if register fails — never run dark silently (that's the pickup-gate: refuse to
    start work unregistered).
  - WHILE ALIVE: a background heartbeat loop pings the bridge every < 600s (lease TTL) as long as the droid
    PID lives, so the session never goes stale on the board.
  - ON EXIT (trap, incl. INT/TERM): unregister + RELEASE the name. Use ephemeral markers (never committed) so
    the 69-name pool can't drain from droid churn.
accept: |
  - e2e DOGFOOD: launch a REAL droid -> it appears on `session-bridge board` -> its heartbeat refreshes past
    at least one 600s TTL window -> on exit it is UNREGISTERED and its name RELEASED back to the pool. Real run.
  - FAIL-LOUD: a forced register failure makes the droid refuse to start (pickup-gate), never run dark.
  - REUSE claim-jedi-name.sh (landed) — do NOT re-implement name allocation.
  - fail-on-revert test: remove the heartbeat loop -> the "stays live past one TTL" assertion goes RED; remove
    the exit trap -> the "unregistered on exit" assertion goes RED.
  - ADVERSARIAL REVIEW (reviewer != builder) — edits the shared money-path launcher fleet-droid.sh.
scope: |
  The droid-launcher bridge lifecycle (name-claim + register + heartbeat + unregister-trap + pickup-gate) only.
  The bridge DAEMON's own liveness/reboot-survival is SERVICE-LIVENESS-WATCHDOG's job (session-bridge daemon is
  a registry entry there), NOT this ticket. Coordinate the fleet-droid.sh launch-block edit with
  SUBAGENT-WORKTREE-SANDBOX — anchor whichever lands first; this is the bridge slice.
ds: |
  ## Dependencies & sequence
  P0. HANDOFF-NAME-ALLOCATOR (claim-jedi-name.sh) is LANDED so the naming prereq is satisfied. Shares the
  fleet-droid.sh launch block with SUBAGENT-WORKTREE-SANDBOX — sequence, do NOT parallel-edit. Pairs with
  SERVICE-LIVENESS-WATCHDOG (which supervises the bridge daemon itself).
