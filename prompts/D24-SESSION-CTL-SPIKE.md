# SESSION — D24 SPIKE: prove opencode's HTTP control plane can replace the session-bridge

**Model:** NON-ANTHROPIC via the Charon gateway. Never Claude/Anthropic. work_class `rig-meta`.
**This is a TIMEBOXED SPIKE (~2h), not a migration.** Prove or disprove; do not port anything yet.
**Repo:** charon-private · **Branch:** `spike/session-ctl` ·
**Worktree:** `/home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE` — ISOLATED.

## FIRST ACTS
0. `NAME="$(bash /home/stack/charon-private/fleet/claim-jedi-name.sh)"; echo "claimed: $NAME"`
   Then `session-bridge_register(session_id="<NAME>", name="D24-SESSION-CTL-SPIKE", repo="charon",
   ticket="D24-SESSION-CTL-SPIKE", status="in-progress", model="<your model>")`.
   If the lease expires do NOT renew — **re-register**. (Yes: you are using the very mechanism you
   are evaluating. Note how it behaves — that is data.)
1. `git -C /home/stack/charon-private worktree add -b spike/session-ctl /home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE master`
2. `cd /home/stack/charon-private-wt/D24-SESSION-CTL-SPIKE`
3. Acquire the lease FROM INSIDE THIS WORKTREE (it binds to the acquiring worktree):
   `bash /home/stack/charon-private/fleet/work-lease.sh acquire D24-SESSION-CTL-SPIKE`
   **NEVER use `WORK_LEASE_BYPASS=1`.**
4. Read the research (BINDING context, do NOT re-derive):
   `fleet/handoff-notes/RESEARCH-AGENT-COMMS-2026-07-26.md` (442 lines)

## WHY THIS EXISTS
The hand-rolled session-bridge (3,073 LOC + one sidecar process per session) depends on the MODEL
choosing to call `register`/`update`. Models don't: **8 of 8 workers ran real work today without ever
registering**, and the manager repeatedly could not see or reach live sessions. Prior research
verified LIVE on this box that opencode is already a client/server program exposing exactly the
5 verbs we need. The thesis: **MCP tool calls are model-elective; an HTTP server is harness-elective
— the model has no vote.**

## THE CRITICAL CONSTRAINT (verified; shapes the whole spike)
Reads are global (shared store), but **steer/interrupt only work on sessions whose agent loop the
process OWNS**. `opencode run --attach` gives see-only — interrupt was a NO-OP on a genuinely hung
run. So workers must BE servers: `opencode --port N --model …`. Research verified a TUI launched with
`--port` serves the full API **while staying interactively watchable** — confirm that yourself.

## PROVE THESE FIVE, BY EXECUTION
Launch ONE throwaway opencode session with `--port` and drive it. For each, paste the actual command
and actual response:
1. **SEE** — `GET /api/session/active` lists it, with a title indicating what it is doing.
2. **STEER** — `POST /api/session/{id}/prompt {"delivery":"steer"}` injects a directive INTO A
   RUNNING TURN and the session visibly acts on it. This is the make-or-break verb.
3. **STOP** — `POST …/interrupt` takes it idle. Prove on a session that is genuinely mid-work, not
   idle — an interrupt that "works" on an idle session proves nothing.
4. **WATCH** — `GET /api/event` (SSE) pushes status without polling.
5. **DEATH DETECTION** — kill the process; show how the manager learns it died, and how fast.

## DELIVERABLE — `fleet/session-ctl.sh` (~60 lines, curl wrapper, 5 verbs)
`list | steer <id> <msg> | stop <id> | reply <id> <answer> | watch`. Thin by design. No framework, no
daemon, no new dependency. It should be obvious enough to delete.

## ANSWER THE OPEN QUESTIONS HONESTLY
- `sync.steal` semantics — flagged UNKNOWN by the research. What does it do; does it endanger us?
- `--mdns` usability for cross-host discovery.
- **What we LOSE vs the bridge:** ticket/claim semantics and lease-based cross-host liveness become
  reachability. Say concretely how bad that is. Faktory is already running on this fleet — does it
  cover the claim half?
- The standing directive is agent-AGNOSTIC tooling; this is opencode-specific. Does the 5-verb
  adapter boundary genuinely mitigate that, or is it a fig leaf? Give your honest read.

## RULES
- **Do NOT touch the 4 live fleet sessions.** List PIDs before and after and prove you did not.
- Do NOT modify `proxy.py`, `daemon.py` or anything in `~/.config/opencode/session-bridge/`.
- Do NOT delete or migrate the bridge. This spike only produces evidence + `session-ctl.sh`.
- Clean up every throwaway session/port you create.
- FAIL-LOUD: no `| tail`, `| head`, `|| true`; `set -o pipefail` on verification paths.
- If a verb does NOT work as researched, that is a SUCCESSFUL spike outcome — report it plainly.
  A spike that "confirms" everything is more suspicious than one that finds a wall.

## REPORT
Write to `/home/stack/charon-private/fleet/handoff-notes/SPIKE-SESSION-CTL-2026-07-26.md`.
Reply: file path + <=15 lines — per-verb VERIFIED/FAILED, the sync.steal answer, what we lose, and a
GO/NO-GO on replacing the bridge.

## LAST STEP
```
git add -A && git commit -m "D24 spike: session-ctl.sh + evidence for opencode HTTP control plane"
```
Do NOT push.

## Dependencies & sequence
- **Depends on: NOTHING.** Owns one new rig script + a report. Cannot collide with any board ticket.
- **Wave:** spike lane. Timebox ~2h; report findings even if incomplete.
