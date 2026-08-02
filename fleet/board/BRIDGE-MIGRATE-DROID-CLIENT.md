repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/bridge-migrate-droid-client
depends_on:
owns: fleet/droid-bridge.sh, fleet/tests/droid-bridge.test.sh
serial_justified: |
  ONE consumer's migration: the client and its regression suite are two halves of the same
  swap. Landing the rewritten client without its suite ships an unproven control path for
  every droid; landing the suite without the client tests nothing. The migration is also the
  point at which the replace-vs-wire contradiction is resolved, so it cannot be half-done.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Own worktree, one checkout one agent.
source: |
  Operator decision 2026-07-31, accepting manager recommendation A after the SESSION-BRIDGE-CONVERGE
  triage (fleet/handoff-notes/BRIDGE-CONVERGE-TRIAGE.md, landed via PR #274).
note: |
  ## THE CONTRADICTION THIS RESOLVES
  Two landed P0s pull opposite ways. BRIDGE-REPLACE-PHASE1 replaces the hand-rolled
  session-bridge (~3,073 LOC) with `fleet/session-ctl.sh` over opencode's own HTTP server
  (operator decision 34). DROID-BRIDGE-REGISTER wired droids INTO that same bridge. Net effect:
  runtime consumers went 5 -> 7 DURING the replacement, and migration stalled at 1 of 7
  (`fleet/summary.sh` is the only one migrated).

  We are now paying to maintain both systems and finishing neither.

  ## WHY REPLACEMENT IS THE RIGHT DIRECTION (do not relitigate)
  The bridge requires the MODEL to call `register`/`update`. Models don't: 8 of 8 workers ran
  real work on 2026-07-26 without ever registering; a release-gate reviewer worked an hour
  invisible; the manager's own entry went 5.8h stale. `session-ctl` addresses opencode's HTTP
  server directly, taking the model out of the liveness loop entirely.

  ## SCOPE — ONE CONSUMER, THE RIGHT ONE
  Migrate `fleet/droid-bridge.sh` off `~/.config/opencode/session-bridge/proxy.py` and onto
  `fleet/session-ctl.sh`. It is the single consumer that both advances replacement AND undoes
  the contradiction, and `fleet/fleet-droid.sh` already calls it as middleware, so the blast
  radius is contained behind an existing seam.

  EXPLICITLY OUT OF SCOPE: the other 5 consumers (`fleet/capability/availability.py`,
  `fleet/capability/assign.py`, `fleet/dark-work-check.sh`, `fleet/handoff.sh`,
  `fleet/checks/bridge-health.py`), and DELETING any bridge code. Deletion happens only when
  the consumer count reaches zero. Propose, never execute, any deletion.

  ## KNOWN TRAPS — do not rediscover, each cost a prior session hours
  - `/api/session/active` is NOT a liveness signal — returns `{}` even for working sessions.
  - `/tui/*` returns `true` UNCONDITIONALLY. It means "published", not "received"; it returned
    true for nonsense command names. Never treat that response as proof.
  - `session-ctl launch` against a TUI worker creates ORPHAN sessions in the global store. For a
    TUI worker use `/tui/append-prompt` + `/tui/submit-prompt` on that worker's own port.
  - `/api/health` goes healthy BEFORE the TUI attaches; injecting in that window is silently
    dropped. Gate on health AND connection stability (see `wait_for_tui_ready` in spawn-worker.sh).
  - The opencode session store is GLOBAL across ports and PAGINATED. Never identify a session by
    count; identify by id + `time.created` (see `verify_spawn_start` in spawn-worker.sh).
  - The bridge ALREADY computes `stalled`/`stall_seconds` and auto-nudges. Do NOT introduce a
    second notion of liveness — reuse or replace, never duplicate.

  ## DONE CONTRACT
  - `fleet/droid-bridge.sh` no longer shells to `proxy.py` for its control path.
  - `fleet/fleet-droid.sh` push-mode register/heartbeat/unregister still works unchanged through
    the existing middleware seam — PROVE it with a real run, not an assertion.
  - `fleet/tests/droid-bridge.test.sh` passes, hermetic and offline, and each new assertion has
    been WATCHED RED against an externally-specified break, then GREEN. Paste both transcripts.
  - Report the new consumer count (was 7) and what remains.

## Dependencies & Sequence
  - Depends on: nothing to start. `session-ctl.sh` is landed in master and working.
  - Blocks: the remaining 5 consumer migrations, then DURABLE-BRIDGE-PHASE-2 (parked) and the
    ~3,073 LOC deletion.
  - Sequence: the 5 remaining consumers share files and must be sequenced one ticket each, NOT
    fanned out in parallel.
  - Disjoint from the research lanes running concurrently (those are read-only, no repo writes).
