repo: charon-private
tier: strong
difficulty: 2
work_class: rig-meta
priority: 0
branch: fix/bridge-proxy-heartbeat
depends_on:
owns: /home/stack/.config/opencode/session-bridge/proxy.py
serial_justified: |
  ONE process's lifecycle contract: the lease refresh and the exit-unregister are two halves of the
  same guarantee (a board entry exists exactly while its proxy lives). Splitting them ships one
  failure mode fixed and the other still live.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session (charon/* gateway model), NOT Claude.
  Graded sample: record into fleet/model-scorecard.tsv. One checkout, one agent.
  NOTE: `session-bridge/` is its OWN git repo — commit there, not in charon-private or charon.
source: |
  Operator decision 22, 2026-07-26. Three sessions in one day (qui-gon-jinn, kit-fisto reviewer,
  and the manager) were purged from the board WHILE STILL WORKING.
note: |
  ## THE DESIGN IS RIGHT; ONE PIECE IS MISSING
  The bridge is already durable and correct: a shared daemon on Roci, **lease-based liveness
  (deliberately NOT PID, so it works cross-host)**, graduated purge (nudge -> nudge -> escalate ->
  purge, daemon.py:222), atomic ticket claim/release, and a secret allowlist so `lease_token` never
  leaves the daemon (daemon.py:94). None of that needs changing.

  **The hole:** `proxy.py` has NO heartbeat. `grep -n "thread|Timer|atexit" proxy.py` returns
  nothing — it is a pure stdio forwarder (`_forward`, `main`, `_respond`, `_error`). So the ONLY
  thing that refreshes a lease is the model choosing to call `update` every few minutes.

  Models do not. Observed 2026-07-26, three for three, despite an explicit instruction in the prompt.
  This is our own documented anti-pattern: enforce structurally, do not ask politely.

  ## THE TWO FAILURE MODES IT CAUSES
  1. **Live session goes invisible.** A session working normally stops heartbeating, its 600s lease
     expires, graduated purge removes it. The manager sees an empty board and cannot tell who is
     working — happened to the release-gate reviewer while it was mid-review.
  2. **Ghost lingers.** A session that ends leaves its entry until the lease expires, so the board
     shows work that stopped. Its ticket claim lingers with it.

  ## THE FIX — in the TRANSPORT, not the prompt
  `proxy.py` is already one long-lived process per session, and every MCP call passes through
  `_forward`. Two changes:
  1. **Remember the `session_id`** from the `register` call it forwards, then refresh the lease from a
     background timer at roughly TTL/3. Liveness becomes "the proxy is alive" — which is the truth we
     actually want — while remaining LEASE-based, so the cross-host design is untouched. Do NOT
     switch to PID-based liveness: that is explicitly rejected in daemon.py:10 because the daemon
     runs on a different host.
  2. **`atexit` (and SIGTERM/SIGINT) -> `unregister`.** Session ends, entry disappears, claim released.

  ## GUARD AGAINST THE OBVIOUS REGRESSION
  A hung proxy must not fake liveness forever. Bind the heartbeat to the session actually being
  alive — stop refreshing when stdin closes / the parent goes away. A heartbeat that outlives its
  session recreates ghosts with extra steps.
accept: |
  DONE-CONTRACT (observable, by EXECUTION):
  - A session that registers and then sits IDLE for longer than `SESSION_BRIDGE_TTL` (600s) is STILL
    on the board afterwards. Demonstrate it: register, wait out the TTL without any tool call, show
    `board()` still lists it. This is the primary claim — prove it by waiting, not by reasoning.
  - Killing the proxy removes the entry: show `board()` before and after, entry gone, ticket released.
  - The heartbeat STOPS when the session ends — prove a killed proxy does not keep refreshing.
  - RED-PROOF BY EXECUTION: disable the heartbeat -> the idle-session test goes RED (purged).
    Report BOTH exit codes.
  - NON-VACUOUS: a test that never waits past the TTL proves nothing — the wait must be real, and a
    zero-length wait must fail the test.
  - No change to daemon.py, to the lease model, or to the secret allowlist. If the fix appears to
    need a daemon change, STOP and report — the daemon is shared across hosts and repos.
  - FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.** Own repo (`~/.config/opencode/session-bridge`),
  disjoint from charon and charon-private — cannot collide with any board ticket.
- **Blocks:** nothing formally, but every future session's visibility depends on it. Run it early —
  each session dispatched before this lands is one the manager may lose sight of.
- **Wave:** parallel lane, P0.
