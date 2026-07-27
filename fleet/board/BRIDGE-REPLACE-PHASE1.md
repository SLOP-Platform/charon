repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 0
branch: feat/bridge-replace-phase1
depends_on: D24-SESSION-CTL-SPIKE
real-dep: D24-SESSION-CTL-SPIKE — TRUE build prereq and shared single-owner of fleet/session-ctl.sh.
  This ticket LANDS the very file that spike produced (spike/session-ctl @ c74e85b); it is a
  continuation, not a parallel writer. Land the spike first, then build on it.
dep-kind: build
owns: fleet/session-ctl.sh, fleet/summary.sh, fleet/tests/session-ctl.test.sh
prompt: /home/stack/charon-private/prompts/BRIDGE-REPLACE-PHASE1.md
serial_justified: |
  ONE adapter plus its first real consumer. Landing the wrapper without migrating a consumer proves
  nothing; migrating a consumer without the wrapper has nothing to call.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Own worktree.
source: |
  Operator decision 34 (2026-07-26): replace the session-bridge. Evidence:
  fleet/handoff-notes/SPIKE-SESSION-CTL-2026-07-26.md (verdict GO, all 5 verbs VERIFIED) and
  fleet/handoff-notes/RESEARCH-AGENT-COMMS-2026-07-26.md.
note: |
  ## WHY REPLACE THE BRIDGE
  The hand-rolled session-bridge (3,073 LOC + one sidecar per session) requires the MODEL to call
  `register`/`update`. Models don't: **8 of 8 workers ran real work on 2026-07-26 without registering.**
  A release-gate reviewer worked an hour while invisible; the manager's own entry went 5.8h stale.
  The spike VERIFIED all five control verbs against opencode's own HTTP server:
  SEE / STEER (`delivery:"steer"` admitted mid-turn, `admittedSeq:7`) / STOP (interrupt on a genuinely
  running session) / WATCH (SSE) / DEATH (kill -9 -> `Connection refused` instantly).
  **MCP tool calls are model-elective; an HTTP server is harness-elective — the model has no vote.**

  ## WHY THIS TICKET IS DELIBERATELY SMALL
  The full migration touches 6 rig scripts, and those files are claimed by ~10 live tickets
  (`fleet-droid.sh` alone has FIVE owners; `end-session.sh` four; `droid-bridge.sh` two). A single
  migration ticket would be a mass collision. **This ticket takes the only collision-free slice:**
  the new adapter plus `summary.sh`, which no live ticket owns.
  The remaining consumers migrate INSIDE their own owners' tickets, later. Do not touch them here.

  ## WHAT THE SPIKE ALREADY SETTLED (do not re-derive)
  * Claims/leases: already `work-lease.sh` + Faktory — NOT the bridge. Nothing to replace.
  * Nudge queue: superseded by synchronous `delivery:"steer"`, not parked messages.
  * Cross-host liveness: reachability probe, arguably STRONGER (no false ghosts). Residual regression:
    a dropped-host worker reads "unreachable" not "lease-expired"; Faktory `reserve_for` covers reclaim.
  * Jedi-name registry: becomes a launcher-written mapping file.
  * Agent-agnostic directive is satisfied at the ADAPTER boundary — only the backend changes if a
    non-opencode worker is added.

  ## SCOPE
  1. Land `fleet/session-ctl.sh` from the spike (`spike/session-ctl` @ c74e85b) — 5 verbs:
     `list | steer <id> <msg> | stop <id> | reply <id> <answer> | watch`. Curl only. No daemon, no
     framework, no new dependency. Thin enough to delete.
  2. Migrate `fleet/summary.sh` off `session-bridge_board` onto `GET /api/session`.
  3. Add a name->port registry mechanism so the manager can address a session by name.
  **Do NOT delete or modify the bridge.** Both run in parallel until every consumer has moved.
accept: |
  DONE-CONTRACT (observable, by EXECUTION):
  - All 5 verbs demonstrated against a REAL session launched with `--port`, actual commands and
    responses pasted. **`stop` must be proven on a session genuinely mid-work** — an interrupt that
    "succeeds" on an idle session proves nothing (`--attach` already produced exactly that false
    positive).
  - `summary.sh` produces equivalent output via HTTP with the bridge NOT consulted. Show before/after.
  - RED-PROOF BY EXECUTION: point session-ctl at a dead port -> it fails LOUDLY, does not silently
    report an empty fleet. Report BOTH exit codes. A control plane that reports "no sessions" when it
    cannot reach anything is the invisibility bug in a new costume.
  - NON-VACUOUS: `list` against zero sessions must be distinguishable from `list` against an
    unreachable server.
  - The 4+ LIVE fleet sessions untouched — list PIDs before and after and prove it.
  - The bridge still works afterwards (parallel running) — prove `session-bridge_board` still responds.
  - FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
## Dependencies & sequence
- **Depends on: NOTHING. Startable immediately.** Owns one new script, one unowned script, one new test.
- **Blocks:** BRIDGE-REPLACE-PHASE2 (migrating the contended consumers inside their owners' tickets)
  and eventual deletion of the bridge.
- **Makes moot:** BRIDGE-PROXY-HEARTBEAT's nudge-clearing defect (operator decision 25b deferred it
  pending this) — `steer` replaces the nudge queue entirely.
- **Wave:** migration lane, P0.
