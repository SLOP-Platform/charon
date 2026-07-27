repo: charon-private
tier: strong
difficulty: 3
work_class: rig-meta
priority: 1
branch: spike/session-ctl
depends_on:
owns: fleet/session-ctl.sh, fleet/handoff-notes/SPIKE-SESSION-CTL-2026-07-26.md
prompt: /home/stack/charon-private/prompts/D24-SESSION-CTL-SPIKE.md
serial_justified: |
  ONE timeboxed spike producing ONE wrapper plus its evidence. The wrapper is meaningless without the
  verification that each verb actually works, and the verification is unrepeatable without the wrapper.
execution: |
  ASSIGNED TO A NON-ANTHROPIC MODEL via an `opencode` session. Graded sample. Timebox ~2h.
  Own worktree. This is a SPIKE — prove or disprove; migrate nothing.
source: |
  Operator decision 24, 2026-07-26. Evidence base:
  fleet/handoff-notes/RESEARCH-AGENT-COMMS-2026-07-26.md (442 lines).
note: |
  ## THE PROBLEM IT ANSWERS
  The hand-rolled session-bridge (3,073 LOC + one sidecar process per session) depends on the MODEL
  choosing to call `register`/`update`. Models don't: **8 of 8 workers ran real work on 2026-07-26
  without ever registering**, and the manager repeatedly could not see or reach live sessions —
  including a release-gate reviewer that worked for an hour while invisible, and the manager's own
  entry going 5.8 hours stale. Directives cannot be routed to sessions the board cannot see.

  ## THE THESIS
  opencode is ALREADY a client/server program; the TUI is one client. Verified live on this box:
  `GET /api/session/active` (see), `POST /api/session/{id}/prompt {"delivery":"steer"}` (inject into a
  RUNNING turn), `POST .../interrupt` (stop), `GET /api/event` (SSE push), plus question/permission
  reply endpoints. Cross-host via `--hostname 0.0.0.0` + `OPENCODE_SERVER_PASSWORD`.
  **MCP tool calls are model-elective; an HTTP server is harness-elective — the model has no vote.**
  That distinction is the whole reason to look at this.

  ## THE CONSTRAINT THAT SHAPES IT
  Reads are global, but steer/interrupt only work on sessions whose agent loop the process OWNS.
  `run --attach` is see-only — interrupt was a NO-OP on a genuinely hung run. So workers must BE
  servers (`opencode --port N`). A `--port` TUI still stays interactively watchable.

  ## HONEST TENSIONS TO REPORT, NOT BURY
  * Agent-SPECIFIC, against the standing agent-agnostic directive. Proposed mitigation is a 5-verb
    adapter with an ACP backend later — the spike must give an honest read on whether that boundary
    is real or a fig leaf.
  * Losses vs the bridge: no ticket/claim semantics (Faktory is already running on this fleet — does
    it cover that half?) and cross-host liveness becomes reachability rather than lease.
  * Open unknowns flagged by the research: `sync.steal` semantics, `--mdns` usability.
accept: |
  DONE-CONTRACT:
  - `fleet/session-ctl.sh` (~60 lines, curl only): `list | steer | stop | reply | watch`. No daemon,
    no framework, no new dependency. Thin enough to delete.
  - Each of the 5 verbs VERIFIED BY EXECUTION with the actual command and actual response pasted.
    **`stop` must be proven against a session genuinely mid-work** — an interrupt that "works" on an
    idle session proves nothing, and `--attach` already produced exactly that false positive.
  - Death detection demonstrated: kill the process, show how and how fast the manager learns.
  - The 4 live fleet sessions UNTOUCHED — list PIDs before and after and prove it.
  - Every throwaway session/port cleaned up.
  - A GO/NO-GO on replacing the bridge, with what we lose stated concretely.
  - **A verb that FAILS is a successful spike outcome.** A spike that confirms everything is more
    suspicious than one that finds a wall — report walls plainly.
  - NO migration, NO deletion of the bridge, NO edits to proxy.py or daemon.py.

## Dependencies & sequence

- **Depends on: NOTHING. Startable immediately.** Owns one new rig script and its report; cannot
  collide with any board ticket or worktree.
- **Blocks:** any decision to retire the session-bridge. Also gates whether BRIDGE-PROXY-HEARTBEAT's
  nudge-clearing defect is worth fixing at all (deferred under operator decision 25b pending this).
- **Wave:** spike lane, P1.
